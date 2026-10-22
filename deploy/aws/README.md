# AWS EC2 Free-Tier / Credit-Eligible Deployment

Region: `ap-south-1` (Mumbai)  
Access: AWS Systems Manager (SSM) Session Manager (Zero open SSH ports)  
Security: Ingress ports 80 and 443 only.

## Deployment Steps
```bash
cd deploy/aws
terraform init
terraform plan
terraform apply
```

## Teardown
```bash
cd deploy/aws
terraform destroy
```
