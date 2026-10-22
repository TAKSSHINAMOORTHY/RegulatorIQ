# Google Cloud Run Free-Tier Deployment

Settings:
- Memory: 2 GiB
- CPU: 1 (startup CPU boost enabled)
- Concurrency: 8
- Min Instances: 0 (free-tier scale-to-zero)
- Max Instances: 2
- Timeout: 300s
- Request-based billing

## Deployment Command
```bash
gcloud run deploy regulatoriq-api \
  --image ghcr.io/taksshinamoorthy/regulatoriq/api:latest \
  --region asia-south1 \
  --memory 2Gi \
  --cpu 1 \
  --cpu-boost \
  --concurrency 8 \
  --min-instances 0 \
  --max-instances 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production,PORT=8080"
```
