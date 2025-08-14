#!/bin/bash

# Variables
VPC_CIDR="10.0.0.0/16"
PUBLIC_SUBNET_CIDR="10.0.1.0/24"
PRIVATE_SUBNET_CIDR="10.0.2.0/24"
REGION="eu-west-1"

# Configure AWS CLI to bypass SSL verification (for corporate networks)
export AWS_CLI_SSL_NO_VERIFY=1
export PYTHONHTTPSVERIFY=0
export SSL_VERIFY=false

# Alternative method: use --no-verify-ssl flag
AWS_EXTRA_ARGS="--no-verify-ssl"

echo "Creating VPC infrastructure for Lambda static IP..."

# Create VPC
VPC_ID=$(aws ec2 create-vpc \
  $AWS_EXTRA_ARGS \
  --cidr-block $VPC_CIDR \
  --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=meraki-lambda-vpc}]" \
  --query 'Vpc.VpcId' \
  --output text)

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
  echo "ERROR: Failed to create VPC"
  echo "Please check your AWS credentials and network connectivity"
  exit 1
fi
echo "Created VPC: $VPC_ID"

# Enable DNS hostnames
aws ec2 modify-vpc-attribute $AWS_EXTRA_ARGS --vpc-id $VPC_ID --enable-dns-hostnames

# Create Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway \
  $AWS_EXTRA_ARGS \
  --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=meraki-igw}]" \
  --query 'InternetGateway.InternetGatewayId' \
  --output text)

if [ -z "$IGW_ID" ] || [ "$IGW_ID" == "None" ]; then
  echo "ERROR: Failed to create Internet Gateway"
  exit 1
fi
echo "Created Internet Gateway: $IGW_ID"

# Attach IGW to VPC
aws ec2 attach-internet-gateway $AWS_EXTRA_ARGS --internet-gateway-id $IGW_ID --vpc-id $VPC_ID

# Create Public Subnet
PUBLIC_SUBNET_ID=$(aws ec2 create-subnet \
  $AWS_EXTRA_ARGS \
  --vpc-id $VPC_ID \
  --cidr-block $PUBLIC_SUBNET_CIDR \
  --availability-zone "${REGION}a" \
  --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=meraki-public-subnet}]" \
  --query 'Subnet.SubnetId' \
  --output text)

if [ -z "$PUBLIC_SUBNET_ID" ] || [ "$PUBLIC_SUBNET_ID" == "None" ]; then
  echo "ERROR: Failed to create Public Subnet"
  exit 1
fi
echo "Created Public Subnet: $PUBLIC_SUBNET_ID"

# Create Private Subnet
PRIVATE_SUBNET_ID=$(aws ec2 create-subnet \
  $AWS_EXTRA_ARGS \
  --vpc-id $VPC_ID \
  --cidr-block $PRIVATE_SUBNET_CIDR \
  --availability-zone "${REGION}a" \
  --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=meraki-private-subnet}]" \
  --query 'Subnet.SubnetId' \
  --output text)

if [ -z "$PRIVATE_SUBNET_ID" ] || [ "$PRIVATE_SUBNET_ID" == "None" ]; then
  echo "ERROR: Failed to create Private Subnet"
  exit 1
fi
echo "Created Private Subnet: $PRIVATE_SUBNET_ID"

# Allocate Elastic IP for NAT Gateway
EIP_ALLOCATION_ID=$(aws ec2 allocate-address \
  $AWS_EXTRA_ARGS \
  --domain vpc \
  --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=meraki-nat-eip}]" \
  --query 'AllocationId' \
  --output text)

if [ -z "$EIP_ALLOCATION_ID" ] || [ "$EIP_ALLOCATION_ID" == "None" ]; then
  echo "ERROR: Failed to allocate Elastic IP"
  exit 1
fi
echo "Allocated Elastic IP: $EIP_ALLOCATION_ID"

# Get Elastic IP address
EIP_ADDRESS=$(aws ec2 describe-addresses \
  $AWS_EXTRA_ARGS \
  --allocation-ids $EIP_ALLOCATION_ID \
  --query 'Addresses[0].PublicIp' \
  --output text)

if [ -z "$EIP_ADDRESS" ] || [ "$EIP_ADDRESS" == "None" ]; then
  echo "ERROR: Failed to get Elastic IP address"
  exit 1
fi
echo "Static IP Address: $EIP_ADDRESS"

# Create NAT Gateway
NAT_GW_ID=$(aws ec2 create-nat-gateway \
  $AWS_EXTRA_ARGS \
  --subnet-id $PUBLIC_SUBNET_ID \
  --allocation-id $EIP_ALLOCATION_ID \
  --query 'NatGateway.NatGatewayId' \
  --output text)

if [ -z "$NAT_GW_ID" ] || [ "$NAT_GW_ID" == "None" ]; then
  echo "ERROR: Failed to create NAT Gateway"
  exit 1
fi
echo "Created NAT Gateway: $NAT_GW_ID"

# Wait for NAT Gateway to be available
echo "Waiting for NAT Gateway to be available..."
aws ec2 wait nat-gateway-available $AWS_EXTRA_ARGS --nat-gateway-ids $NAT_GW_ID

# Tag NAT Gateway after creation
aws ec2 create-tags $AWS_EXTRA_ARGS \
  --resources $NAT_GW_ID \
  --tags Key=Name,Value=meraki-nat-gw

# Create route table for public subnet
PUBLIC_RT_ID=$(aws ec2 create-route-table \
  $AWS_EXTRA_ARGS \
  --vpc-id $VPC_ID \
  --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=meraki-public-rt}]" \
  --query 'RouteTable.RouteTableId' \
  --output text)
echo "Created Public Route Table: $PUBLIC_RT_ID"

# Add route to Internet Gateway
aws ec2 create-route \
  $AWS_EXTRA_ARGS \
  --route-table-id $PUBLIC_RT_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate public subnet with public route table
aws ec2 associate-route-table \
  $AWS_EXTRA_ARGS \
  --subnet-id $PUBLIC_SUBNET_ID \
  --route-table-id $PUBLIC_RT_ID

# Create route table for private subnet
PRIVATE_RT_ID=$(aws ec2 create-route-table \
  $AWS_EXTRA_ARGS \
  --vpc-id $VPC_ID \
  --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=meraki-private-rt}]" \
  --query 'RouteTable.RouteTableId' \
  --output text)
echo "Created Private Route Table: $PRIVATE_RT_ID"

# Add route to NAT Gateway
aws ec2 create-route \
  $AWS_EXTRA_ARGS \
  --route-table-id $PRIVATE_RT_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id $NAT_GW_ID

# Associate private subnet with private route table
aws ec2 associate-route-table \
  $AWS_EXTRA_ARGS \
  --subnet-id $PRIVATE_SUBNET_ID \
  --route-table-id $PRIVATE_RT_ID

# Create Security Group for Lambda
LAMBDA_SG_ID=$(aws ec2 create-security-group \
  $AWS_EXTRA_ARGS \
  --group-name meraki-lambda-sg \
  --description "Security group for Meraki Lambda function" \
  --vpc-id $VPC_ID \
  --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=meraki-lambda-sg}]" \
  --query 'GroupId' \
  --output text)
echo "Created Security Group: $LAMBDA_SG_ID"

# Add outbound rule for HTTPS
aws ec2 authorize-security-group-egress \
  $AWS_EXTRA_ARGS \
  --group-id $LAMBDA_SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

echo ""
echo "=== VPC Setup Complete ==="
echo "VPC ID: $VPC_ID"
echo "Private Subnet ID: $PRIVATE_SUBNET_ID"
echo "Security Group ID: $LAMBDA_SG_ID"
echo "Static IP Address: $EIP_ADDRESS"
echo ""
echo "Add these to your GitHub Secrets:"
echo "VPC_SUBNET_ID: $PRIVATE_SUBNET_ID"
echo "LAMBDA_SECURITY_GROUP_ID: $LAMBDA_SG_ID"
echo "STATIC_IP_ADDRESS: $EIP_ADDRESS"