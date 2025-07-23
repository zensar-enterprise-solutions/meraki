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
import sys
from datetime import datetime
from botocore.exceptions import ClientError
import logging

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_meraki_token(api_key, org_id, network_name):
    headers = {
        'X-Cisco-Meraki-API-Key': api_key,
        'Content-Type': 'application/json'
    }
    # Create network
    net_resp = requests.post(
        f"https://api.meraki.com/api/v1/organizations/{org_id}/networks",
        headers=headers,
        json={
            "name": network_name,
            "productTypes": ["appliance"],
            "tags": ["vmx", "aws", "automation"],
            "timeZone": "America/Los_Angeles"
        }
    )
    if net_resp.status_code != 201:
        logger.error("Meraki API POST URL used: %s", f"https://api.meraki.com/api/v1/organizations/{org_id}/networks")
        logger.error("Meraki API Key used: %s", api_key[:6] + "..." + api_key[-4:])
        logger.error("Meraki Org ID used: %s", org_id)
        logger.error("Meraki network payload: %s", json.dumps({
            "name": network_name,
            "productTypes": ["appliance"],
            "tags": ["vmx", "aws", "automation"],
            "timeZone": "America/Los_Angeles"
        }))
        logger.error("Meraki API response status: %s", net_resp.status_code)
        logger.error("Meraki API response text: %r", net_resp.text)
        logger.error("Likely causes: invalid organization ID, invalid API key, insufficient API permissions, or wrong API base URL.")
        logger.error("If you are using a Meraki 'test' or 'demo' organization, API write operations may not be allowed.")
        logger.error("Please verify your Meraki API key, organization ID, and that the API key has permissions to create networks.")
        error_msg = "Empty response body" if not net_resp.text else net_resp.text
        logger.error(f"Failed to create network: {error_msg}")
        sys.exit(1)
    network_id = net_resp.json()['id']
    # Generate token
    token_resp = requests.post(
        f"https://api.meraki.com/api/v1/networks/{network_id}/appliance/vmx/authenticationToken",
        headers=headers
    )
    if token_resp.status_code != 201:
        try:
            error_json = token_resp.json()
            error_msg = error_json.get("errors") or error_json.get("error") or token_resp.text
        except Exception:
            error_msg = token_resp.text
        logger.error(f"Failed to generate token: {error_msg}")
        sys.exit(1)
    token = token_resp.json()['token']
    logger.info(f"Generated Meraki vMX token: {token}")
    return network_id, token

def create_vpc(ec2, cidr, name):
    vpc = ec2.create_vpc(CidrBlock=cidr)
    vpc_id = vpc['Vpc']['VpcId']
    ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': name}])
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    logger.info(f"Created VPC: {vpc_id}")
    return vpc_id

def create_subnet(ec2, vpc_id, cidr, az, name):
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr, AvailabilityZone=az)
    subnet_id = subnet['Subnet']['SubnetId']
    ec2.create_tags(Resources=[subnet_id], Tags=[{'Key': 'Name', 'Value': name}])
    logger.info(f"Created subnet: {subnet_id}")
    return subnet_id

def create_igw_and_attach(ec2, vpc_id, name):
    igw = ec2.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    ec2.create_tags(Resources=[igw_id], Tags=[{'Key': 'Name', 'Value': name}])
    logger.info(f"Created and attached Internet Gateway: {igw_id}")
    return igw_id

def create_route_table(ec2, vpc_id, igw_id, subnet_id, name):
    rt = ec2.create_route_table(VpcId=vpc_id)
    rt_id = rt['RouteTable']['RouteTableId']
    ec2.create_tags(Resources=[rt_id], Tags=[{'Key': 'Name', 'Value': name}])
    ec2.create_route(RouteTableId=rt_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
    ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
    logger.info(f"Created and associated route table: {rt_id}")
    return rt_id

def create_security_group(ec2, vpc_id, name):
    sg = ec2.create_security_group(
        GroupName=name,
        Description="Meraki vMX SG",
        VpcId=vpc_id
    )
    sg_id = sg['GroupId']
    # Allow SSH, HTTPS, IKE, NAT-T, ICMP, ESP, AH
    rules = [
        {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': 'udp', 'FromPort': 500, 'ToPort': 500, 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': 'udp', 'FromPort': 4500, 'ToPort': 4500, 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': 'icmp', 'FromPort': -1, 'ToPort': -1, 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': '50', 'CidrIp': '0.0.0.0/0'},
        {'IpProtocol': '51', 'CidrIp': '0.0.0.0/0'}
    ]
    for rule in rules:
        perm = {
            'IpProtocol': rule['IpProtocol'],
            'IpRanges': [{'CidrIp': rule['CidrIp']}]
        }
        if 'FromPort' in rule:
            perm['FromPort'] = rule['FromPort']
            perm['ToPort'] = rule['ToPort']
        try:
            ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[perm])
        except ClientError:
            logger.warning(f"Rule may already exist or failed to add: {rule}")
    logger.info(f"Created security group: {sg_id}")
    return sg_id

def get_latest_vmx_ami(ec2):
    images = ec2.describe_images(
        Filters=[
            {'Name': 'name', 'Values': ['meraki-vmx*']},
            {'Name': 'state', 'Values': ['available']},
            {'Name': 'architecture', 'Values': ['x86_64']}
        ],
        Owners=['679593333241']
    )['Images']
    if not images:
        logger.error("No Meraki vMX AMI found.")
        sys.exit(1)
    latest = sorted(images, key=lambda x: x['CreationDate'], reverse=True)[0]
    logger.info(f"Using Meraki vMX AMI: {latest['ImageId']}")
    return latest['ImageId']

def deploy_vmx_instance(ec2, ami_id, instance_type, key_pair, subnet_id, sg_id, user_data, name):
    resp = ec2.run_instances(
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        InstanceType=instance_type,
        KeyName=key_pair,
        SecurityGroupIds=[sg_id],
        SubnetId=subnet_id,
        UserData=user_data,
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [{'Key': 'Name', 'Value': name}]
        }],
        MetadataOptions={
            'HttpTokens': 'required',
            'HttpPutResponseHopLimit': 2,
            'HttpEndpoint': 'enabled'
        }
    )
    instance_id = resp['Instances'][0]['InstanceId']
    logger.info(f"vMX instance launched: {instance_id}")
    ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])
    desc = ec2.describe_instances(InstanceIds=[instance_id])
    inst = desc['Reservations'][0]['Instances'][0]
    logger.info(f"Public IP: {inst.get('PublicIpAddress')}")
    logger.info(f"Private IP: {inst.get('PrivateIpAddress')}")
    return instance_id

def main():
    # Example config, replace with argparse or config file as needed
    config = {
        "meraki_api_key": "edfbb293da981d643af1255c420c79bbca91fb51",
        "organization_id": "wh7Kwc",
        "aws_region": "eu-north-1",
        "key_pair_name": "meraki-key",
        "vpc_cidr": "10.0.0.0/16",
        "subnet_cidr": "10.0.1.0/24",
        "vmx_name": "Meraki-vMX-AWS"
    }
    ec2 = boto3.client('ec2', region_name=config['aws_region'])
    # 1. Generate Meraki token
    network_id, token = generate_meraki_token(
        config['meraki_api_key'],
        config['organization_id'],
        config['vmx_name']
    )
    # 2. Create AWS infrastructure
    vpc_id = create_vpc(ec2, config['vpc_cidr'], f"vpc-{config['vmx_name']}")
    subnet_id = create_subnet(ec2, vpc_id, config['subnet_cidr'], config['aws_region'] + "a", f"subnet-{config['vmx_name']}")
    igw_id = create_igw_and_attach(ec2, vpc_id, f"igw-{config['vmx_name']}")
    rt_id = create_route_table(ec2, vpc_id, igw_id, subnet_id, f"rt-{config['vmx_name']}")
    sg_id = create_security_group(ec2, vpc_id, f"sg-{config['vmx_name']}")
    # 3. Deploy vMX instance
    ami_id = get_latest_vmx_ami(ec2)
    user_data = f"""#!/bin/bash
echo "{token}" > /opt/meraki/auth_token
echo "vMX deployed at $(date)" >> /var/log/vmx_deployment.log
"""
    instance_id = deploy_vmx_instance(
        ec2, ami_id, "c5.large", config['key_pair_name'],
        subnet_id, sg_id, user_data, config['vmx_name']
    )
    logger.info("Deployment complete.")
    logger.info(f"Meraki Dashboard URL: https://n856.meraki.com/o/{config['organization_id']}/manage/usage/list?network_id={network_id}")

if __name__ == "__main__":
    main()
