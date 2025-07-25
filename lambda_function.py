import json
import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_secret(secret_name):
    """Get secret from AWS Secrets Manager"""
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=os.environ.get('AWS_REGION', 'eu-west-1')
    )
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            return json.loads(response['SecretString'])
    except ClientError as e:
        logger.error(f"Error getting secret: {e}")
        raise e

def lambda_handler(event, context):
    """Lambda handler for Meraki automation"""
    try:
        # Get Meraki API key from Secrets Manager
        secrets = get_secret(os.environ['MERAKI_SECRET_NAME'])
        api_key = secrets['meraki_api_key']
        
        # Parse input parameters
        params = event.get('queryStringParameters', {})
        body = json.loads(event.get('body', '{}'))
        
        config = {
            "meraki_api_key": api_key,
            "organization_id": os.environ['ORGANIZATION_ID'],
            "network_name": body.get('network_name'),
            "source_device": body.get('source_device'),
            "target_network": body.get('target_network'),
            "timezone": "Europe/London",
            "tags": ["managed", "automation"],
            "device_serials": body.get('device_serials', []),
            "wan_config": {"vlan": None}
        }
        
        # Import your Meraki automation code
        from meraki_network import MerakiNetworkManager
        from device_move import DeviceMover
        
        # Execute network creation
        manager = MerakiNetworkManager(config)
        network_result = manager.deploy()
        
        if network_result:
            # Execute device move if specified
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
        else:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Network deployment failed'})
            }
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
