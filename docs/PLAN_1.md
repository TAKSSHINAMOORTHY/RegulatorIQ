# Plan: Prompt 1 of 10 - Foundation + Automated Official RBI Corpus Acquisition

- [x] PART A: REPOSITORY AND TOOLING
  - [x] A1. Initialise git and folder layout
  - [x] A2. Python 3.11, pyproject.toml, and dependencies
  - [x] A3. config/paths.py and config/settings.py
- [x] PART B: CORPUS TARGETS AND DATA CONTRACT
  - [x] B1. Official RBI entry points and seed URLs
  - [x] B2. Raw storage layout under data/raw/rbi/
  - [x] B3. Manifest schema (JSONL and Parquet)
- [x] PART C: CRAWLER ENGINE (ingest/)
  - [x] C1. Crawler client (polite rate limits, exponential backoff)
  - [x] C2. Resumability and checkpointing
  - [x] C3. Duplicate detection by sha256
- [x] PART D: TESTS AND VERIFICATION
  - [x] Unit tests with respx mocks
  - [x] Integration tests for pipeline
  - [x] Corpus report generation
- [x] PART E: EXECUTION (`make bootstrap`, `make data`, `make verify-p1`)
