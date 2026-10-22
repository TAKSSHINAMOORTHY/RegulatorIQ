"""Standalone Mock API Server for RegulatorIQ Frontend Development and Testing.

Runs an independent, lightweight FastAPI server without requiring vector indices
or machine learning models. Emits scripted SSE event streams selected via
magic prompt prefixes like `[[scenario:superseded]]`.

Usage:
  python scripts/mock_api.py --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, AsyncIterator, Dict, Optional

import uvicorn
from fastapi import FastAPI, Header, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="RegulatorIQ Mock API",
    version="0.1.0-mock",
    description="Mock API server for frontend development and automated UI testing",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


class AskRequest(BaseModel):
    question: str
    history: list = Field(default_factory=list)
    options: dict = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    request_id: str
    rating: str
    reason: Optional[str] = None
    comment: Optional[str] = None


@app.get("/health")
def get_health() -> Dict[str, Any]:
    return {"status": "ok", "uptime_s": 42.0}


@app.get("/ready")
def get_ready() -> Dict[str, Any]:
    return {
        "status": "ready",
        "mode": "full",
        "index_version": "2.1.0-mock",
        "chunk_count": 4820,
        "degraded": [],
        "warmup_enabled": True,
        "version": "0.1.0-mock",
        "started_at": "2026-10-22T08:00:00Z",
    }


@app.post("/warmup")
def post_warmup() -> Dict[str, Any]:
    return {
        "ok": True,
        "mode": "full",
        "timings_ms": {"embed_ms": 1.2, "retrieve_ms": 2.4, "rerank_ms": 3.1},
        "llm_called": False,
    }


@app.get("/meta")
def get_meta() -> Dict[str, Any]:
    return {
        "app": "RegulatorIQ",
        "version": "0.1.0-mock",
        "mode": "full",
        "index_version": "2.1.0-mock",
        "corpus": {
            "documents": 312,
            "chunks": 4820,
            "as_of_crawl_date": "2026-10-22",
            "doc_types": {"master_direction": 120, "circular": 180, "notification": 12},
        },
        "capabilities": ["stream", "as_of", "include_superseded", "feedback"],
        "limits": {"max_question_chars": 1000, "max_history_turns": 4},
        "disclaimer_key": "regulatory_disclaimer",
        "disclaimer": "Unofficial tool, not affiliated with the Reserve Bank of India.",
        "degraded_notice": None,
    }


@app.get("/version")
def get_version() -> Dict[str, Any]:
    return {
        "version": "0.1.0-mock",
        "git_sha": "mocksha123",
        "index_version": "2.1.0-mock",
        "mode": "full",
        "build_time": "2026-10-22T08:00:00Z",
    }


@app.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
def post_feedback(body: FeedbackRequest) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def sse_frame(ev_type: str, data: Dict[str, Any], event_id: int) -> str:
    return f"id: {event_id}\nevent: {ev_type}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@app.post("/ask")
async def post_ask(
    req: AskRequest,
    accept: Optional[str] = Header(default="text/event-stream"),
) -> Any:
    q = req.question.strip()

    # Determine scenario from prefix
    scenario = "default"
    if q.startswith("[[scenario:") and "]]" in q:
        scenario = q.split("[[scenario:")[1].split("]]")[0]

    # Non-streaming JSON response
    if accept and "application/json" in accept and "text/event-stream" not in accept:
        if scenario == "refusal":
            return JSONResponse(
                {
                    "answer": "This query falls outside the official scope of Reserve Bank of India regulatory directives.",
                    "citations": [],
                    "refused": True,
                    "retrieved": [],
                    "timings": {"total_ms": 120.0},
                    "usage": {"in": 50, "out": 20, "total": 70},
                    "provider": "mock",
                    "model": "mock-eval",
                }
            )
        return JSONResponse(
            {
                "answer": "Under Master Direction - Know Your Customer (KYC) Direction, 2016, regulated entities must update KYC records periodically.",
                "citations": [
                    {
                        "chunk_id": "rbi_kyc_2016_c001",
                        "doc_id": "rbi_kyc_2016",
                        "title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
                        "source_url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
                        "section": "Section 4.1",
                        "published_date": "2016-02-25",
                        "status": "current",
                    }
                ],
                "refused": False,
                "retrieved": [],
                "timings": {"total_ms": 150.0},
                "usage": {"in": 120, "out": 60, "total": 180},
                "provider": "mock",
                "model": "mock-eval",
            }
        )

    # SSE Streaming response
    async def event_generator() -> AsyncIterator[str]:
        seq = 1
        yield sse_frame(
            "meta",
            {"request_id": "mock-req-1234", "mode": "full", "index_version": "2.1.0-mock"},
            seq,
        )
        seq += 1

        if scenario == "refusal":
            yield sse_frame("status", {"message": "Screening regulatory safety guardrails"}, seq)
            seq += 1
            yield sse_frame(
                "refusal",
                {
                    "reason": "out_of_scope",
                    "message": "Query falls outside official RBI regulatory framework.",
                    "guidance": "Please consult official RBI Master Directions on rbi.org.in.",
                },
                seq,
            )
            return

        if scenario == "clarification":
            yield sse_frame("status", {"message": "Resolving regulatory scope"}, seq)
            seq += 1
            yield sse_frame(
                "clarification",
                {
                    "question": "Are you asking with respect to Scheduled Commercial Banks or Non-Banking Financial Companies (NBFCs)?",
                    "options": ["Commercial Banks", "NBFCs"],
                },
                seq,
            )
            return

        if scenario == "error":
            yield sse_frame("status", {"message": "Executing regulatory search"}, seq)
            seq += 1
            yield sse_frame("error", {"message": "Upstream service timeout"}, seq)
            yield sse_frame(
                "final",
                {
                    "answer": "An error occurred during query execution.",
                    "refused": True,
                    "citations": [],
                },
                seq,
            )
            return

        # Default & Superseded Scenarios
        yield sse_frame("status", {"message": "Formulating retrieval strategy"}, seq)
        seq += 1
        yield sse_frame(
            "plan", {"steps": ["Retrieve Master Directions", "Verify temporal supersession"]}, seq
        )
        seq += 1
        yield sse_frame("retrieval", {"count": 3, "query": q}, seq)
        seq += 1
        yield sse_frame("grade", {"relevant": 3, "irrelevant": 0}, seq)
        seq += 1
        if scenario == "superseded":
            yield sse_frame(
                "validity",
                {
                    "status": "superseded",
                    "superseded_by": "RBI/2023-24/MD-01",
                    "note": "Replaced by Master Direction - Reserve Bank of India (KYC) Update, 2023",
                },
                seq,
            )
            seq += 1
        yield sse_frame("grounding", {"supported_ratio": 1.0, "calibrated_confidence": 0.96}, seq)
        seq += 1

        tokens = [
            "According ",
            "to ",
            "Master ",
            "Direction ",
            "on ",
            "KYC, ",
            "regulated ",
            "entities ",
            "must ",
            "verify ",
            "customer ",
            "identity. [1]",
        ]
        for t in tokens:
            yield sse_frame("token", {"text": t}, seq)
            seq += 1
            await asyncio.sleep(0.01)

        yield sse_frame(
            "citation",
            {
                "index": 1,
                "doc_id": "rbi_kyc_2016",
                "title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
                "source_url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
                "section": "Section 4",
                "published_date": "2016-02-25",
                "status": "current",
            },
            seq,
        )
        seq += 1

        yield sse_frame(
            "final",
            {
                "answer": "According to Master Direction on KYC, regulated entities must verify customer identity. [1]",
                "refused": False,
                "citations": [
                    {
                        "index": 1,
                        "doc_id": "rbi_kyc_2016",
                        "title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
                        "source_url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
                        "section": "Section 4",
                        "published_date": "2016-02-25",
                        "status": "current",
                    }
                ],
                "timings": {"total_ms": 150.0},
            },
            seq,
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Request-ID": "mock-req-1234",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start RegulatorIQ Mock API server")
    parser.add_argument("--port", type=int, default=8000, help="Listen port")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
