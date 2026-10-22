# Vercel Frontend Deployment

Deploys the Next.js `web/` application to Vercel production.

## Commands
```bash
cd web
npx vercel pull --yes --environment=production --token=$VERCEL_TOKEN
npx vercel build --prod --token=$VERCEL_TOKEN
npx vercel deploy --prebuilt --prod --token=$VERCEL_TOKEN
```

## Environment Variables
- `NEXT_PUBLIC_API_URLS`: Comma-separated list of deployed API endpoint URLs.
