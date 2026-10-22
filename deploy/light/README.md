# Lightweight Fallback Deployments (Render & Koyeb)

These free-tier instances operate with 512 MB memory constraints and automatically spin down after idle windows (15 min on Render).

They must be deployed with `RAG_LIGHT_MODE=1` which activates:
- BM25-only retrieval
- Rules-based agent routing
- Memory-mapped indices
- Zero heavy torch/neural models
