"""Integration tests for FastAPI Route Endpoints."""

import pytest
from fastapi.testclient import TestClient

from agent.events import AgentEvent
from agent.types import RagAnswer
from api.main import create_app
from api.settings import APISettings
from api.state import AppState, ServiceMode, ServiceStage, get_app_state


class MockAgentRunner:
    """Mock agent runner for route testing."""

    def run(self, question: str, **kwargs):
        return RagAnswer(
            answer="According to RBI directives, CRR is 4.50%.",
            citations=[
                {
                    "index": 1,
                    "title": "Master Direction - CRR",
                    "source_url": "https://www.rbi.org.in/crr",
                    "section": "Section 3",
                    "status": "current",
                }
            ],
            refused=False,
            retrieved=[],
            timings={"total_ms": 100.0},
            usage={"in": 10, "out": 10, "total": 20},
            provider="mock",
            model="mock_v1",
        )

    def stream(self, question: str, **kwargs):
        yield AgentEvent(seq=1, step="plan", type="status", data={"message": "Planning"})
        yield AgentEvent(seq=2, step="ground", type="grounding", data={"supported_ratio": 1.0})
        yield AgentEvent(seq=3, step="gen", type="token", data={"text": "CRR is 4.50%."})
        yield AgentEvent(
            seq=4,
            step="finalize",
            type="final",
            data={"answer": "CRR is 4.50%.", "refused": False, "citations": []},
        )


@pytest.fixture
def app_and_client():
    settings = APISettings(
        ENV="test",
        WARMUP_TOKEN="test_warmup_token_123",
        METRICS_TOKEN="test_metrics_token_456",
        API_KEYS="secret_api_key_789",
    )
    app = create_app(settings)
    client = TestClient(app)
    return app, client


def test_health_endpoint(app_and_client):
    _, client = app_and_client
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_s" in data
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_ready_endpoint_states(app_and_client):
    _, client = app_and_client
    app_state = get_app_state()

    # While starting -> 503
    app_state.transition_to(ServiceStage.LOADING_INDEX)
    app_state.agent_runner = None
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"

    # When ready -> 200
    app_state.transition_to(ServiceStage.READY)
    app_state.agent_runner = MockAgentRunner()
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_warmup_auth_and_execution(app_and_client):
    _, client = app_and_client
    app_state = get_app_state()
    app_state.transition_to(ServiceStage.READY)
    app_state.agent_runner = MockAgentRunner()

    # 1. Missing header -> 401
    resp = client.post("/warmup")
    assert resp.status_code == 401

    # 2. Wrong token -> 401
    resp = client.post("/warmup", headers={"Authorization": "Bearer wrong_token"})
    assert resp.status_code == 401

    # 3. Valid token -> 200
    resp = client.post("/warmup", headers={"Authorization": "Bearer test_warmup_token_123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["llm_called"] is False


def test_meta_endpoint(app_and_client):
    _, client = app_and_client
    resp = client.get("/meta")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=60"
    data = resp.json()
    assert data["app"] == "RegulatorIQ"
    assert "disclaimer" in data
    assert "capabilities" in data


def test_version_endpoint(app_and_client):
    _, client = app_and_client
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "0.1.0"
    assert "git_sha" in data


def test_metrics_auth(app_and_client):
    _, client = app_and_client
    # Missing / invalid token -> 404
    resp = client.get("/metrics")
    assert resp.status_code == 404

    # Valid token -> 200
    resp = client.get("/metrics", headers={"Authorization": "Bearer test_metrics_token_456"})
    assert resp.status_code == 200
    assert "regulatoriq_requests_total" in resp.text


def test_feedback_endpoint(app_and_client):
    _, client = app_and_client
    # Invalid UUID -> 422
    resp = client.post("/feedback", json={"request_id": "not-a-uuid", "rating": "up"})
    assert resp.status_code == 422

    # Valid UUID -> 204
    resp = client.post(
        "/feedback",
        json={
            "request_id": "12345678-1234-5678-1234-567812345678",
            "rating": "up",
            "comment": "My phone is 9876543210 and this helped.",
        },
    )
    assert resp.status_code == 204


def test_ask_auth_and_execution(app_and_client):
    _, client = app_and_client
    app_state = get_app_state()
    app_state.transition_to(ServiceStage.READY)
    app_state.agent_runner = MockAgentRunner()

    payload = {"question": "What is CRR?"}

    # 1. Missing API key -> 401
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 401

    # 2. JSON mode -> 200
    resp = client.post(
        "/ask",
        json=payload,
        headers={"X-API-Key": "secret_api_key_789", "Accept": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "CRR is 4.50%" in data["answer"]
    assert len(data["citations"]) > 0

    # 3. Streaming SSE mode -> 200
    resp = client.post(
        "/ask",
        json=payload,
        headers={"X-API-Key": "secret_api_key_789", "Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: meta" in resp.text
    assert "event: final" in resp.text
