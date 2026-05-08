# ============================================================
# SNMP POLLER — Final: Multi-device, writes to InfluxDB
# ============================================================
# New imports:
# yaml         — loads our device inventory
# datetime     — generates timestamps for each data point
# influxdb_client — writes data points to InfluxDB
# Point        — builds individual data points
# WriteOptions — configures how data is written (synchronous)
# ============================================================

import yaml
from datetime import datetime, timezone
from pysnmp.hlapi import *
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ============================================================
# INFLUXDB CONNECTION SETTINGS
# These must match what you configured during InfluxDB setup
# BUCKET  — where data is stored (we created "telemetry")
# ORG     — your organisation name (we used "netlab")
# TOKEN   — the operator token you saved during setup
# URL     — InfluxDB is running locally on Ubuntu port 8086
# ============================================================
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "XW4QNLmM_uIUQBfkgrqJVfp8ufp2wlXlyZdat2cRXT9PNO11xc3KR5gKvQKrO0GPd5QD_PbCkaTzJAd3PjQxQA=="
INFLUX_ORG    = "netlab"
INFLUX_BUCKET = "telemetry"

# ============================================================
# SNMP SETTINGS
# ============================================================
COMMUNITY = "Admin@123"
PORT = 161

# ============================================================
# OID DEFINITIONS
# Scalar OIDs — single value per device
# Interface OIDs — one value per interface
# ============================================================
SCALAR_OIDS = {
    "sysName":   "1.3.6.1.2.1.1.5.0",
    "sysUptime": "1.3.6.1.2.1.1.3.0",
}

IF_TABLE_BASE = "1.3.6.1.2.1.2.2.1"
IF_COLUMNS = {
    "ifDescr":      f"{IF_TABLE_BASE}.2",
    "ifOperStatus": f"{IF_TABLE_BASE}.8",
    "ifInOctets":   f"{IF_TABLE_BASE}.10",
    "ifOutOctets":  f"{IF_TABLE_BASE}.16",
    "ifInErrors":   f"{IF_TABLE_BASE}.14",
    "ifOutErrors":  f"{IF_TABLE_BASE}.20",
}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def ticks_to_uptime(ticks):
    """Converts SNMP timeticks to human readable string."""
    seconds = int(ticks) // 100
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def snmp_get(ip, oids_dict):
    """
    Performs SNMP GET for multiple scalar OIDs.
    Returns a dictionary of {name: value} pairs.
    Returns None if there is an error.
    """
    errorIndication, errorStatus, errorIndex, varBinds = getCmd(
        SnmpEngine(),
        CommunityData(COMMUNITY, mpModel=1),
        UdpTransportTarget((ip, PORT), timeout=2, retries=1),
        ContextData(),
        *[ObjectType(ObjectIdentity(oid)) for oid in oids_dict.values()],
    )
    if errorIndication or errorStatus:
        return None
    return {
        name: varBind[1].prettyPrint()
        for name, varBind in zip(oids_dict.keys(), varBinds)
    }


def snmp_bulk_walk(ip, col_oid):
    """
    Performs SNMP BULK walk for one interface table column.
    Returns a dictionary of {if_index: value} pairs.
    """
    errorIndication, errorStatus, errorIndex, varBinds = bulkCmd(
        SnmpEngine(),
        CommunityData(COMMUNITY, mpModel=1),
        UdpTransportTarget((ip, PORT), timeout=2, retries=1),
        ContextData(),
        0, 25,
        ObjectType(ObjectIdentity(col_oid)),
        lexicographicMode=False,
    )
    if errorIndication or errorStatus:
        return {}
    result = {}
    for row in varBinds:
        for varBind in row:
            oid_str = str(varBind[0])
            if not oid_str.startswith(col_oid + "."):
                continue
            if_index = oid_str.split(".")[-1]
            result[if_index] = varBind[1].prettyPrint()
    return result


def collect_interfaces(ip):
    """
    Walks all interface columns and combines into a
    nested dictionary keyed by interface index.
    Returns {if_index: {col_name: value}} dictionary.
    """
    interfaces = {}
    for col_name, col_oid in IF_COLUMNS.items():
        column_data = snmp_bulk_walk(ip, col_oid)
        for if_index, value in column_data.items():
            if if_index not in interfaces:
                interfaces[if_index] = {}
            interfaces[if_index][col_name] = value
    return interfaces


# ============================================================
# LOAD INVENTORY
# ============================================================
with open("/home/netauto/network-automation/inventory/hosts.yaml", "r") as f:
    inventory = yaml.safe_load(f)

# ============================================================
# CONNECT TO INFLUXDB
# InfluxDBClient manages the HTTP connection to InfluxDB
# write_api handles writing data points
# SYNCHRONOUS means we wait for confirmation each write
# ============================================================
client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ============================================================
# MAIN COLLECTION LOOP
# For each device in inventory:
# 1. Get scalar values (hostname, uptime)
# 2. Walk interface table
# 3. Build InfluxDB Point objects
# 4. Write points to InfluxDB
# ============================================================
timestamp = datetime.now(timezone.utc)
print(f"\nCollection run: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"Devices: {len(inventory['hosts'])}\n")

for hostname, data in inventory["hosts"].items():
    ip = data["hostname"]
    print(f"Polling {hostname} ({ip})...")

    # Step 1 — get scalar values
    scalars = snmp_get(ip, SCALAR_OIDS)
    if not scalars:
        print(f"  FAILED — SNMP unreachable on {ip}\n")
        continue

    device_name = scalars["sysName"]
    uptime = ticks_to_uptime(scalars["sysUptime"])
    print(f"  Device : {device_name}")
    print(f"  Uptime : {uptime}")

    # Step 2 — collect interface table
    interfaces = collect_interfaces(ip)
    print(f"  Interfaces found: {len(interfaces)}")

    # Step 3 — build and write InfluxDB points
    points = []
    for if_index, if_data in interfaces.items():
        if_name = if_data.get("ifDescr", f"if{if_index}")
        status_raw = if_data.get("ifOperStatus", "2")
        status = 1 if status_raw == "1" else 0

        # Build one Point per interface
        # Each Point becomes one row in InfluxDB
        point = (
            Point("interface_stats")
            .tag("device", device_name)
            .tag("host", hostname)
            .tag("interface", if_name)
            .field("status", status)
            .field("in_bytes", int(if_data.get("ifInOctets", 0)))
            .field("out_bytes", int(if_data.get("ifOutOctets", 0)))
            .field("in_errors", int(if_data.get("ifInErrors", 0)))
            .field("out_errors", int(if_data.get("ifOutErrors", 0)))
            .time(timestamp)
        )
        points.append(point)

    # Write all points for this device in one batch
    write_api.write(bucket=INFLUX_BUCKET, record=points)
    print(f"  Written {len(points)} points to InfluxDB\n")

# Close the InfluxDB connection cleanly
client.close()
print("Collection complete.")