# ============================================================
# CONCEPT 1: IMPORTS
# ============================================================
# We import specific tools we need from libraries
# 'yaml' handles YAML files — our inventory format
# 'datetime' gives us timestamps for file naming
# 'os' lets us interact with the filesystem

import yaml
import os
from datetime import datetime

# ============================================================
# CONCEPT 2: FUNCTIONS
# ============================================================
# A function takes inputs, does something, returns an output
# This function loads our inventory YAML and returns it as
# a Python dictionary — a data structure we can loop through

def load_inventory(filepath):
    """
    Opens a YAML file and returns it as a Python dictionary.
    filepath: the path to the hosts.yaml file
    """
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


def get_timestamp():
    """
    Returns the current date and time as a formatted string.
    Used for naming output files uniquely.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def print_device_summary(hostname, data):
    """
    Prints a formatted summary line for one device.
    hostname: the device name from inventory (e.g. ar1000v-1)
    data: the dictionary of device details (ip, username etc)
    """
    print(f"  {hostname:<15} {data['hostname']:<18} {data['platform']}")


# ============================================================
# CONCEPT 3: CLASSES
# ============================================================
# A class is a blueprint. Here we create a DeviceInventory
# class that loads, stores and provides access to our devices.
# Every time you create an instance of this class it loads
# the inventory automatically in __init__

class DeviceInventory:
    """
    Represents the full device inventory from hosts.yaml.
    Attributes:
        filepath: path to the YAML inventory file
        hosts: dictionary of all devices
    Methods:
        load(): reads the YAML file into self.hosts
        summary(): prints all devices in a table
        get_device(hostname): returns one device's details
    """

    def __init__(self, filepath):
        """
        __init__ runs automatically when you create an instance.
        It stores the filepath and immediately loads the inventory.
        """
        self.filepath = filepath
        self.hosts = {}
        self.load()

    def load(self):
        """Loads the YAML file into self.hosts dictionary."""
        self.hosts = load_inventory(self.filepath)["hosts"]
        print(f"Loaded {len(self.hosts)} devices from {self.filepath}")

    def summary(self):
        """Prints a formatted table of all devices."""
        print(f"\n{'HOSTNAME':<15} {'IP':<18} {'PLATFORM'}")
        print("-" * 50)
        for hostname, data in self.hosts.items():
            print_device_summary(hostname, data)

    def get_device(self, hostname):
        """Returns the details dict for a specific device."""
        return self.hosts.get(hostname, None)


# ============================================================
# MAIN — this runs when you execute the script directly
# ============================================================
# The if __name__ == "__main__" block is important:
# It means this code only runs when you run this file directly
# If another script imports this file, this block is skipped
# This is how you write reusable modules

if __name__ == "__main__":
    # Create an instance of DeviceInventory
    # This calls __init__ automatically
    inventory = DeviceInventory("inventory/hosts.yaml")

    # Call the summary method to print all devices
    inventory.summary()

    # Get one specific device
    device = inventory.get_device("ce6800")
    print(f"\nCE6800 details:")
    print(f"  IP      : {device['hostname']}")
    print(f"  Platform: {device['platform']}")
    print(f"  Username: {device['username']}")