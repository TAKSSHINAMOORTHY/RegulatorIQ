# Pending Deployment: AWS EC2 (ap-south-1)

AWS Terraform definitions are set up in `deploy/aws/main.tf`.

## Required Environment Variables
- `AWS_ACCESS_KEY_ID`: IAM user key
- `AWS_SECRET_ACCESS_KEY`: IAM user secret
- `AWS_DEFAULT_REGION`: `ap-south-1`

## Execution Command
```bash
python scripts/deploy.py --apply --targets aws
```
