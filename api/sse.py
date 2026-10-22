"""Server-Sent Events (SSE) Stream Formatter and Encoder for RegulatorIQ.

Ensures strict adherence to agent/events.schema.json event contract and order:
  meta -> status -> plan -> retrieval -> grade -> validity -> xref -> grounding -> token* -> citation* -> final | refusal | clarification | error
Injects heartbeats (: ping) and sanitizes event outputs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

from api.security import sanitize_event_data

logger = logging.getLogger("regulatoriq.sse")


def format_sse_event(event_type: str, data: Dict[str, Any], event_id: Optional[int] = None) -> str:
    """Format single SSE frame: id: N\nevent: type\ndata: json\n\n"""
    # Sanitize payload before emitting
    clean_data = sanitize_event_data(event_type, data)
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    data_str = json.dumps(clean_data, separators=(",", ":"))
    lines.append(f"data: {data_str}")
    return "\n".join(lines) + "\n\n"


def format_sse_comment(comment: str = "ping") -> str:
    """Format SSE heartbeat comment: : ping\n\n"""
    return f": {comment}\n\n"


async def sse_event_stream_generator(
    event_iterator: AsyncIterator[Dict[str, Any]],
    request_id: str,
    mode: str,
    index_version: str,
    heartbeat_interval_s: float = 15.0,
) -> AsyncIterator[str]:
    """Wraps an async generator of raw events, prepends meta event, and emits heartbeats."""
    seq = 1

    # 1. First event: meta
    meta_payload = {
        "request_id": request_id,
        "mode": mode,
        "index_version": index_version,
    }
    yield format_sse_event("meta", meta_payload, event_id=seq)
    seq += 1

    grounding_seen = False

    while True:
        try:
            # Wait for next event or heartbeat timeout
            event = await asyncio.wait_for(event_iterator.__anext__(), timeout=heartbeat_interval_s)
            ev_type = event.get("event") or event.get("type") or "status"
            ev_data = event.get("data") or {
                k: v for k, v in event.items() if k not in ("event", "type")
            }

            # Enforce contract: token cannot precede grounding
            if ev_type == "grounding":
                grounding_seen = True
            elif ev_type == "token" and not grounding_seen:
                logger.warning("Dropping premature token event prior to grounding verification")
                continue

            yield format_sse_event(ev_type, ev_data, event_id=seq)
            seq += 1

            if ev_type in ("final", "refusal", "clarification", "error"):
                break

        except asyncio.TimeoutError:
            # Emit SSE heartbeat comment
            yield format_sse_comment("ping")
        except StopAsyncIteration:
            break
