import json
import os
import logging
import sys

# Add package directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set environment variable to indicate Lambda environment
os.environ['AWS_LAMBDA_FUNCTION_NAME'] = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'lambda')

# Configure logging for Lambda environment (before importing workinglocal modules)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clear any existing handlers to avoid file logging issues
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Add only console handler for Lambda
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Monkey patch FileHandler to prevent file creation in Lambda
original_file_handler = logging.FileHandler

def lambda_file_handler(*args, **kwargs):
    # In Lambda, redirect file logging to console
    return logging.StreamHandler()

logging.FileHandler = lambda_file_handler

# Import required modules after logging configuration
try:
    import requests
    from workinglocal.meraki_network import MerakiNetworkManager
    from workinglocal.device_move import DeviceMover
except ImportError as e:
    print(f"Error importing dependencies: {str(e)}")
    raise
finally:
    # Restore original FileHandler
    logging.FileHandler = original_file_handler

def lambda_handler(event, context):
    try:
        # Load configuration from local file
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workinglocal', 'config.json')
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Override with environment variables if available
        config["meraki_api_key"] = os.environ.get('MERAKI_API_KEY', config.get('meraki_api_key'))
        config["organization_id"] = os.environ.get('ORGANIZATION_ID', config.get('organization_id'))
        
        # Parse input event for any runtime overrides
        body = json.loads(event.get('body', '{}'))
        
        # Allow runtime overrides from request body
        if body.get('network_name'):
            config['network_name'] = str(body.get('network_name'))
        if body.get('source_device'):
            config['source_device'] = body.get('source_device')
        if body.get('target_network'):
            config['target_network'] = body.get('target_network')
        if body.get('device_serials'):
            config['device_serials'] = body.get('device_serials')
        
        # Validate required fields
        if not config.get('network_name') or not isinstance(config.get('network_name'), str):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'network_name is required and must be a string'})
            }

        # Create network manager and deploy
        manager = MerakiNetworkManager(config)
        result = manager.deploy()
        
        if result:
            deployment_result = {'network': result}
            
            # Step 2: Move device if configured
            if config.get('source_device') and config.get('target_network'):
                logger.info("Starting device move process...")
                try:
                    mover = DeviceMover(config)
                    device = mover.get_device_details()
                    if device:
                        target_id = mover.get_target_network_id()
                        if target_id:
                            move_result = mover.move_device(device, target_id)
                            if move_result:
                                deployment_result['device_move'] = move_result
                                logger.info("Device move completed successfully")
                            else:
                                logger.warning("Device move failed, but network creation was successful")
                except Exception as e:
                    logger.error(f"Device move failed: {str(e)}")
                    logger.warning("Network creation was successful, but device move failed")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Deployment successful',
                    'result': str(deployment_result)
                })
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Network deployment failed'})
            }

    except FileNotFoundError:
        logger.error("Configuration file not found at workinglocal/config.json")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Configuration file not found'})
        }
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Invalid configuration file format'})
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }