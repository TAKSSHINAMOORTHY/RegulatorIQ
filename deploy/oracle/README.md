# Oracle Cloud Infrastructure (OCI) Always-Free Deployment

Target Shape: Ampere A1.Flex (2 OCPU / 12 GB RAM) or VM.Standard.E2.1.Micro (`RAG_LIGHT_MODE=1`).

## Prerequisites
- OCI Account with tenancy, user OCID, and API signing key.
- Environment variables: `OCI_TENANCY_OCID`, `OCI_USER_OCID`, `OCI_FINGERPRINT`, `OCI_KEY_PATH`, `OCI_REGION`.

## Deployment via Terraform
```bash
cd deploy/oracle
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

## Cloud-Init Script
Installs Docker, creates systemd log-rotation timers, and launches `docker/compose.prod.yaml` with Caddy automatic TLS.
