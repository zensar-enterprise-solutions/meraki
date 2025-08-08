# Meraki Automation

This repository is used for Meraki automation with AWS Lambda integration.

## AWS Infrastructure

### VPC Setup Complete
- **VPC ID**: `<VPC_ID_FROM_AWS_CONSOLE>`
- **Private Subnet ID**: `<PRIVATE_SUBNET_ID>`  
- **Security Group ID**: `<SECURITY_GROUP_ID>`
- **Static IP Address**: `<STATIC_IP_ADDRESS>`

### GitHub Secrets Configuration

Add the following secrets to your GitHub repository:

```
VPC_SUBNET_ID: <your-subnet-id>
LAMBDA_SECURITY_GROUP_ID: <your-security-group-id>
STATIC_IP_ADDRESS: <your-static-ip>
```

**Note**: Replace placeholders with actual values from your AWS console.