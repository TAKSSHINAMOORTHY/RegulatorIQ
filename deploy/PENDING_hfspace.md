# Pending Deployment: Hugging Face Space

The Docker Space repository frontmatter is configured in `deploy/hfspace/README.md`.

## Required Environment Variables
- `HF_TOKEN`: Hugging Face User Access Token with write permissions.
- `HF_USERNAME`: Your Hugging Face account name.

## Execution Command
```bash
python scripts/deploy.py --apply --targets hfspace
```
