"""Targeted tests to ensure >=85% test coverage across api/ modules."""

import asyncio
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from api.deps import verify_api_key
from api.errors import (
    PayloadTooLarge,
    RateLimitExceeded,
    ServiceUnavailable,
    api_error_handler,
    unhandled_exception_handler,
)
from api.feedback_store import FeedbackStore
from api.index_fetch import (
    compute_file_sha256,
    fetch_index_archive,
    safe_extract_archive,
)
from api.index_fetch import (
    main as index_fetch_main,
)
from api.lifespan import bootstrap_engine
from api.observability import LocalJsonlTracer, SimpleMetricsRegistry
from api.preflight import main as preflight_main
from api.preflight import run_preflight
from api.routes.warmup import execute_warmup
from api.schemas import FeedbackRequest
from api.security import (
    BodySizeLimiterMiddleware,
    SecurityHeadersMiddleware,
)
from api.settings import APISettings
from api.sse import sse_event_stream_generator
from api.state import AppState, ServiceMode, ServiceStage


def test_feedback_store_all_backends():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # 1. JSONL sink
        jsonl_path = tmp / "fb.jsonl"
        store_jsonl = FeedbackStore(sink_type="jsonl", file_path=jsonl_path)
        req = FeedbackRequest(
            request_id="12345678-1234-5678-1234-567812345678", rating="up", comment="Great"
        )
        store_jsonl.save_feedback(req, client_hash="abc")
        assert jsonl_path.exists()

        # 2. SQLite sink
        sqlite_path = tmp / "fb.db"
        store_sql = FeedbackStore(sink_type="sqlite", file_path=sqlite_path)
        store_sql.save_feedback(req, client_hash="def")
        with sqlite3.connect(str(sqlite_path)) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            assert cnt == 1

        # 3. None sink
        store_none = FeedbackStore(sink_type="none", file_path=None)
        store_none.save_feedback(req, client_hash="none")


@pytest.mark.asyncio
async def test_sse_event_stream_generator_coverage():
    async def mock_events():
        yield {"event": "status", "data": {"message": "ok"}}
        yield {"event": "grounding", "data": {"supported_ratio": 1.0}}
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "final", "data": {"answer": "done"}}

    lines = []
    async for frame in sse_event_stream_generator(
        mock_events(),
        request_id="test-req",
        mode="full",
        index_version="2.1.0",
        heartbeat_interval_s=0.1,
    ):
        lines.append(frame)

    full_output = "".join(lines)
    assert "event: meta" in full_output
    assert "event: status" in full_output
    assert "event: token" in full_output
    assert "event: final" in full_output


@pytest.mark.asyncio
async def test_error_handlers():
    scope = {"type": "http", "method": "GET", "path": "/test", "headers": []}
    req = Request(scope)
    req.state.request_id = "test-req-id"

    # APIError
    res1 = await api_error_handler(req, RateLimitExceeded(10))
    assert res1.status_code == 429
    assert json.loads(res1.body.decode())["error"] == "rate_limited"

    # PayloadTooLarge
    res2 = await api_error_handler(req, PayloadTooLarge(16384))
    assert res2.status_code == 413

    # ServiceUnavailable
    res3 = await api_error_handler(req, ServiceUnavailable("Busy", retry_after_s=5))
    assert res3.status_code == 503

    # Unhandled Exception
    res4 = await unhandled_exception_handler(req, RuntimeError("Database died"))
    assert res4.status_code == 500
    assert json.loads(res4.body.decode())["error"] == "internal_error"


def test_index_fetch_safe_extract_zip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        zip_file = tmp / "valid.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("manifest.json", '{"version": "2.1.0"}')
        dest = tmp / "extracted"
        safe_extract_archive(zip_file, dest)
        assert (dest / "manifest.json").exists()


def test_index_fetch_compute_sha():
    with tempfile.NamedTemporaryFile("w") as f:
        f.write("test content")
        f.flush()
        sha = compute_file_sha256(Path(f.name))
        assert len(sha) == 64


def test_metrics_registry_coverage():
    reg = SimpleMetricsRegistry()
    reg.record_request("/ask", 200, "full")
    reg.record_ask_latency(0.15)
    reg.record_ttft(0.05)
    reg.record_rate_limited("/ask")
    reg.record_refusal()
    reg.record_clarification()
    reg.record_llm_usage(2, 50)
    reg.record_sanitiser_hit()
    reg.record_warmup()
    reg.record_queue_wait()
    reg.record_cancelled()
    text = reg.render_prometheus_text()
    assert "regulatoriq_requests_total" in text
    assert "regulatoriq_ask_latency_seconds_sum" in text
    assert "regulatoriq_refusals_total 1" in text


def test_tracer_flushing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        tracer = LocalJsonlTracer(request_id="req-flush", log_dir=tmp)
        with tracer.span("test_span", {"question": "What is CRR?"}):
            pass
        tracer.event("custom_event", {"key": "val"})
        tracer.set_usage(1, 100)
        assert len(tracer.get_trace()) == 2
        tracer.flush()
        assert (tmp / "traces.jsonl").exists()


def test_warmup_route_execution_with_retriever():
    state = AppState()
    state.transition_to(ServiceStage.READY)
    state.agent_runner = MagicMock()

    # Mock retriever
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [{"chunk_id": "c1", "text": "hello"}]
    mock_retriever.embedder.embed_queries.return_value = [[0.1] * 384]
    mock_retriever.reranker.rerank.return_value = [("hello", 0.9)]
    state.retriever = mock_retriever

    res = execute_warmup(client_ip="127.0.0.1", state=state, limiter=None)
    assert res.ok is True
    assert res.llm_called is False
    assert "retrieve_ms" in res.timings_ms


@pytest.mark.asyncio
async def test_lifespan_bootstrap_flow():
    state = AppState()
    settings = APISettings(ENV="test", RAG_LIGHT_MODE=1, LLM_PROVIDER="rules")

    # Mock IndexStore and Retriever
    with (
        patch("api.lifespan.IndexStore") as mock_store_cls,
        patch("api.lifespan.Retriever") as mock_retriever_cls,
        patch("api.lifespan.AgentRunner") as mock_runner_cls,
    ):
        mock_store = MagicMock()
        mock_store.verify.return_value = (True, "OK")
        mock_store_cls.return_value = mock_store

        mock_retriever = MagicMock()
        mock_retriever_cls.from_config.return_value = mock_retriever

        mock_runner = MagicMock()
        mock_runner_cls.from_config.return_value = mock_runner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_index = Path(tmp_dir) / "index"
            tmp_index.mkdir(parents=True, exist_ok=True)
            (tmp_index / "manifest.json").write_text('{"version": "2.1.0"}')
            settings.INDEX_DIR = str(tmp_index)

            await bootstrap_engine(state, settings)
            assert state.current_stage in (ServiceStage.READY, ServiceStage.DEGRADED)
            assert state.mode == ServiceMode.LIGHT


def test_preflight_cli_and_bindable():
    report = run_preflight()
    assert "port_bind" in report["checks"]


def test_security_headers_https_forwarded():
    app = MagicMock()
    settings = APISettings(ENV="test", TRUSTED_PROXIES="10.0.0.1")
    middleware = SecurityHeadersMiddleware(app, settings)

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-forwarded-proto", b"https")],
            "client": ("10.0.0.1", 12345),
        }
    )

    async def call_next(r):
        from starlette.responses import Response

        return Response("ok")

    resp = asyncio.run(middleware.dispatch(req, call_next))
    assert "strict-transport-security" in resp.headers


@pytest.mark.asyncio
async def test_body_size_limiter_exceeded():
    app = MagicMock()
    middleware = BodySizeLimiterMiddleware(app, max_bytes=100)

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ask",
            "headers": [(b"content-length", b"200")],
        }
    )
    req.state.request_id = "req-too-large"

    async def call_next(r):
        from starlette.responses import Response

        return Response("ok")

    resp = await middleware.dispatch(req, call_next)
    assert resp.status_code == 413


def test_api_key_auth_verification():
    settings = APISettings(ENV="test", API_KEYS="valid_key_1,valid_key_2")
    req = Request({"type": "http", "method": "GET", "path": "/ask", "headers": []})

    # Missing key raises 401
    with pytest.raises(Exception):
        verify_api_key(req, settings=settings, x_api_key=None)

    # Invalid key raises 401
    with pytest.raises(Exception):
        verify_api_key(req, settings=settings, x_api_key="wrong_key")

    # Valid key passes
    verify_api_key(req, settings=settings, x_api_key="valid_key_1")


def test_ratelimit_get_client_ip_trusted_proxy():
    from api.ratelimit import RateLimiter

    limiter = RateLimiter(trusted_proxies={"10.0.0.1"})

    # Direct client from untrusted proxy
    req_direct = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.195")],
            "client": ("192.168.1.1", 1234),
        }
    )
    # Since 192.168.1.1 is NOT trusted, x-forwarded-for is ignored
    assert limiter.get_client_ip(req_direct) == "192.168.1.1"

    # Client behind trusted proxy 10.0.0.1
    req_trusted = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.1")],
            "client": ("10.0.0.1", 1234),
        }
    )
    assert limiter.get_client_ip(req_trusted) == "203.0.113.195"


def test_index_fetch_mock_flow():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        target = tmp / "target_index"

        # Mock download_with_resume
        with (
            patch("api.index_fetch.download_with_resume"),
            patch("api.index_fetch.safe_extract_archive") as mock_extract,
        ):

            def create_fake_manifest(archive, extract_dir):
                m_dir = extract_dir / "index"
                m_dir.mkdir(parents=True, exist_ok=True)
                (m_dir / "manifest.json").write_text('{"version": "2.1.0"}')

            mock_extract.side_effect = create_fake_manifest
            ok = fetch_index_archive(
                index_url="https://example.com/index.tar.gz",
                target_dir=target,
            )
            assert ok is True
            assert (target / "manifest.json").exists()


def test_feedback_rate_limit_rejection():
    from fastapi import HTTPException

    from api.routes.feedback import submit_feedback

    mock_limiter = MagicMock()
    mock_limiter.check_feedback_rate_limit.return_value = (False, 45)
    with pytest.raises(HTTPException) as exc_info:
        submit_feedback(
            body=FeedbackRequest(request_id="12345678-1234-5678-1234-567812345678", rating="down"),
            client_ip="1.2.3.4",
            limiter=mock_limiter,
            store=None,
        )
    assert exc_info.value.status_code == 429


def test_ready_route_with_populated_store():
    from starlette.responses import Response

    from api.routes.ready import get_ready

    st = AppState()
    mock_store = MagicMock()
    mock_store.manifest = {"version": "2.1.0", "counts": {"chunks": 5000}}
    st.index_store = mock_store
    st.transition_to(ServiceStage.READY)
    st.agent_runner = MagicMock()

    resp = Response()
    ready_data = get_ready(resp, state=st, settings=APISettings(ENV="test"))
    assert ready_data.chunk_count == 5000
    assert ready_data.index_version == "2.1.0"


def test_cli_entrypoints():
    with patch("sys.argv", ["preflight"]):
        with pytest.raises(SystemExit) as exc:
            preflight_main()
        assert exc.value.code in (0, 78)

    with (
        patch("sys.argv", ["index_fetch", "--url", "https://example.com/test.zip"]),
        patch("api.index_fetch.fetch_index_archive", return_value=True),
    ):
        with pytest.raises(SystemExit) as exc:
            index_fetch_main()
        assert exc.value.code == 0


def test_ask_route_branches():
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api.state import get_app_state
    from tests.unit.test_api_routes import MockAgentRunner

    settings = APISettings(ENV="test", API_KEYS="")
    app = create_app(settings)
    client = TestClient(app)
    st = get_app_state()

    orig_runner = st.agent_runner
    orig_limiter = st.rate_limiter
    try:
        # 1. Not ready -> 503
        st.agent_runner = None
        resp = client.post("/ask", json={"question": "test"})
        assert resp.status_code == 503

        # 2. Rate limited -> 429
        st.transition_to(ServiceStage.READY)
        st.agent_runner = MockAgentRunner()
        mock_limiter = MagicMock()
        mock_limiter.check_ask_rate_limit.return_value = (False, 30)
        st.rate_limiter = mock_limiter

        resp = client.post("/ask", json={"question": "test"})
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "30"
    finally:
        st.agent_runner = orig_runner
        st.rate_limiter = orig_limiter


def test_coverage_gap_fillers():
    from starlette.responses import Response

    from api.budget import GlobalBudgetGuard
    from api.preflight import run_preflight
    from api.routes.meta import get_metadata
    from api.routes.version import get_version

    st = AppState()
    st.index_store = None
    resp = Response()
    meta_res = get_metadata(response=resp, state=st, settings=APISettings(ENV="test"))
    assert meta_res.index_version == "none"

    ver_res = get_version(state=st, settings=APISettings(ENV="test"))
    assert ver_res.index_version == "none"

    bg = GlobalBudgetGuard(st, daily_call_limit=0)
    assert bg.percent_used == 100.0
    bg.record_llm_calls(0)

    with patch("api.preflight.get_settings") as mock_set:
        mock_set.side_effect = RuntimeError("Bad settings")
        rep = run_preflight()
        assert rep["status"] == "error"
