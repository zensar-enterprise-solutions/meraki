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
        # Parse input event
        body = json.loads(event.get('body', '{}'))
        
        config = {
            "meraki_api_key": os.environ['MERAKI_API_KEY'],
            "organization_id": os.environ['ORGANIZATION_ID'],
            "network_name": body.get('network_name'),
            "source_device": body.get('source_device'),
            "target_network": body.get('target_network'),
            "timezone": "Europe/London",
            "tags": ["managed", "automation"],
            "device_serials": body.get('device_serials', []),
            "wan_config": {"vlan": None}
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

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
