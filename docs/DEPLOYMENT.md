# Multi-Provider Deployment Decision Tree & Guide

RegulatorIQ is designed to run across multiple free-tier and low-cost cloud providers using the exact same multi-stage Docker container image (`docker/Dockerfile`).

---

## 1. Provider Decision Matrix

| Provider | Shape / Specs | Cost | Cold Start | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Oracle Cloud (OCI)** | Ampere A1.Flex (2 OCPU / 12 GB RAM) | $0.00 (Always Free) | 0s (Always-On) | **Primary Production Target** |
| **Google Cloud Run** | 1 vCPU / 2 GiB RAM, Min instances 0 | $0.00 (2M req/mo) | 15s - 35s | Best for auto-scaling serverless API |
| **Hugging Face Spaces**| 2 vCPU / 16 GB RAM (Docker SDK) | $0.00 (Free Basic) | 0s (Kept warm 48h) | Best for public demo showcase |
| **AWS EC2 (ap-south-1)**| t3.small or t2.micro (`RAG_LIGHT_MODE=1`) | Free Tier Credits | 0s (Always-On) | Alternate regional VM in Mumbai |
| **Render / Koyeb** | 512 MB RAM (`RAG_LIGHT_MODE=1`) | $0.00 (Free Plan) | 25s - 50s | Emergency fallback API |
| **Vercel** | Next.js Edge / Serverless Frontend | $0.00 (Hobby Plan) | < 0.2s | **Primary Frontend Target** |

---

## 2. Deployment Commands

### Oracle Cloud
```bash
cd deploy/oracle && terraform init && terraform apply
```

### Google Cloud Run
```bash
gcloud run deploy regulatoriq-api --image ghcr.io/taksshinamoorthy/regulatoriq/api:latest --region asia-south1
```

### Hugging Face Space
```bash
python scripts/deploy.py --apply --targets hfspace
```

### Vercel (Frontend)
```bash
cd web && npx vercel --prod
```
