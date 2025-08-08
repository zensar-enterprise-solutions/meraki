# Meraki Automation

This repository is used for Meraki automation with AWS Lambda integration.

## AWS Infrastructure

### VPC Setup Complete
- **VPC ID**: vpc-094012fa4493dc5e0
- **Private Subnet ID**: subnet-077e022aaafe3d4e6  
- **Security Group ID**: sg-0c9030f90f5acc596
- **Static IP Address**: 13.49.144.160

### GitHub Secrets Configuration

Add the following secrets to your GitHub repository:

```
VPC_SUBNET_ID: subnet-077e022aaafe3d4e6
LAMBDA_SECURITY_GROUP_ID: sg-0c9030f90f5acc596
STATIC_IP_ADDRESS: 13.49.144.160
```

These values configure the Lambda function to use the VPC infrastructure for consistent outbound IP addressing.