"""Keep-warm script for RegulatorIQ server instances.

Standard library only. Probes GET /health and executes POST /warmup.
Never calls /ask, respects a maximum 10 pings per rolling 24h cap.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENTS_FILE = ROOT / "deploy" / "deployments.json"
WARMUP_CACHE_FILE = ROOT / "data" / "warmup_history.json"
MAX_DAILY_RUNS = 10


def load_warmup_history() -> list[float]:
    if not WARMUP_CACHE_FILE.exists():
        return []
    try:
        data = json.loads(WARMUP_CACHE_FILE.read_text(encoding="utf-8"))
        return [float(ts) for ts in data if isinstance(ts, (int, float))]
    except Exception:
        return []


def save_warmup_history(timestamps: list[float]) -> None:
    WARMUP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    WARMUP_CACHE_FILE.write_text(json.dumps(timestamps), encoding="utf-8")


def check_daily_cap(now: float) -> bool:
    """Return True if under daily cap (<= 10 runs in rolling 24 hours)."""
    one_day_ago = now - 86400.0
    history = [ts for ts in load_warmup_history() if ts > one_day_ago]
    return len(history) < MAX_DAILY_RUNS


def record_warmup_run(now: float) -> None:
    one_day_ago = now - 86400.0
    history = [ts for ts in load_warmup_history() if ts > one_day_ago]
    history.append(now)
    save_warmup_history(history)


def warmup_target(url: str, token: str, max_retries: int = 4) -> bool:
    base = url.rstrip("/")
    health_url = f"{base}/health"
    warmup_url = f"{base}/warmup"

    # Step 1: Health check
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"[{url}] Health check returned non-200: {resp.status}")
    except Exception as e:
        print(f"[{url}] Health probe initial warning: {e}")

    # Step 2: Warmup with retries
    backoffs = [0, 15, 30, 45]
    for attempt in range(max_retries):
        if attempt > 0:
            delay = backoffs[attempt] if attempt < len(backoffs) else 45
            print(f"[{url}] Waiting {delay}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(delay)

        try:
            req = urllib.request.Request(
                warmup_url,
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "X-Warmup": "1",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    print(f"[{url}] Warmup succeeded (status=200, time={body.get('warmup_time_ms', 'N/A')}ms)")
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"[{url}] Warmup rejected (401 Unauthorized - verify WARMUP_TOKEN)")
                return False
            print(f"[{url}] Warmup attempt {attempt + 1} HTTPError: {e.code}")
        except Exception as e:
            print(f"[{url}] Warmup attempt {attempt + 1} error: {e}")

    return False


def main():
    parser = argparse.ArgumentParser(description="RegulatorIQ Keep-Warm Runner")
    parser.add_argument("--urls", help="Comma-separated target URLs")
    parser.add_argument("--token", default=os.environ.get("WARMUP_TOKEN", "test_warmup_token_12345"))
    parser.add_argument("--force", action="store_true", help="Ignore rolling 24h cap check")
    args = parser.parse_args()

    now = time.time()
    if not args.force and not check_daily_cap(now):
        print(f"Hard cap reached: already performed {MAX_DAILY_RUNS} keep-warm runs in the past 24 hours. Aborting.")
        sys.exit(0)

    urls = []
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif os.environ.get("WARMUP_URLS"):
        urls = [u.strip() for u in os.environ["WARMUP_URLS"].split(",") if u.strip()]
    elif DEPLOYMENTS_FILE.exists():
        try:
            data = json.loads(DEPLOYMENTS_FILE.read_text(encoding="utf-8"))
            urls = [d["url"] for d in data if isinstance(d, dict) and d.get("url")]
        except Exception:
            urls = []

    if not urls:
        urls = ["http://localhost:8000"]

    print("=" * 60)
    print(f"RegulatorIQ Keep-Warm Execution: {datetime.now(timezone.utc).isoformat()}")
    print(f"Targets ({len(urls)}): {', '.join(urls)}")
    print("=" * 60)

    results = {}
    for target in urls:
        ok = warmup_target(target, args.token)
        results[target] = ok

    record_warmup_run(now)

    print("\nWarmup Summary:")
    for tgt, ok in results.items():
        print(f"  {tgt:30s} -> {'SUCCESS' if ok else 'FAILED'}")

    # Exit non-zero only if ALL targets fail
    if not any(results.values()):
        print("\nAll keep-warm targets failed.")
        sys.exit(1)
    else:
        print("\nKeep-warm run completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
