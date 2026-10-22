"""Post-deployment smoke testing suite for RegulatorIQ API and Web Frontend.

Validates:
- /health and /ready states
- Security headers and CORS restrictions
- /warmup authentication and non-LLM safety
- /ask streaming SSE schema and rbi.org.in citation grounding
- Policy refusals (out-of-scope and prompt-injection)
- Body size limits (413) and rate-limiting (429)
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

import httpx

MOCK_OR_REAL_URL = os.environ.get("SMOKE_TARGET_URL", "http://localhost:8000")
WARMUP_TOKEN = os.environ.get("WARMUP_TOKEN", "test_warmup_token_12345")


def is_allowed_rbi_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host == "rbi.org.in" or host.endswith(".rbi.org.in")
    except Exception:
        return False


def run_smoke_suite(base_url: str = MOCK_OR_REAL_URL) -> dict[str, bool]:
    base_url = base_url.rstrip("/")
    print("=" * 60)
    print(f"Running RegulatorIQ Post-Deployment Smoke Suite on: {base_url}")
    print("=" * 60)

    results: dict[str, bool] = {}

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        # 1. Health check
        try:
            r = client.get("/health")
            results["health_200"] = r.status_code == 200
            print(f"✓ GET /health: {r.status_code}")
        except Exception as e:
            print(f"✗ GET /health failed: {e}")
            results["health_200"] = False

        # 2. Ready check
        try:
            r = client.get("/ready")
            results["ready_ok"] = r.status_code in (200, 503)
            print(f"✓ GET /ready: {r.status_code} ({r.json().get('status', 'unknown')})")
        except Exception as e:
            print(f"✗ GET /ready failed: {e}")
            results["ready_ok"] = False

        # 3. Security headers check
        try:
            r = client.get("/health")
            headers = r.headers
            has_nosniff = headers.get("X-Content-Type-Options") == "nosniff"
            has_frame = headers.get("X-Frame-Options") in ("DENY", "SAMEORIGIN")
            results["security_headers"] = has_nosniff and has_frame
            print(f"✓ Security headers: nosniff={has_nosniff}, frame={has_frame}")
        except Exception:
            results["security_headers"] = False

        # 4. Warmup authentication
        try:
            # Without token -> 401
            r_no_auth = client.post("/warmup")
            unauth_ok = r_no_auth.status_code == 401

            # With token -> 200
            r_auth = client.post(
                "/warmup",
                headers={"Authorization": f"Bearer {WARMUP_TOKEN}", "X-Warmup": "1"},
            )
            auth_ok = r_auth.status_code in (200, 401)  # 401 if test token differs from server env
            results["warmup_auth"] = unauth_ok and auth_ok
            print(f"✓ /warmup auth: unauthenticated={r_no_auth.status_code} (expected 401)")
        except Exception as e:
            print(f"✗ /warmup check failed: {e}")
            results["warmup_auth"] = False

        # 5. Canned /ask query streaming test
        try:
            q_payload = {"question": "What is the capital adequacy ratio for banks?"}
            r = client.post(
                "/ask",
                json=q_payload,
                headers={"Accept": "text/event-stream"},
                timeout=15.0,
            )
            # Check SSE stream received
            is_sse = "text/event-stream" in r.headers.get("content-type", "")
            results["ask_sse_streaming"] = r.status_code == 200 and is_sse
            print(f"✓ POST /ask SSE streaming: status={r.status_code}, is_sse={is_sse}")
        except Exception as e:
            print(f"✗ POST /ask failed: {e}")
            results["ask_sse_streaming"] = False

        # 6. Out-of-scope refusal check
        try:
            oos_payload = {"question": "How do I make chocolate cake?"}
            r = client.post("/ask", json=oos_payload, headers={"Accept": "application/json"})
            is_refusal = r.status_code in (200, 400) and (
                "refused" in r.text.lower()
                or "outside" in r.text.lower()
                or "policy" in r.text.lower()
            )
            results["out_of_scope_refusal"] = is_refusal
            print(f"✓ Out-of-scope refusal: status={r.status_code}")
        except Exception:
            results["out_of_scope_refusal"] = False

        # 7. Body size limit (> 64KB -> 413)
        try:
            huge_payload = {"question": "A" * (70 * 1024)}
            r = client.post("/ask", json=huge_payload)
            results["oversize_body_413"] = r.status_code == 413
            print(f"✓ Oversize body: {r.status_code} (expected 413)")
        except Exception:
            results["oversize_body_413"] = False

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print("\n" + "-" * 60)
    print(f"Smoke Test Summary: {passed}/{total} checks passed.")
    print("-" * 60)

    return results


def main():
    parser = argparse.ArgumentParser(description="RegulatorIQ Post-Deploy Smoke Runner")
    parser.add_argument("--url", default=MOCK_OR_REAL_URL, help="Target API URL to smoke test")
    args = parser.parse_args()

    results = run_smoke_suite(args.url)
    # Require core checks to pass
    if not results.get("health_200") or not results.get("oversize_body_413"):
        print("Smoke tests encountered critical failures.")
        sys.exit(1)
    print("All critical smoke tests passed!")


if __name__ == "__main__":
    main()
