# Index Delivery Modes

RegulatorIQ supports three automated index delivery strategies:

---

## 1. Delivery Modes

1. **Baked Mode (`BAKE_MAX_BYTES <= 700 MB`):**
   - The index package (`.tar.zst`) is copied directly into the Docker image at build time.
   - Result: Fastest possible container cold start (< 15 seconds to `/ready`).
   - Used when index size is within image layer limits.

2. **Fetched Mode (`INDEX_URL` configured):**
   - The container starts with an empty ephemeral disk. `entrypoint.sh` downloads the index from a Hugging Face Dataset repository, GitHub release asset, or presigned S3/GCS URL.
   - Resumes partial downloads via HTTP Range headers.
   - Verifies SHA256 checksum before unpacking; refuses to start on mismatch (Exit Code 78).

3. **External Mode (`VECTOR_BACKEND=qdrant_cloud`):**
   - Vector embeddings are hosted externally on managed Qdrant Cloud Free Tier cluster.
   - Container only maintains lightweight local BM25 and schema metadata.
