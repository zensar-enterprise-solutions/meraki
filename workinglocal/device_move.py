#!/usr/bin/env python3

import requests
import json
import time
import logging
import sys
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging for Lambda compatibility
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class DeviceMover:
    def __init__(self, config):
        self.api_key = config['meraki_api_key']
        self.org_id = config['organization_id']
        self.source_serial = config.get('source_device', '').lower()
        self.target_network = config.get('target_network', config.get('network_name'))
        
        # Configure session with retries
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.1,
            status_forcelist=[408, 429, 500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Meraki API headers
        self.headers = {
            'X-Cisco-Meraki-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        self.base_url = "https://api.meraki.com/api/v1"
        
        # Security: Set default timeout for all requests
        self.request_timeout = 30
        
        # Validate configuration
        if not self.source_serial:
            raise ValueError("source_device MAC address is required")
        if not self.target_network:
            raise ValueError("target_network or network_name is required")

    def get_device_details(self):
        """Get current device network assignment"""
        try:
            # Try getting device details directly
            response = self.session.get(
                f"{self.base_url}/organizations/{self.org_id}/inventory/devices",
                headers=self.headers,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                devices = response.json()
                mac_clean = self.source_serial.replace(':', '').lower()
                
                # Try matching by MAC or serial
                device = next(
                    (d for d in devices if 
                     d.get('mac', '').lower().replace(':', '') == mac_clean or
                     d.get('serial', '').lower() == mac_clean
                    ), None
                )
                
                if device:
                    logger.info(f"Found device: {device.get('serial')} (MAC: {device.get('mac', 'Unknown')})")
                    return device
                    
                logger.error(f"Device {self.source_serial} not found")
                logger.info("Available devices:")
                for d in devices:
                    logger.info(f"- Serial: {d.get('serial')}, MAC: {d.get('mac', 'Unknown')}")
            else:
                logger.error(f"Failed to get devices. Status: {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Error getting device details: {e}")
            return None

    def get_target_network_id(self):
        """Get target network ID"""
        try:
            response = self.session.get(
                f"{self.base_url}/organizations/{self.org_id}/networks",
                headers=self.headers,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                networks = response.json()
                # Try exact match first
                network = next(
                    (n for n in networks if 
                     n['name'].lower() == self.target_network.lower() or
                     n['name'].lower().startswith('meraki-network')
                    ), None
                )
                
                if network:
                    logger.info(f"Found matching network: {network['name']} (ID: {network['id']})")
                    self.target_network = network['name']  # Update to actual name
                    return network['id']
                
                logger.error(f"Network matching '{self.target_network}' not found")
                logger.info("Available networks:")
                for n in networks:
                    logger.info(f"- {n['name']}")
                return None
            
            logger.error(f"Failed to get networks: {response.text}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting networks: {e}")
            return None

    def move_device(self, device, target_network_id):
        """Move device to target network"""
        try:
            # First remove from current network if needed
            if device.get('networkId'):
                logger.info(f"Removing device from current network {device['networkId']}")
                self.session.post(
                    f"{self.base_url}/networks/{device['networkId']}/devices/{device['serial']}/remove",
                    headers=self.headers,
                    timeout=self.request_timeout
                )
                time.sleep(2)  # Wait for removal to process
            
            # Claim to new network
            response = self.session.post(
                f"{self.base_url}/networks/{target_network_id}/devices/claim",
                headers=self.headers,
                json={"serials": [device['serial']]},
                timeout=self.request_timeout
            )     
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully moved device to network {self.target_network}")
                return True
            else:
                logger.error(f"Failed to move device. Status: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error moving device: {e}")
            return False

def main():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

    mover = DeviceMover(config)
    
    # Get device details
    device = mover.get_device_details()
    if not device:
        sys.exit(1)
    
    # Get target network ID
    target_network_id = mover.get_target_network_id()
    if not target_network_id:
        sys.exit(1)
    
    # Move device
    if mover.move_device(device, target_network_id):
        logger.info("Device move completed successfully!")
        sys.exit(0)
    else:
        logger.error("Device move failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()