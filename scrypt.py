#!/usr/bin/env python3
"""
Cisco Meraki vMX AWS Deployment Script
This script deploys a Cisco Meraki vMX appliance onto AWS by:
1. Generating authentication tokens
2. Creating necessary AWS infrastructure
3. Deploying the vMX instance
4. Configuring network settings
"""

import boto3
import requests
import json
import time
import base64
import logging
import argparse
import sys
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vmx_deployment.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MerakiVMXDeployer:
    def __init__(self, config):
        """Initialize the Meraki vMX deployer with configuration"""
        self.config = config
        self.meraki_api_key = config['meraki_api_key']
        self.org_id = config['organization_id']
        self.network_id = config.get('network_id')
        self.aws_region = config['aws_region']
        
        # Initialize AWS clients
        try:
            self.ec2_client = boto3.client('ec2', region_name=self.aws_region)
            self.iam_client = boto3.client('iam', region_name=self.aws_region)
            self.ssm_client = boto3.client('ssm', region_name=self.aws_region)
            logger.info("AWS clients initialized successfully")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS CLI or set environment variables.")
            sys.exit(1)
        
        # Meraki API base URL
        self.meraki_base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            'X-Cisco-Meraki-API-Key': self.meraki_api_key,
            'Content-Type': 'application/json'
        }
        
        # vMX specific configurations
        self.vmx_config = {
            'instance_type': config.get('instance_type', 'c5.large'),
            'key_pair': config.get('key_pair_name'),
            'vpc_cidr': config.get('vpc_cidr', '10.0.0.0/16'),
            'subnet_cidr': config.get('subnet_cidr', '10.0.1.0/24'),
            'vmx_name': config.get('vmx_name', 'Meraki-vMX-AWS'),
            'tags': config.get('tags', {})
        }

    def generate_vmx_authentication_token(self):
        """Generate authentication token for vMX deployment"""
        logger.info("Generating vMX authentication token...")
        
        try:
            # Create a new network if network_id is not provided
            if not self.network_id:
                logger.info("Creating new Meraki network for vMX...")
                network_data = {
                    "name": self.vmx_config['vmx_name'],
                    "productTypes": ["appliance"],
                    "tags": ["vmx", "aws", "automation"],
                    "timeZone": "America/Los_Angeles"
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
                else:
                    logger.error(f"Failed to create network: {response.text}")
                    return None
            
            # Generate vMX authentication token
            vmx_token_url = f"{self.meraki_base_url}/networks/{self.network_id}/appliance/vmx/authenticationToken"
            
            response = requests.post(vmx_token_url, headers=self.headers)
            
            if response.status_code == 201:
                token_data = response.json()
                auth_token = token_data['token']
                expires_at = token_data['expiresAt']
                
                logger.info(f"Authentication token generated successfully")
                logger.info(f"Token expires at: {expires_at}")
                
                # Store token in AWS SSM Parameter Store
                self.store_token_in_ssm(auth_token, expires_at)
                
                return auth_token
            else:
                logger.error(f"Failed to generate authentication token: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making API request: {e}")
            return None

    def store_token_in_ssm(self, token, expires_at):
        """Store authentication token in AWS SSM Parameter Store"""
        try:
            parameter_name = f"/meraki/vmx/{self.vmx_config['vmx_name']}/auth-token"
            
            token_data = {
                'token': token,
                'expires_at': expires_at,
                'network_id': self.network_id,
                'generated_at': datetime.now().isoformat()
            }
            
            self.ssm_client.put_parameter(
                Name=parameter_name,
                Value=json.dumps(token_data),
                Type='SecureString',
                Overwrite=True,
                Description=f"Meraki vMX authentication token for {self.vmx_config['vmx_name']}"
            )
            
            logger.info(f"Token stored in SSM Parameter Store: {parameter_name}")
            
        except ClientError as e:
            logger.error(f"Failed to store token in SSM: {e}")

    def create_vpc_infrastructure(self):
        """Create VPC infrastructure for vMX deployment"""
        logger.info("Creating VPC infrastructure...")
        
        try:
            # Create VPC
            vpc_response = self.ec2_client.create_vpc(
                CidrBlock=self.vmx_config['vpc_cidr'],
                TagSpecifications=[
                    {
                        'ResourceType': 'vpc',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"vpc-{self.vmx_config['vmx_name']}"},
                            {'Key': 'Purpose', 'Value': 'Meraki vMX'},
                            **[{'Key': k, 'Value': v} for k, v in self.vmx_config['tags'].items()]
                        ]
                    }
                ]
            )
            
            vpc_id = vpc_response['Vpc']['VpcId']
            logger.info(f"Created VPC: {vpc_id}")
            
            # Wait for VPC to be available
            self.ec2_client.get_waiter('vpc_available').wait(VpcIds=[vpc_id])
            
            # Enable DNS hostnames and DNS resolution
            self.ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
            self.ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
            
            # Create Internet Gateway
            igw_response = self.ec2_client.create_internet_gateway(
                TagSpecifications=[
                    {
                        'ResourceType': 'internet-gateway',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"igw-{self.vmx_config['vmx_name']}"},
                            {'Key': 'Purpose', 'Value': 'Meraki vMX'}
                        ]
                    }
                ]
            )
            
            igw_id = igw_response['InternetGateway']['InternetGatewayId']
            logger.info(f"Created Internet Gateway: {igw_id}")
            
            # Attach Internet Gateway to VPC
            self.ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            
            # Create public subnet
            subnet_response = self.ec2_client.create_subnet(
                VpcId=vpc_id,
                CidrBlock=self.vmx_config['subnet_cidr'],
                AvailabilityZone=f"{self.aws_region}a",
                TagSpecifications=[
                    {
                        'ResourceType': 'subnet',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"subnet-{self.vmx_config['vmx_name']}-public"},
                            {'Key': 'Type', 'Value': 'Public'},
                            {'Key': 'Purpose', 'Value': 'Meraki vMX'}
                        ]
                    }
                ]
            )
            
            subnet_id = subnet_response['Subnet']['SubnetId']
            logger.info(f"Created subnet: {subnet_id}")
            
            # Create route table
            rt_response = self.ec2_client.create_route_table(
                VpcId=vpc_id,
                TagSpecifications=[
                    {
                        'ResourceType': 'route-table',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"rt-{self.vmx_config['vmx_name']}-public"},
                            {'Key': 'Purpose', 'Value': 'Meraki vMX'}
                        ]
                    }
                ]
            )
            
            route_table_id = rt_response['RouteTable']['RouteTableId']
            logger.info(f"Created route table: {route_table_id}")
            
            # Create route to Internet Gateway
            self.ec2_client.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=igw_id
            )
            
            # Associate route table with subnet
            self.ec2_client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)
            
            # Create security group for vMX
            sg_response = self.ec2_client.create_security_group(
                GroupName=f"sg-{self.vmx_config['vmx_name']}-vmx",
                Description="Security group for Meraki vMX appliance",
                VpcId=vpc_id,
                TagSpecifications=[
                    {
                        'ResourceType': 'security-group',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"sg-{self.vmx_config['vmx_name']}-vmx"},
                            {'Key': 'Purpose', 'Value': 'Meraki vMX'}
                        ]
                    }
                ]
            )
            
            security_group_id = sg_response['GroupId']
            logger.info(f"Created security group: {security_group_id}")
            
            # Add security group rules for vMX
            self.configure_vmx_security_group(security_group_id)
            
            return {
                'vpc_id': vpc_id,
                'subnet_id': subnet_id,
                'security_group_id': security_group_id,
                'internet_gateway_id': igw_id,
                'route_table_id': route_table_id
            }
            
        except ClientError as e:
            logger.error(f"Failed to create VPC infrastructure: {e}")
            return None

    def configure_vmx_security_group(self, security_group_id):
        """Configure security group rules for vMX"""
        logger.info("Configuring security group rules for vMX...")
        
        try:
            # vMX required ports and protocols
            security_rules = [
                # SSH access
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'SSH access'
                },
                # HTTPS for management
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'HTTPS management'
                },
                # IPsec VPN - ESP
                {
                    'IpProtocol': '50',
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'IPsec ESP'
                },
                # IPsec VPN - AH
                {
                    'IpProtocol': '51',
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'IPsec AH'
                },
                # IKE/IPsec
                {
                    'IpProtocol': 'udp',
                    'FromPort': 500,
                    'ToPort': 500,
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'IKE'
                },
                # IPsec NAT-T
                {
                    'IpProtocol': 'udp',
                    'FromPort': 4500,
                    'ToPort': 4500,
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'IPsec NAT-T'
                },
                # ICMP
                {
                    'IpProtocol': 'icmp',
                    'FromPort': -1,
                    'ToPort': -1,
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'ICMP'
                }
            ]
            
            # Add ingress rules
            for rule in security_rules:
                self.ec2_client.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[{
                        'IpProtocol': rule['IpProtocol'],
                        'IpRanges': [{'CidrIp': rule['CidrIp'], 'Description': rule['Description']}],
                        **({} if rule['IpProtocol'] == 'icmp' or rule['IpProtocol'] in ['50', '51'] 
                           else {'FromPort': rule['FromPort'], 'ToPort': rule['ToPort']})
                    }]
                )
            
            logger.info("Security group rules configured successfully")
            
        except ClientError as e:
            logger.error(f"Failed to configure security group: {e}")

    def get_vmx_ami_id(self):
        """Get the latest Meraki vMX AMI ID"""
        logger.info("Looking up Meraki vMX AMI...")
        
        try:
            # Search for Meraki vMX AMI
            response = self.ec2_client.describe_images(
                Filters=[
                    {'Name': 'name', 'Values': ['meraki-vmx*']},
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'architecture', 'Values': ['x86_64']}
                ],
                Owners=['679593333241']  # Cisco Meraki AWS Account ID
            )
            
            if response['Images']:
                # Sort by creation date and get the latest
                latest_image = sorted(response['Images'], 
                                    key=lambda x: x['CreationDate'], reverse=True)[0]
                ami_id = latest_image['ImageId']
                logger.info(f"Found Meraki vMX AMI: {ami_id}")
                return ami_id
            else:
                logger.error("No Meraki vMX AMI found. Please check AWS Marketplace subscription.")
                return None
                
        except ClientError as e:
            logger.error(f"Failed to lookup vMX AMI: {e}")
            return None

    def create_vmx_user_data(self, auth_token):
        """Create user data script for vMX initialization"""
        user_data_script = f"""#!/bin/bash
# Meraki vMX initialization script
echo "Starting Meraki vMX configuration..."

# Set authentication token
echo "{auth_token}" > /opt/meraki/auth_token

# Configure network settings
cat > /opt/meraki/vmx_config.json << EOF
{{
    "network_id": "{self.network_id}",
    "auth_token": "{auth_token}",
    "deployment_time": "{datetime.now().isoformat()}",
    "aws_region": "{self.aws_region}",
    "instance_name": "{self.vmx_config['vmx_name']}"
}}
EOF

# Start Meraki services
systemctl enable meraki-agent
systemctl start meraki-agent

# Log deployment completion
echo "Meraki vMX deployment completed at $(date)" >> /var/log/vmx_deployment.log
"""
        
        return base64.b64encode(user_data_script.encode()).decode()

    def deploy_vmx_instance(self, infrastructure, auth_token):
        """Deploy the Meraki vMX EC2 instance"""
        logger.info("Deploying Meraki vMX instance...")
        
        try:
            # Get vMX AMI ID
            ami_id = self.get_vmx_ami_id()
            if not ami_id:
                return None
            
            # Create user data
            user_data = self.create_vmx_user_data(auth_token)
            
            # Create IAM role for vMX instance
            iam_role_arn = self.create_vmx_iam_role()
            
            # Launch vMX instance
            run_response = self.ec2_client.run_instances(
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=self.vmx_config['instance_type'],
                KeyName=self.vmx_config['key_pair'],
                SecurityGroupIds=[infrastructure['security_group_id']],
                SubnetId=infrastructure['subnet_id'],
                UserData=user_data,
                IamInstanceProfile={'Arn': iam_role_arn} if iam_role_arn else {},
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': self.vmx_config['vmx_name']},
                            {'Key': 'Type', 'Value': 'Meraki vMX'},
                            {'Key': 'NetworkId', 'Value': self.network_id},
                            {'Key': 'DeploymentDate', 'Value': datetime.now().strftime('%Y-%m-%d')},
                            **[{'Key': k, 'Value': v} for k, v in self.vmx_config['tags'].items()]
                        ]
                    }
                ],
                MetadataOptions={
                    'HttpTokens': 'required',
                    'HttpPutResponseHopLimit': 2,
                    'HttpEndpoint': 'enabled'
                }
            )
            
            instance_id = run_response['Instances'][0]['InstanceId']
            logger.info(f"vMX instance launched: {instance_id}")
            
            # Wait for instance to be running
            logger.info("Waiting for instance to be running...")
            self.ec2_client.get_waiter('instance_running').wait(InstanceIds=[instance_id])
            
            # Get instance details
            instance_details = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = instance_details['Reservations'][0]['Instances'][0]
            
            public_ip = instance.get('PublicIpAddress')
            private_ip = instance.get('PrivateIpAddress')
            
            logger.info(f"vMX instance is running")
            logger.info(f"Instance ID: {instance_id}")
            logger.info(f"Public IP: {public_ip}")
            logger.info(f"Private IP: {private_ip}")
            
            return {
                'instance_id': instance_id,
                'public_ip': public_ip,
                'private_ip': private_ip,
                'ami_id': ami_id
            }
            
        except ClientError as e:
            logger.error(f"Failed to deploy vMX instance: {e}")
            return None

    def create_vmx_iam_role(self):
        """Create IAM role for vMX instance"""
        try:
            role_name = f"MerakiVMXRole-{self.vmx_config['vmx_name']}"
            
            # Trust policy for EC2
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            # Create IAM role
            self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="IAM role for Meraki vMX instance",
                Tags=[
                    {'Key': 'Purpose', 'Value': 'Meraki vMX'},
                    {'Key': 'VMXName', 'Value': self.vmx_config['vmx_name']}
                ]
            )
            
            # Attach policies
            policies = [
                'arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy',
                'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
            ]
            
            for policy_arn in policies:
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            
            # Create instance profile
            profile_name = f"MerakiVMXProfile-{self.vmx_config['vmx_name']}"
            self.iam_client.create_instance_profile(InstanceProfileName=profile_name)
            self.iam_client.add_role_to_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role_name
            )
            
            # Wait for instance profile to be ready
            time.sleep(10)
            
            profile_response = self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
            return profile_response['InstanceProfile']['Arn']
            
        except ClientError as e:
            logger.warning(f"Failed to create IAM role: {e}")
            return None

    def verify_vmx_deployment(self, instance_details):
        """Verify vMX deployment and registration with Meraki Dashboard"""
        logger.info("Verifying vMX deployment...")
        
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Check device status in Meraki Dashboard
                devices_response = requests.get(
                    f"{self.meraki_base_url}/networks/{self.network_id}/devices",
                    headers=self.headers
                )
                
                if devices_response.status_code == 200:
                    devices = devices_response.json()
                    
                    # Look for the vMX device
                    vmx_device = None
                    for device in devices:
                        if device.get('model', '').startswith('vMX'):
                            vmx_device = device
                            break
                    
                    if vmx_device:
                        logger.info(f"vMX device found in Dashboard: {vmx_device['serial']}")
                        logger.info(f"Device status: {vmx_device.get('status', 'Unknown')}")
                        return vmx_device
                    else:
                        logger.info(f"Waiting for vMX to register... (attempt {attempt + 1}/{max_attempts})")
                        time.sleep(60)
                        attempt += 1
                else:
                    logger.error(f"Failed to fetch devices: {devices_response.text}")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error checking device status: {e}")
                break
        
        logger.warning("vMX device not found in Dashboard after waiting period")
        return None

    def cleanup_on_failure(self, resources):
        """Cleanup resources if deployment fails"""
        logger.info("Cleaning up resources due to deployment failure...")
        
        try:
            if 'instance_id' in resources:
                self.ec2_client.terminate_instances(InstanceIds=[resources['instance_id']])
                logger.info(f"Terminated instance: {resources['instance_id']}")
            
            # Additional cleanup logic can be added here
            
        except ClientError as e:
            logger.error(f"Error during cleanup: {e}")

    def deploy(self):
        """Main deployment method"""
        logger.info("Starting Meraki vMX deployment to AWS...")
        logger.info(f"Target region: {self.aws_region}")
        logger.info(f"Instance type: {self.vmx_config['instance_type']}")
        logger.info(f"vMX name: {self.vmx_config['vmx_name']}")
        
        deployment_results = {}
        
        try:
            # Step 1: Generate authentication token
            auth_token = self.generate_vmx_authentication_token()
            if not auth_token:
                logger.error("Failed to generate authentication token")
                return None
            
            deployment_results['auth_token'] = auth_token
            deployment_results['network_id'] = self.network_id
            
            # Step 2: Create VPC infrastructure
            infrastructure = self.create_vpc_infrastructure()
            if not infrastructure:
                logger.error("Failed to create VPC infrastructure")
                return None
            
            deployment_results['infrastructure'] = infrastructure
            
            # Step 3: Deploy vMX instance
            instance_details = self.deploy_vmx_instance(infrastructure, auth_token)
            if not instance_details:
                logger.error("Failed to deploy vMX instance")
                self.cleanup_on_failure(deployment_results)
                return None
            
            deployment_results['instance'] = instance_details
            
            # Step 4: Verify deployment
            vmx_device = self.verify_vmx_deployment(instance_details)
            if vmx_device:
                deployment_results['device'] = vmx_device
            
            # Generate deployment summary
            self.generate_deployment_summary(deployment_results)
            
            logger.info("Meraki vMX deployment completed successfully!")
            return deployment_results
            
        except Exception as e:
            logger.error(f"Unexpected error during deployment: {e}")
            self.cleanup_on_failure(deployment_results)
            return None

    def generate_deployment_summary(self, results):
        """Generate deployment summary"""
        summary = f"""
=== Meraki vMX Deployment Summary ===
Deployment Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
AWS Region: {self.aws_region}
vMX Name: {self.vmx_config['vmx_name']}

Network Information:
- Network ID: {results['network_id']}
- Authentication Token: Generated and stored in SSM

AWS Infrastructure:
- VPC ID: {results['infrastructure']['vpc_id']}
- Subnet ID: {results['infrastructure']['subnet_id']}
- Security Group ID: {results['infrastructure']['security_group_id']}

vMX Instance:
- Instance ID: {results['instance']['instance_id']}
- Public IP: {results['instance']['public_ip']}
- Private IP: {results['instance']['private_ip']}
- AMI ID: {results['instance']['ami_id']}

Dashboard URL: https://dashboard.meraki.com/o/{self.org_id}/manage/usage/list?network_id={results['network_id']}

Next Steps:
1. Wait for vMX to fully initialize (5-10 minutes)
2. Configure network settings in Meraki Dashboard
3. Set up site-to-site VPN connections
4. Configure firewall rules and policies
        """
        
        print(summary)
        
        # Save summary to file
        with open(f"vmx_deployment_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 'w') as f:
            f.write(summary)


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description='Deploy Cisco Meraki vMX to AWS')
    parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Perform dry run without deployment')
    
    args = parser.parse_args()
    
    # Load configuration
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
    required_fields = ['meraki_api_key', 'organization_id', 'aws_region', 'key_pair_name']
    for field in required_fields:
        if field not in config:
            logger.error(f"Required configuration field missing: {field}")
            sys.exit(1)
    
    if args.dry_run:
        logger.info("Dry run mode - no resources will be created")
        logger.info(f"Configuration validated successfully")
        logger.info(f"Target region: {config['aws_region']}")
        logger.info(f"Instance type: {config.get('instance_type', 'c5.large')}")
        return
    
    # Initialize deployer and start deployment
    deployer = MerakiVMXDeployer(config)
    result = deployer.deploy()
    
    if result:
        logger.info("Deployment completed successfully!")
        sys.exit(0)
    else:
        logger.error("Deployment failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()