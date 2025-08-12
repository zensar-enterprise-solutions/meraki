#!/usr/bin/env python3

import subprocess
import sys
import logging
import time
import os

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
        # Security fix: Use absolute path for python executable and proper subprocess call
        python_executable = sys.executable  # Use the same Python interpreter
        result = subprocess.run(
            [python_executable, script_name, '--config', config_file],
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # Add timeout to prevent hanging processes
        )
        logger.info(result.stdout)
        if result.stderr:
            logger.warning(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Script {script_name} failed!")
        logger.error(f"Return code: {e.returncode}")
        if e.stdout:
            logger.error(f"Stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Stderr: {e.stderr}")
        return False
    except subprocess.TimeoutExpired as e:
        logger.error(f"Script {script_name} timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Unexpected error running {script_name}: {e}")
        return False

def main():
    config_file = 'config.json'
    
    # Validate that required files exist before starting
    required_files = [config_file, 'meraki_network.py', 'device_move.py']
    for file_path in required_files:
        if not os.path.exists(file_path):
            logger.error(f"Required file not found: {file_path}")
            sys.exit(1)
    
    logger.info("Starting deployment and device move process...")
    
    # Step 1: Create network
    if run_script('meraki_network.py', config_file):
        logger.info("Network creation successful")
        # Wait for network to fully initialize
        logger.info("Waiting 30 seconds for network initialization...")
        time.sleep(30)
        
        # Step 2: Move device
        if run_script('device_move.py', config_file):
            logger.info("Device move successful")
            logger.info("Deployment and device move completed successfully!")
            sys.exit(0)
        else:
            logger.error("Device move failed")
            sys.exit(1)
    else:
        logger.error("Network creation failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
