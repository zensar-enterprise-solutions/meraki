#!/usr/bin/env python3
"""
Cisco Meraki Network Creation and Device Management Script
This script:
1. Creates a new Meraki network
2. Adds devices to the network
3. Verifies device status
"""

import requests
import json
import logging
import argparse
import sys
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('meraki_network.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MerakiNetworkManager:
    def __init__(self, config):
        """Initialize the Meraki Network Manager with configuration"""
        self.config = config
        self.meraki_api_key = config['meraki_api_key']
        self.org_id = config['organization_id']
        self.network_id = config.get('network_id')
        
        # Meraki API base URL and headers
        self.meraki_base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            'X-Cisco-Meraki-API-Key': self.meraki_api_key,
            'Content-Type': 'application/json'
        }

    def create_network(self):
        """Create a new Meraki network"""
        logger.info("Creating new Meraki network...")
        
        try:
            # Add timestamp to network name to ensure uniqueness
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            network_name = f"{self.config.get('network_name', 'Meraki-Network')}-{timestamp}"
            
            network_data = {
                "name": network_name,
                "productTypes": ["appliance", "switch", "wireless"],  # Adjust as needed
                "tags": self.config.get('tags', []),
                "timeZone": self.config.get('timezone', 'Europe/London')
            }
            
            response = requests.post(
                f"{self.meraki_base_url}/organizations/{self.org_id}/networks",
                headers=self.headers,
                json=network_data
            )
            
            if response.status_code == 201:
                network = response.json()
                self.network_id = network['id']
                logger.info(f"Created network: {self.network_id}")
                return network
            else:
                logger.error(f"Failed to create network: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making API request: {e}")
            return None

    def add_devices(self, serial_numbers):
        """Add devices to the network"""
        logger.info(f"Adding devices to network {self.network_id}...")
        
        try:
            response = requests.post(
                f"{self.meraki_base_url}/organizations/{self.org_id}/claim",
                headers=self.headers,
                json={
                    "serials": serial_numbers,
                    "networkId": self.network_id
                }
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully claimed devices: {serial_numbers}")
                # Add delay to allow claim to propagate
                logger.info("Waiting 30 seconds for device claim to process...")
                time.sleep(30)
                return self.verify_devices(serial_numbers)
            else:
                logger.error(f"Failed to claim devices: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding devices: {e}")
            return None

    def verify_devices(self, serial_numbers):
        """Verify devices are added with enhanced retry logic"""
        logger.info("Verifying device status...")
        max_attempts = 4  # Increased from 3 to 4 attempts
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Check device statuses
                status_response = requests.get(
                    f"{self.meraki_base_url}/networks/{self.network_id}/devices/statuses",
                    headers=self.headers
                )
                
                # Check basic device listing
                devices_response = requests.get(
                    f"{self.meraki_base_url}/networks/{self.network_id}/devices",
                    headers=self.headers
                )
                
                if status_response.status_code == 200 and devices_response.status_code == 200:
                    device_statuses = status_response.json()
                    devices = devices_response.json()
                    
                    # Match devices with their statuses
                    claimed_devices = []
                    for device in devices:
                        if device['serial'] in serial_numbers:
                            # Find matching status
                            status = next((s for s in device_statuses if s['serial'] == device['serial']), {})
                            device['connectionStatus'] = status.get('status')
                            device['lastReportedAt'] = status.get('lastReportedAt')
                            claimed_devices.append(device)
                    
                    if claimed_devices:
                        logger.info(f"Found {len(claimed_devices)} devices in network:")
                        for device in claimed_devices:
                            logger.info(
                                f"- {device['model']} ({device['serial']}): "
                                f"Status: {device.get('connectionStatus', 'Unknown')}, "
                                f"Last Seen: {device.get('lastReportedAt', 'Never')}"
                            )
                        return claimed_devices
                    
                    attempt += 1
                    logger.info(f"No devices found yet. Attempt {attempt}/{max_attempts}")
                    logger.info("Waiting 60 seconds before next check...")  # Increased wait time
                    time.sleep(60)
                else:
                    logger.error(f"Failed to verify devices: {devices_response.text}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error verifying devices: {e}")
                attempt += 1
                time.sleep(30)
        
        logger.error(f"Verification timeout - no devices found after {max_attempts} attempts")
        logger.info("Please verify device status in Meraki Dashboard manually")
        logger.info(f"Dashboard URL: https://dashboard.meraki.com/o/{self.org_id}/manage/organization/inventory")
        return None

    def configure_wan_settings(self, wan_config):
        """Configure WAN settings with DHCP or static IP"""
        logger.info("Configuring WAN settings for appliance...")
        
        try:
            # Default WAN settings using DHCP
            wan_settings = {
                "wan1": {
                    "enabled": True,
                    "usingStaticIp": False,  # Use DHCP instead of static IP
                    "vlan": wan_config.get('vlan', None)  # Optional VLAN setting
                }
            }
            
            response = requests.put(
                f"{self.meraki_base_url}/networks/{self.network_id}/appliance/uplink/settings",
                headers=self.headers,
                json=wan_settings
            )
            
            if response.status_code == 200:
                logger.info("Successfully configured WAN settings with DHCP")
                # Get the assigned public IP
                status_response = requests.get(
                    f"{self.meraki_base_url}/networks/{self.network_id}/devices/statuses",
                    headers=self.headers
                )
                
                if status_response.status_code == 200:
                    devices = status_response.json()
                    for device in devices:
                        if device.get('wan1Ip'):
                            logger.info(f"Appliance WAN1 IP: {device['wan1Ip']}")
                return True
            else:
                logger.error(f"Failed to configure WAN settings: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error configuring WAN settings: {e}")
            return False

    def get_organization_inventory(self):
        """Get available devices from organization inventory"""
        logger.info("Fetching organization inventory...")
        
        try:
            response = requests.get(
                f"{self.meraki_base_url}/organizations/{self.org_id}/inventory",
                headers=self.headers
            )
            
            if response.status_code == 200:
                inventory = response.json()
                available_devices = [d for d in inventory if not d.get('networkId')]
                
                if available_devices:
                    logger.info(f"Found {len(available_devices)} available devices:")
                    for device in available_devices:
                        logger.info(f"- {device['model']} ({device['serial']})")
                    return available_devices
                else:
                    logger.warning("No available devices found in organization inventory")
                    return []
            else:
                logger.error(f"Failed to fetch inventory: {response.text}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching inventory: {e}")
            return []

    def add_devices_to_network(self, device_serials=None):
        """Add devices to network from inventory or specific serials"""
        if not device_serials:
            # Get available devices if no serials provided
            available_devices = self.get_organization_inventory()
            if not available_devices:
                return None
            device_serials = [d['serial'] for d in available_devices]
        
        logger.info(f"Adding {len(device_serials)} devices to network {self.network_id}...")
        
        try:
            # Claim devices in batches of 10
            batch_size = 10
            claimed_devices = []
            
            for i in range(0, len(device_serials), batch_size):
                batch = device_serials[i:i + batch_size]
                
                response = requests.post(
                    f"{self.meraki_base_url}/organizations/{self.org_id}/claim",
                    headers=self.headers,
                    json={
                        "serials": batch,
                        "networkId": self.network_id
                    }
                )
                
                if response.status_code == 200:
                    logger.info(f"Successfully claimed devices batch: {batch}")
                    claimed_devices.extend(batch)
                else:
                    logger.error(f"Failed to claim devices batch {batch}: {response.text}")
            
            if claimed_devices:
                logger.info(f"Successfully claimed {len(claimed_devices)} devices")
                # Wait for devices to appear in network
                logger.info("Waiting for devices to appear in network...")
                time.sleep(30)
                return self.verify_devices(claimed_devices)
            else:
                logger.error("No devices were successfully claimed")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error claiming devices: {e}")
            return None

    def get_configuration_templates(self):
        """Get available configuration templates from organization"""
        logger.info("Fetching available configuration templates...")
        
        try:
            response = requests.get(
                f"{self.meraki_base_url}/organizations/{self.org_id}/configTemplates",
                headers=self.headers
            )
            
            if response.status_code == 200:
                templates = response.json()
                if templates:
                    logger.info("Available templates:")
                    for template in templates:
                        logger.info(f"- {template['name']} (ID: {template['id']})")
                    return templates
                else:
                    logger.warning("No configuration templates found in organization")
                    return []
            else:
                logger.error(f"Failed to fetch templates: {response.text}")
                return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching templates: {e}")
            return []

    def bind_template(self, template_id='L_3859584880656523057'):
        """Bind network to configuration template"""
        logger.info(f"Binding network to template {template_id}...")
        
        try:
            response = requests.post(
                f"{self.meraki_base_url}/networks/{self.network_id}/bind",
                headers=self.headers,
                json={
                    "configTemplateId": template_id,
                    "autoBind": False  # Changed to False to handle multiple switch profiles
                }
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully bound network to template {template_id}")
                logger.warning("Note: Switches must be manually bound in dashboard due to multiple switch profiles")
                logger.info(f"Dashboard URL: https://dashboard.meraki.com/o/{self.org_id}/n/{self.network_id}/configure/switches")
                return True
            else:
                logger.error(f"Failed to bind template: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error binding template: {e}")
            return False

    def deploy(self):
        """Main deployment method"""
        logger.info("Starting Meraki network deployment...")
        deployment_results = {}
        
        try:
            # Step 1: Create network if not provided
            if not self.network_id:
                network = self.create_network()
                if not network:
                    logger.error("Failed to create network")
                    return None
                deployment_results['network'] = network
                
                logger.info("Waiting for network to initialize...")
                time.sleep(10)
            
            # Step 2: Bind to specific template
            if not self.bind_template():
                logger.error("Failed to bind template")
                logger.warning("Please bind switches manually in the dashboard")
                # Continue deployment even if template binding fails
            else:
                logger.info("Waiting for template binding to complete...")
                time.sleep(30)
        
            # Step 3: Add devices
            devices = self.add_devices_to_network(self.config.get('device_serials'))
            if devices:
                deployment_results['devices'] = devices
        
            logger.info("Network deployment completed successfully!")
            return deployment_results
        
        except Exception as e:
            logger.error(f"Unexpected error during deployment: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description='Create Meraki network and add devices')
    parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    
    args = parser.parse_args()
    
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {args.config}")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in configuration file: {args.config}")
        sys.exit(1)
    
    # Validate required configuration
    required_fields = ['meraki_api_key', 'organization_id']
    for field in required_fields:
        if field not in config:
            logger.error(f"Required configuration field missing: {field}")
            sys.exit(1)
    
    # Initialize manager and start deployment
    manager = MerakiNetworkManager(config)
    result = manager.deploy()
    
    if result:
        logger.info("Deployment completed successfully!")
        sys.exit(0)
    else:
        logger.error("Deployment failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()