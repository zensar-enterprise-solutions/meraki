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
        """Verify devices are added with retries"""
        logger.info("Verifying device status...")
        max_attempts = 5
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = requests.get(
                    f"{self.meraki_base_url}/networks/{self.network_id}/devices",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    devices = response.json()
                    claimed_devices = [d for d in devices if d['serial'] in serial_numbers]
                    
                    if claimed_devices:
                        logger.info(f"Found {len(claimed_devices)} devices in network:")
                        for device in claimed_devices:
                            logger.info(f"- {device['model']} ({device['serial']}): {device.get('status', 'Unknown')}")
                        return claimed_devices
                    else:
                        attempt += 1
                        logger.info(f"No devices found yet. Attempt {attempt}/{max_attempts}")
                        time.sleep(30)  # Wait 30 seconds between attempts
                        
                else:
                    logger.error(f"Failed to verify devices: {response.text}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error verifying devices: {e}")
                return None
        
        logger.error("Verification timeout - no devices found after maximum attempts")
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

    def deploy(self):
        """Main deployment method"""
        logger.info("Starting Meraki network deployment...")
        
        try:
            # Step 1: Create network if not provided
            if not self.network_id:
                network = self.create_network()
                if not network:
                    logger.error("Failed to create network")
                    return None
            
            # Step 2: Add devices if specified
            if 'device_serials' in self.config:
                devices = self.add_devices(self.config['device_serials'])
                if not devices:
                    logger.error("Failed to add devices")
                    return None
            
            # Step 3: Configure WAN settings if provided
            if 'wan_config' in self.config:
                wan_success = self.configure_wan_settings(self.config['wan_config'])
                if not wan_success:
                    logger.error("Failed to configure WAN settings")
                    return None
                deployment_results['wan_configured'] = True
            
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