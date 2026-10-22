# Operational Runbook: RegulatorIQ

Standard operating procedures for managing, deploying, rolling back, and tearing down RegulatorIQ services.

---

## 1. Deploying Updates

### Full Automated Rollout
```bash
python scripts/deploy.py --apply --targets auto
```
This script automatically executes:
1. API container deployment to active providers.
2. Health and readiness verification (`/ready`).
3. Frontend deployment with updated `NEXT_PUBLIC_API_URLS`.
4. CORS origin synchronization on API targets.

---

## 2. Emergency Rollback

If a new container version fails the smoke suite:
- **Cloud Run:** `gcloud run services update-traffic regulatoriq-api --to-revisions PREVIOUS_REVISION=100`
- **Docker Compose:** Update `IMAGE_NAME` in `docker/compose.prod.yaml` to previous tag and run `docker compose -f docker/compose.prod.yaml up -d`
- **Vercel:** Roll back via Vercel dashboard or `npx vercel rollback`.

---

## 3. Secret Rotation

1. Generate a new secret token:
   ```bash
   python scripts/gen_token.py
   ```
2. Update the token in your provider secret store (`WARMUP_TOKEN`, etc.).
3. Redeploy or restart the container:
   ```bash
   docker compose -f docker/compose.prod.yaml restart api
   ```

---

## 4. Teardown Checklist

To ensure zero unexpected billing:
- **AWS:** `cd deploy/aws && terraform destroy`
- **Oracle:** Terminate VM instance or run `cd deploy/oracle && terraform destroy`
- **Cloud Run:** `gcloud run services delete regulatoriq-api`
