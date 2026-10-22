# Pending Deployment: Vercel Frontend

The Next.js web application is built and configured with `web/vercel.json`.

## Required Environment Variables
- `VERCEL_TOKEN`: Vercel personal access token
- `NEXT_PUBLIC_API_URLS`: Comma-separated API target URLs

## Execution Command
```bash
python scripts/deploy.py --apply --targets vercel
```
