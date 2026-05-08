# ============================================================
# NETCONF READER — Layer 5: Multi-device with inventory
# ============================================================
# Production-ready version that:
# 1. Reads device list from YAML inventory
# 2. Attempts NETCONF connection to each device
# 3. Handles devices that don't support NETCONF gracefully
# 4. Collects interface config + state from each device
# 5. Saves results to a structured JSON report
# 6. Prints a summary table
#
# New concepts:
# json module    — saves structured data to JSON file
# try/except with specific exceptions — different handling
#                  for different failure types
# datetime       — timestamps for the report filename
# ============================================================

from ncclient import manager
from ncclient.transport.errors import SSHError, AuthenticationError
from ncclient.operations.rpc import RPCError
import xml.etree.ElementTree as ET
import yaml
import json
import os
from datetime import datetime

# ============================================================
# NAMESPACE MAP
# ============================================================
NS = {
    "ifm":  "http://www.huawei.com/netconf/vrp/huawei-ifm",
    "ietf": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
}

# ============================================================
# NETCONF CONNECTION DEFAULTS
# These are the same for all devices — port, verify, timeout
# Device-specific credentials come from the inventory file
# ============================================================
NETCONF_DEFAULTS = {
    "port":           830,
    "hostkey_verify": False,
    "device_params":  {"name": "huaweiyang"},
    "manager_params": {"timeout": 30},
}

# ============================================================
# FILTERS
# ============================================================
CONFIG_FILTER = """
<filter type="subtree">
  <ifm xmlns="http://www.huawei.com/netconf/vrp/huawei-ifm">
    <interfaces>
      <interface>
        <ifName/>
        <ifPhyType/>
        <ifMtu/>
        <ifDescr/>
      </interface>
    </interfaces>
  </ifm>
</filter>
"""

STATE_FILTER = """
<filter type="subtree">
  <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
    <interface>
      <name/>
      <enabled/>
      <description/>
    </interface>
  </interfaces>
</filter>
"""

# ============================================================
# PARSER FUNCTIONS
# ============================================================
def parse_ifm_interfaces(root, fields):
    result = {}
    for iface in root.findall(".//ifm:interface", NS):
        name_elem = iface.find("ifm:ifName", NS)
        if name_elem is None:
            continue
        name = name_elem.text
        result[name] = {"ifName": name}
        for field in fields:
            elem = iface.find(f"ifm:{field}", NS)
            result[name][field] = elem.text if elem is not None else ""
    return result


def parse_ietf_interfaces(root):
    result = {}
    for iface in root.findall(".//ietf:interface", NS):
        name_elem    = iface.find("ietf:name", NS)
        enabled_elem = iface.find("ietf:enabled", NS)
        desc_elem    = iface.find("ietf:description", NS)
        if name_elem is None:
            continue
        result[name_elem.text] = {
            "enabled":     enabled_elem.text if enabled_elem is not None else "unknown",
            "description": desc_elem.text if desc_elem is not None else "",
        }
    return result


# ============================================================
# NETCONF COLLECTION FUNCTION
# Connects to one device and collects interface data
# Returns a dict with device info and interface list
# Returns None if connection fails
#
# Specific exception handling:
# SSHError            — device unreachable or port closed
# AuthenticationError — wrong username/password
# RPCError            — device rejected our NETCONF request
# Exception           — any other unexpected error
#
# Each exception type gets a specific error message so you
# know exactly why a device failed without guessing
# ============================================================
def collect_device(hostname, ip, username, password):
    conn_params = {
        "host":     ip,
        "username": username,
        "password": password,
        **NETCONF_DEFAULTS,
    }

    try:
        with manager.connect(**conn_params) as conn:
            # Get configuration
            config_resp = conn.get_config(
                source="running",
                filter=CONFIG_FILTER
            )
            config_root  = ET.fromstring(config_resp.xml)
            config_data  = parse_ifm_interfaces(
                config_root,
                ["ifPhyType", "ifMtu", "ifDescr"]
            )

            # Get operational state
            state_resp = conn.get(filter=STATE_FILTER)
            state_root = ET.fromstring(state_resp.xml)
            state_data = parse_ietf_interfaces(state_root)

            # Merge config and state
            interfaces = []
            for if_name, config in sorted(config_data.items()):
                state = state_data.get(if_name, {})
                enabled = state.get("enabled", "unknown")
                interfaces.append({
                    "name":        if_name,
                    "type":        config.get("ifPhyType", ""),
                    "mtu":         config.get("ifMtu", ""),
                    "description": state.get("description", "")
                                   or config.get("ifDescr", ""),
                    "status":      "up" if enabled == "true" else "down",
                })

            return {
                "hostname":   hostname,
                "ip":         ip,
                "status":     "success",
                "interfaces": interfaces,
            }

    except SSHError:
        return {"hostname": hostname, "ip": ip,
                "status": "failed", "error": "SSH error — NETCONF port 830 unreachable"}
    except AuthenticationError:
        return {"hostname": hostname, "ip": ip,
                "status": "failed", "error": "Authentication failed"}
    except RPCError as e:
        return {"hostname": hostname, "ip": ip,
                "status": "failed", "error": f"RPC error: {e}"}
    except Exception as e:
        return {"hostname": hostname, "ip": ip,
                "status": "failed", "error": str(e)}


# ============================================================
# MAIN
# ============================================================
# Load inventory
with open("/home/netauto/network-automation/inventory/hosts.yaml") as f:
    inventory = yaml.safe_load(f)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = "/home/netauto/network-automation/02-device-connectivity/output"
os.makedirs(output_dir, exist_ok=True)

print(f"\nNETCONF Collection — {timestamp}")
print(f"Devices: {len(inventory['hosts'])}\n")

report = {
    "timestamp": timestamp,
    "devices":   [],
}

# Loop through all devices in inventory
for hostname, data in inventory["hosts"].items():
    ip       = data["hostname"]
    username = data["username"]
    password = data["password"]

    print(f"Connecting to {hostname} ({ip}) via NETCONF...")
    result = collect_device(hostname, ip, username, password)
    report["devices"].append(result)

    if result["status"] == "success":
        iface_count = len(result["interfaces"])
        up_count    = sum(1 for i in result["interfaces"] if i["status"] == "up")
        print(f"  Status     : Success")
        print(f"  Interfaces : {iface_count} total, {up_count} up")

        # Print interface table for this device
        print(f"\n  {'Interface':<20} {'Type':<12} {'Status':<8} {'MTU':<6} {'Description'}")
        print(f"  {'-'*65}")
        for iface in result["interfaces"]:
            print(
                f"  {iface['name']:<20}"
                f"{iface['type']:<12}"
                f"{iface['status']:<8}"
                f"{iface['mtu']:<6}"
                f"{iface['description']}"
            )
        print()
    else:
        print(f"  Status : Failed — {result['error']}\n")

# Save JSON report
report_file = f"{output_dir}/netconf_report_{timestamp}.json"
with open(report_file, "w") as f:
    json.dump(report, f, indent=2)

print(f"Report saved to {report_file}")

# Print summary
print(f"\n{'='*50}")
print(f"SUMMARY")
print(f"{'='*50}")
for device in report["devices"]:
    status = device["status"].upper()
    if device["status"] == "success":
        up = sum(1 for i in device["interfaces"] if i["status"] == "up")
        total = len(device["interfaces"])
        print(f"  {device['hostname']:<15} {status:<10} {up}/{total} interfaces up")
    else:
        print(f"  {device['hostname']:<15} {status:<10} {device.get('error', '')}")