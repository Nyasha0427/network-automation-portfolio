from dotenv import load_dotenv
import os
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

load_dotenv()

AR1_PASSWORD    = os.environ.get("DEVICE_PASSWORD_AR1", "changeme")
CE6800_PASSWORD = os.environ.get("DEVICE_PASSWORD_CE6800", "changeme")

devices = [
    {"device_type": "huawei_vrp", "host": "10.16.1.250", "username": "admin",
     "password": AR1_PASSWORD, "name": "AR1000v-1"},
    {"device_type": "huawei_vrp", "host": "10.16.1.246", "username": "admin",
     "password": AR1_PASSWORD, "name": "AR1000v-2"},
    {"device_type": "huawei_vrpv8", "host": "10.16.1.248", "username": "admin1",
     "password": CE6800_PASSWORD, "name": "CE6800"},
    {"device_type": "huawei_vrp", "host": "10.16.1.247", "username": "admin1",
     "password": CE6800_PASSWORD, "name": "NE40E"},
]

for device in devices:
    name = device.pop("name")
    try:
        print(f"\nConnecting to {name} ({device['host']})...")
        with ConnectHandler(**device) as conn:
            output = conn.send_command("display version", expect_string=r">")
            lines = output.split("\n")
            print(f"  Prompt : {conn.find_prompt()}")
            print(f"  Version: {lines[1].strip()}")
            print(f"  Status : Connected successfully")
    except NetmikoTimeoutException:
        print(f"  FAILED : Timeout on {device['host']}")
    except NetmikoAuthenticationException:
        print(f"  FAILED : Auth error on {device['host']}")
    except Exception as e:
        print(f"  FAILED : {e}")