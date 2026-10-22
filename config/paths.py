"""Central path configuration for RegulatorIQ.

Discovers the repository root by walking up from the current file until pyproject.toml
is found. Exposes all directory and file paths as pathlib.Path constants with optional
environment variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_repo_root() -> Path:
    """Walk up from this file to find the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to current working directory if pyproject.toml is not found
    return Path.cwd().resolve()


ROOT = find_repo_root()

# Top-level directories with environment overrides
DATA_DIR = Path(os.environ.get("RBI_DATA_DIR", ROOT / "data"))
ARTIFACTS_DIR = Path(os.environ.get("RBI_ARTIFACTS_DIR", ROOT / "artifacts"))
REPORTS_DIR = Path(os.environ.get("RBI_REPORTS_DIR", ROOT / "reports"))
DOCS_DIR = Path(os.environ.get("RBI_DOCS_DIR", ROOT / "docs"))
CONFIG_DIR = Path(os.environ.get("RBI_CONFIG_DIR", ROOT / "config"))
EVALS_DIR = Path(os.environ.get("RBI_EVALS_DIR", ROOT / "evals"))
TESTS_DIR = ROOT / "tests"

# Data contract subdirectories
RAW_DATA_DIR = DATA_DIR / "raw"
RAW_RBI_DIR = RAW_DATA_DIR / "rbi"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MANIFESTS_DIR = DATA_DIR / "manifests"

# Specific file paths
MANIFEST_JSONL_PATH = MANIFESTS_DIR / "rbi_manifest.jsonl"
MANIFEST_PARQUET_PATH = MANIFESTS_DIR / "rbi_manifest.parquet"
CHUNKS_PARQUET_PATH = PROCESSED_DATA_DIR / "chunks.parquet"
DOCUMENTS_PARQUET_PATH = PROCESSED_DATA_DIR / "documents.parquet"
LINKS_PARQUET_PATH = PROCESSED_DATA_DIR / "links.parquet"

# Phase 2 Paths
PARSED_DIR = INTERIM_DATA_DIR / "parsed"
QUARANTINE_DIR = INTERIM_DATA_DIR / "quarantine"
DOCUMENTS_PATH = DOCUMENTS_PARQUET_PATH
CHUNKS_PATH = CHUNKS_PARQUET_PATH
LINKS_PATH = LINKS_PARQUET_PATH
PARSE_REPORT_MD = REPORTS_DIR / "parse_report.md"
PARSE_REPORT_JSON = REPORTS_DIR / "parse_report.json"
LINK_ANOMALIES_MD = REPORTS_DIR / "link_anomalies.md"

# Index and Cache artifacts
INDEX_BASE_DIR = ARTIFACTS_DIR / "index"
INDEX_DIR = INDEX_BASE_DIR
EMBED_CACHE_DIR = ARTIFACTS_DIR / "embed_cache"
INDEX_POINTER = INDEX_DIR / "CURRENT"
RERANK_CACHE_DIR = ARTIFACTS_DIR / "rerank_cache"
LLM_CACHE_DIR = ARTIFACTS_DIR / "llm_cache"
DIST_DIR = ARTIFACTS_DIR / "dist"

# Documentation and Reports
STATE_FILE_PATH = DOCS_DIR / "STATE.json"
DECISIONS_FILE_PATH = DOCS_DIR / "DECISIONS.md"
LEGAL_DOCS_DIR = DOCS_DIR / "legal"
LOGS_DIR = REPORTS_DIR / "logs"
CORPUS_REPORT_MD = REPORTS_DIR / "corpus_report.md"
CORPUS_REPORT_JSON = REPORTS_DIR / "corpus_report.json"
INDEX_REPORT_MD = REPORTS_DIR / "index_report.md"
INDEX_REPORT_JSON = REPORTS_DIR / "index_report.json"
EVAL_BASELINE_REPORT_MD = REPORTS_DIR / "eval_baseline.md"

# Evaluation and Benchmarking
EVAL_SET_PATH = EVALS_DIR / "eval_set.v1.jsonl"
EVAL_SET_META = EVALS_DIR / "eval_set.v1.meta.json"
RUNS_DIR = EVALS_DIR / "runs"
BASELINES_DIR = EVALS_DIR / "baselines"
THRESHOLDS_PATH = EVALS_DIR / "thresholds.yaml"
ABLATION_DIR = EVALS_DIR / "ablations"
TEST_TOUCH_LOG = EVALS_DIR / "test_touch_log.jsonl"

# Phase 5 Retrieval & Ablation artifacts
RETRIEVAL_CONFIG = CONFIG_DIR / "retrieval.yaml"
CALIBRATION_PATH = CONFIG_DIR / "calibration.json"
PROMPT_RAG_V2_PATH = ROOT / "agent" / "prompts" / "rag.v2.txt"
ABLATION_REPORT_MD = REPORTS_DIR / "ablation.md"
CLAIMS_MD = REPORTS_DIR / "claims.md"

# Phase 6 Agentic RAG Paths
AGENT_CONFIG = CONFIG_DIR / "agent.yaml"
AGENT_PROMPTS_DIR = ROOT / "agent" / "prompts"
EVENTS_SCHEMA = ROOT / "agent" / "events.schema.json"
AGENT_RUNS_DIR = RUNS_DIR
SCENARIOS_DIR = TESTS_DIR / "scenarios"
INJECTION_PATTERNS_PATH = CONFIG_DIR / "injection_patterns.yaml"
AGENT_REPORT_MD = REPORTS_DIR / "agent_report.md"
AGENT_TUNING_LOG = ABLATION_DIR / "agent_tuning_log.jsonl"

# Auto-create essential directories on import
for directory in (
    DATA_DIR,
    RAW_DATA_DIR,
    RAW_RBI_DIR,
    INTERIM_DATA_DIR,
    PARSED_DIR,
    QUARANTINE_DIR,
    PROCESSED_DATA_DIR,
    MANIFESTS_DIR,
    ARTIFACTS_DIR,
    INDEX_BASE_DIR,
    REPORTS_DIR,
    LOGS_DIR,
    DOCS_DIR,
    LEGAL_DOCS_DIR,
    EVALS_DIR,
    RUNS_DIR,
    BASELINES_DIR,
    LLM_CACHE_DIR,
    ABLATION_DIR,
    RERANK_CACHE_DIR,
    AGENT_PROMPTS_DIR,
    SCENARIOS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
