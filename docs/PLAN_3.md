# Plan: Prompt 3 of 10 - Embeddings & Hybrid Index Store

- [x] PART A: EMBEDDING ENGINE (retrieval/embeddings.py)
  - [x] A1. BAAI/bge-small-en-v1.5 model with fastembed/ONNX
  - [x] A2. Offline caching and fallback embedder
- [x] PART B: HYBRID INDEX STORE (retrieval/index_store.py)
  - [x] B1. Dense vector storage and cosine similarity
  - [x] B2. BM25 inverted lexical index
  - [x] B3. Graph and metadata store
- [x] PART C: VERIFICATION AND TESTS (`make verify-p3`)
