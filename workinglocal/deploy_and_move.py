#!/usr/bin/env python3

import subprocess
import sys
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deployment.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def run_script(script_name, config_file):
    """Run a Python script and return True if successful"""
    logger.info(f"Executing {script_name}...")
    try:
        result = subprocess.run(
            ['python', script_name, '--config', config_file],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(result.stdout)
        if result.stderr:
            logger.warning(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Script {script_name} failed!")
        logger.error(f"Output: {e.output}")
        return False

def main():
    config_file = 'config.json'
    
    # Step 1: Create network
    if run_script('meraki_network.py', config_file):
        logger.info("Network creation successful")
        # Wait for network to fully initialize
        time.sleep(30)
        
        # Step 2: Move device
        if run_script('device-move.py', config_file):
            logger.info("Device move successful")
            sys.exit(0)
        else:
            logger.error("Device move failed")
            sys.exit(1)
    else:
        logger.error("Network creation failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
