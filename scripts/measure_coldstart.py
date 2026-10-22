"""Measure and report cold-start latencies across deployment targets.

Outputs reports/coldstart.md.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "reports" / "coldstart.md"


def measure_target(url: str) -> dict:
    base = url.rstrip("/")
    start = time.perf_counter()

    ttfb = 0.0
    ready_time = 0.0
    first_answer_time = 0.0

    with httpx.Client(base_url=base, timeout=120.0) as client:
        # Measure health TTFB
        t0 = time.perf_counter()
        try:
            r = client.get("/health")
            ttfb = time.perf_counter() - t0
        except Exception:
            ttfb = -1.0

        # Measure /ready time
        t1 = time.perf_counter()
        try:
            r = client.get("/ready")
            ready_time = time.perf_counter() - t1
        except Exception:
            ready_time = -1.0

        # Measure /ask first answer latency
        t2 = time.perf_counter()
        try:
            r = client.post("/ask", json={"question": "What is the capital adequacy ratio?"})
            first_answer_time = time.perf_counter() - t2
        except Exception:
            first_answer_time = -1.0

    return {
        "url": url,
        "ttfb_seconds": round(ttfb, 3),
        "ready_seconds": round(ready_time, 3),
        "first_answer_seconds": round(first_answer_time, 3),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    res = measure_target(args.url)

    md = [
        "# RegulatorIQ Cold-Start Latency Report",
        "",
        f"**Target Tested:** `{res['url']}`  ",
        f"**Measured At:** `{res['measured_at']}`  ",
        "",
        "| Metric | Measured Duration | Free Host Expectations |",
        "| :--- | :--- | :--- |",
        f"| **Time-to-First-Byte (TTFB)** | **{res['ttfb_seconds']}s** | < 1.0s (warm), 15-30s (cold) |",
        f"| **Time-to-Ready (/ready)** | **{res['ready_seconds']}s** | < 0.5s (warm), 20-45s (cold index load) |",
        f"| **First Answer Stream Latency** | **{res['first_answer_seconds']}s** | < 2.0s (warm inference) |",
        "",
        "## Implications for Keep-Warm Schedule",
        "",
        "- For scale-to-zero providers (Cloud Run, Render Free), 10 pings/day warms instances during peak business hours (07:00 - 22:00 IST).",
        "- For persistent Always-Free VMs (Oracle Ampere, AWS EC2), memory-mapped indices avoid disk re-reads and maintain sub-second TTFB continuously.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Coldstart report written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
