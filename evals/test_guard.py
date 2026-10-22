"""Test split discipline and anti-tamper guard.

Tracks every access to the test evaluation split in TEST_TOUCH_LOG.
Enforces that each system may only be run against the test split ONCE,
requiring --force-test-touch with an explicit reason for any subsequent run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.paths import TEST_TOUCH_LOG


def read_test_touches(log_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read all entries from test touch log."""
    path = log_path or TEST_TOUCH_LOG
    if not path.exists():
        return []
    touches = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    touches.append(json.loads(line))
                except Exception:
                    pass
    return touches


def check_and_log_test_touch(
    system_name: str,
    config_hash: str,
    run_id: str,
    purpose: str = "ablation",
    force: bool = False,
    force_reason: str = "",
    log_path: Optional[Path] = None,
) -> int:
    """Check test split touch constraint and record access.

    Returns the total touch count for this system (e.g. 1 for first run, 2 for second).
    Raises RuntimeError if system has already run on the test split and force is False.
    """
    path = log_path or TEST_TOUCH_LOG
    path.parent.mkdir(parents=True, exist_ok=True)

    past_touches = read_test_touches(path)
    system_past_touches = [t for t in past_touches if t.get("system") == system_name]
    touch_count = len(system_past_touches)

    if touch_count >= 1 and not force:
        raise RuntimeError(
            f"Test split touch guard violation: System '{system_name}' has already run on the test split "
            f"({touch_count} previous touches recorded in {path.name}). "
            f"A second run requires --force-test-touch with a documented reason."
        )

    # Record this touch
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": system_name,
        "config_hash": config_hash,
        "run_id": run_id,
        "purpose": purpose,
        "touch_index": touch_count + 1,
        "forced": bool(touch_count >= 1),
        "force_reason": force_reason if touch_count >= 1 else "",
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return touch_count + 1
