"""Helper utility to read and update docs/STATE.json."""

from __future__ import annotations

import json
from typing import Any, Dict

from config.paths import STATE_FILE_PATH


def read_state() -> Dict[str, Any]:
    """Load the current project state from docs/STATE.json."""
    if not STATE_FILE_PATH.exists():
        return {
            "project": "RegulatorIQ",
            "version": "0.1.0",
            "phases": {},
        }
    with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        return dict(data) if isinstance(data, dict) else {}


def write_state(state: Dict[str, Any]) -> None:
    """Save the state dictionary back to docs/STATE.json atomically."""
    temp_path = STATE_FILE_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    temp_path.replace(STATE_FILE_PATH)


def update_phase(phase_number: int | str, **fields: Any) -> Dict[str, Any]:
    """Update or initialize a phase in docs/STATE.json.

    Args:
        phase_number: Integer or string phase identifier (e.g. 1 or "1")
        **fields: Keyword arguments to update on the phase object
                 (e.g. status="complete", artifacts={...}, counts={...})
    """
    state = read_state()
    phase_key = str(phase_number)
    if "phases" not in state:
        state["phases"] = {}

    if phase_key not in state["phases"]:
        state["phases"][phase_key] = {
            "status": "pending",
            "completed_at": None,
            "commit": None,
            "artifacts": {},
            "counts": {},
            "notes": [],
        }

    for key, val in fields.items():
        if isinstance(val, dict) and isinstance(state["phases"][phase_key].get(key), dict):
            state["phases"][phase_key][key].update(val)
        else:
            state["phases"][phase_key][key] = val

    write_state(state)
    return state


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "read":
        print(json.dumps(read_state(), indent=2))
