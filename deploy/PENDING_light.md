# Pending Deployment: Lightweight Fallback (Render / Koyeb)

The `render.yaml` blueprint is configured for 512 MB instances.

## Required Environment Variables
- `RENDER_API_KEY`: Render account API key OR
- `KOYEB_TOKEN`: Koyeb CLI token

## Execution Command
```bash
python scripts/deploy.py --apply --targets light
```
