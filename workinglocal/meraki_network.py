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
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging for Lambda compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class MerakiNetworkManager:
    def __init__(self, config, debug=False):
        """Initialize the Meraki Network Manager with configuration"""
        self.config = config
        if debug:
            logger.setLevel(logging.DEBUG)
            
        self.meraki_api_key = config['meraki_api_key']
        self.org_id = config['organization_id']
        self.network_id = config.get('network_id')
        
        # Configure session with retries and rate limiting
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[408, 429, 500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Meraki API base URL and headers
        self.meraki_base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            'X-Cisco-Meraki-API-Key': self.meraki_api_key,
            'Content-Type': 'application/json'
        }
        
        # Validate API access
        self.validate_api_access()

    def validate_api_access(self):
        """Validate API key and organization access"""
        try:
            response = self.session.get(
                f"{self.meraki_base_url}/organizations/{self.org_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                logger.info("Successfully authenticated with Meraki API")
                return True
            else:
                logger.error(f"Failed to authenticate: {response.text}")
                raise Exception("API authentication failed")
        except Exception as e:
            logger.error(f"API validation error: {str(e)}")
            raise

    def create_network(self):
        """Create a new Meraki network"""
        logger.info("Creating new Meraki network...")
        
        try:
            # Add timestamp to network name to ensure uniqueness
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            # network_name = f"{self.config.get('network_name', 'Meraki-Network')}-{timestamp}"
            network_name = self.config.get('network_name', 'Meraki-Network-test')
            
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

    def get_organization_inventory(self, max_retries=3):
        """Get available devices from organization inventory with retries"""
        logger.info("Fetching organization inventory...")
        available_devices = []  # Initialize outside try block
        
        for attempt in range(max_retries):
            try:
                # Try inventory endpoint first
                inventory_response = requests.get(
                    f"{self.meraki_base_url}/organizations/{self.org_id}/inventory",
                    headers=self.headers
                )
                
                if inventory_response.status_code == 200:
                    inventory = inventory_response.json()
                    # Get all organization networks
                    networks_response = requests.get(
                        f"{self.meraki_base_url}/organizations/{self.org_id}/networks",
                        headers=self.headers
                    )
                    
                    if networks_response.status_code == 200:
                        networks = networks_response.json()
                        network_ids = set(n['id'] for n in networks)
                        
                        # Filter for truly available devices
                        available_devices = [
                            device for device in inventory 
                            if (not device.get('networkId') or device.get('networkId') not in network_ids)
                            and device.get('serial')
                            and device.get('orderNumber')  # Only include devices with order numbers
                        ]
                        
                        if available_devices:
                            logger.info(f"Found {len(available_devices)} available devices:")
                            for device in available_devices:
                                logger.info(
                                    f"- Model: {device.get('model', 'Unknown')}, "
                                    f"Serial: {device['serial']}, "
                                    f"Order: {device.get('orderNumber', 'N/A')}, "
                                    f"Network ID: {device.get('networkId', 'None')}"
                                )
                            return available_devices
                        
                        logger.warning("No available devices found in this attempt")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying... (Attempt {attempt + 1}/{max_retries})")
                            time.sleep(5)
                            continue
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching organization inventory: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(5)
                    continue

        logger.info("Inventory fetch complete")
        return available_devices  # Will return empty list if no devices found

    def bind_template(self, template_name='1156'):
        """Bind network to configuration template by template name"""
        logger.info(f"Looking up template ID for template name '{template_name}'...")
        try:
            # Get all config templates for the organization
            response = self.session.get(
                f"{self.meraki_base_url}/organizations/{self.org_id}/configTemplates",
                headers=self.headers
            )
            if response.status_code != 200:
                logger.error(f"Failed to fetch config templates: {response.text}")
                return False

            templates = response.json()
            template_id = None
            for template in templates:
                if template.get('name') == template_name:
                    template_id = template.get('id')
                    break

            if not template_id:
                logger.error(f"Template with name '{template_name}' not found.")
                return False

            logger.info(f"Binding network to template {template_id} ('{template_name}')...")

            response = self.session.post(
                f"{self.meraki_base_url}/networks/{self.network_id}/bind",
                headers=self.headers,
                json={
                    "configTemplateId": template_id,
                    "autoBind": False  # Disable auto-bind for switches
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
            
            # Step 2: Bind to specific template first
            if not self.bind_template():
                logger.error("Failed to bind template")
                logger.warning("Please bind switches manually in the dashboard")
            else:
                logger.info("Waiting for template binding to complete...")
                time.sleep(30)
            
            # Step 3: Check for available devices
            available_devices = self.get_organization_inventory()
            if not available_devices:
                logger.warning("No available devices found. Network created successfully but no devices to add.")
                return deployment_results
            
            # Step 4: Add available devices
            devices = self.add_devices_to_network(self.config.get('device_serials'))
            if devices:
                deployment_results['devices'] = devices
        
            logger.info("Network deployment completed successfully!")
            return deployment_results
        
        except Exception as e:
            logger.error(f"Unexpected error during deployment: {str(e)}")
            if logger.level == logging.DEBUG:
                import traceback
                logger.debug(traceback.format_exc())
            return None

def main():
    parser = argparse.ArgumentParser(description='Create Meraki network and add devices')
    parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
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
    
    try:
        # Initialize manager and start deployment
        manager = MerakiNetworkManager(config, debug=args.debug)
        result = manager.deploy()
        
        if result:
            logger.info("Deployment completed successfully!")
            sys.exit(0)
        else:
            logger.error("Deployment failed!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Script execution failed: {str(e)}")
        if args.debug:
            import traceback
            logger.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()