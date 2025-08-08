import json
import os
import logging
import sys

# Add package directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import required modules
try:
    import requests
    from workinglocal.meraki_network import MerakiNetworkManager
    from workinglocal.device_move import DeviceMover
except ImportError as e:
    print(f"Error importing dependencies: {str(e)}")
    raise

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

        # Step 1: Create network
        manager = MerakiNetworkManager(config)
        network_result = manager.deploy()
        
        if not network_result:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Network creation failed'})
            }

        # Step 2: Move device if specified
        if body.get('move_device'):
            mover = DeviceMover(config)
            device = mover.get_device_details()
            if device:
                target_id = mover.get_target_network_id()
                if target_id:
                    move_result = mover.move_device(device, target_id)
                    if not move_result:
                        return {
                            'statusCode': 500,
                            'body': json.dumps({'error': 'Device move failed'})
                        }

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Deployment successful',
                'result': network_result
            })
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
