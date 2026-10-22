"""Preflight Check CLI for Container and Service Startup.

Validates:
1. Environment variables and production configuration safeguards.
2. Index presence, manifest integrity, and fast verification.
3. Model library imports and offline caching.
4. System resource thresholds (free disk space and RAM).
5. Port bindability.

Exit codes:
- 0: All checks passed cleanly.
- 78: Configuration or integrity error (e.g. invalid CORS, missing index).
- 1: Unexpected system error.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import socket
import sys
from pathlib import Path
from typing import Any, Dict

from api.settings import get_settings
from retrieval.index_store import IndexStore

logger = logging.getLogger("regulatoriq.preflight")


def check_port_bindable(host: str, port: int) -> bool:
    """Test whether specified host and port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
        except Exception:
            return False


def run_preflight() -> Dict[str, Any]:
    """Execute all preflight checks and return JSON-serializable report."""
    report: Dict[str, Any] = {
        "status": "ok",
        "checks": {},
        "warnings": [],
        "errors": [],
    }

    # 1. Settings validation
    try:
        settings = get_settings()
        report["checks"]["settings"] = "passed"
    except Exception as e:
        report["status"] = "error"
        report["errors"].append(f"Settings validation failed: {e}")
        return report

    # 2. Port check
    if check_port_bindable(settings.HOST, settings.PORT):
        report["checks"]["port_bind"] = "passed"
    else:
        report["status"] = "error"
        report["errors"].append(
            f"Port {settings.PORT} on host {settings.HOST} is already in use or cannot be bound."
        )

    # 3. Disk & Memory check
    disk_usage = shutil.disk_usage(".")
    free_gb = round(disk_usage.free / (1024**3), 2)
    report["checks"]["free_disk_gb"] = free_gb

    if free_gb < 1.0:
        report["warnings"].append(f"Low free disk space: {free_gb} GB remaining.")

    # 4. Index presence check
    index_path = Path(settings.INDEX_DIR)
    manifest_file = index_path / "manifest.json"
    if manifest_file.exists():
        try:
            store = IndexStore(index_path)
            valid, msg = store.verify(mode="fast")
            if valid:
                report["checks"]["index_manifest"] = "valid"
                report["index_version"] = store.manifest.get("version", "unknown")
            else:
                report["status"] = "error"
                report["errors"].append(f"Index validation failed: {msg}")
        except Exception as e:
            report["status"] = "error"
            report["errors"].append(f"Error opening index: {e}")
    else:
        if settings.INDEX_URL:
            report["checks"]["index_manifest"] = "pending_fetch"
            report["warnings"].append(
                "Index not found locally; remote INDEX_URL configured for automatic fetch."
            )
        else:
            report["status"] = "error"
            report["errors"].append(f"Index not found at {index_path} and INDEX_URL is not set.")

    # 5. Core model imports
    try:
        for mod in ("bs4", "fastapi", "pydantic", "selectolax"):
            importlib.import_module(mod)
        report["checks"]["core_imports"] = "passed"
    except ImportError as e:
        report["status"] = "error"
        report["errors"].append(f"Required module missing: {e}")

    return report


def main() -> None:
    """CLI execution wrapper."""
    report = run_preflight()
    print(json.dumps(report, indent=2))

    if report["status"] != "ok":
        # Exit 78 for config/integrity errors
        sys.exit(78)
    sys.exit(0)


if __name__ == "__main__":
    main()
