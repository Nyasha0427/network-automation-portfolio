import yaml
import os
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# Load inventory
with open("inventory/hosts.yaml", "r") as f:
    inventory = yaml.safe_load(f)

# Commands to run on each device
commands = [
    "display version",
    "display ip interface brief",
    "display ip routing-table",
    "display interface brief",
]

# Timestamp for this collection run
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = f"02-device-connectivity/output/{timestamp}"
os.makedirs(output_dir, exist_ok=True)

print(f"\nCollection started: {timestamp}")
print(f"Output directory: {output_dir}")
print(f"Devices: {len(inventory['hosts'])}\n")

# Loop through all devices
for hostname, data in inventory["hosts"].items():
    print(f"Connecting to {hostname} ({data['hostname']})...")

    device = {
        "device_type": data["platform"],
        "host": data["hostname"],
        "username": data["username"],
        "password": data["password"],
        "timeout": 30,
    }

    try:
        with ConnectHandler(**device) as conn:
            output_lines = []
            output_lines.append(f"Device: {hostname}")
            output_lines.append(f"IP: {data['hostname']}")
            output_lines.append(f"Collected: {timestamp}\n")
            output_lines.append("=" * 60)

            for command in commands:
                print(f"  Running: {command}")
                output_lines.append(f"\n### {command} ###\n")
                try:
                    result = conn.send_command(
                        command, expect_string=r">", read_timeout=30
                    )
                    output_lines.append(result)
                except Exception as e:
                    output_lines.append(f"ERROR: {e}")

            # Save to file
            filename = f"{output_dir}/{hostname}.txt"
            with open(filename, "w") as f:
                f.write("\n".join(output_lines))

            print(f"  Saved to {filename}")
            print(f"  Status: Success\n")

    except NetmikoTimeoutException:
        print(f"  FAILED: Timeout on {data['hostname']}\n")
    except NetmikoAuthenticationException:
        print(f"  FAILED: Auth error on {data['hostname']}\n")
    except Exception as e:
        print(f"  FAILED: {e}\n")

print(f"Collection complete. Files saved to {output_dir}")