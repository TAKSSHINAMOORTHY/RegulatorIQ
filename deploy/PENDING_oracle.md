# Pending Deployment: Oracle Cloud (OCI Always-Free)

Deployment to Oracle Cloud Infrastructure is ready to trigger once credentials are provided.

## Required Environment Variables
- `OCI_TENANCY_OCID`: Your OCI Tenancy OCID
- `OCI_USER_OCID`: Your OCI User OCID
- `OCI_FINGERPRINT`: API Key fingerprint
- `OCI_KEY_PATH`: Path to RSA private key file (`.pem`)
- `OCI_REGION`: Target region (e.g., `ap-mumbai-1`)

## Execution Command
```bash
python scripts/deploy.py --apply --targets oracle
```
