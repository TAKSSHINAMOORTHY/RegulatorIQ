"""Metrics Route for RegulatorIQ API.

GET /metrics serves Prometheus exposition text format. Protected by METRICS_TOKEN
Bearer authentication. Returns 404 when token is not configured or mismatched.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.deps import verify_metrics_token
from api.observability import metrics_registry

router = APIRouter(tags=["Operations"])


@router.get("/metrics", dependencies=[Depends(verify_metrics_token)])
def get_metrics() -> Response:
    """Return Prometheus-formatted operational metrics."""
    metrics_text = metrics_registry.render_prometheus_text()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")
