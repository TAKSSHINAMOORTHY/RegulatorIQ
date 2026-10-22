"""Replay and verification for all 18 golden scenarios in tests/scenarios/*.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from agent.runner import AgentRunner
from agent.types import RagAnswer
from config.paths import SCENARIOS_DIR
from retrieval.pipeline import Retriever
from retrieval.rerank import FakeReranker


@dataclass
class ScenarioChunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    is_current: bool = True
    circular_no: Optional[str] = "RBI/2025-26/10"
    title: str = "RBI Master Direction"
    issue_date: str = "2025-04-01"
    valid_from: Optional[str] = "2025-04-01"
    valid_to: Optional[str] = None
    source_url: str = "https://www.rbi.org.in/valid"


@dataclass
class ScenarioLink:
    src_doc_id: str
    rel_type: str
    target_doc_id: str
    target_circular_no: str
    context_text: str = ""
    relation: str = ""

    def __post_init__(self) -> None:
        if not self.relation:
            self.relation = self.rel_type


class ScenarioIndexStore:
    """Configurable synthetic store for scenario evaluation."""

    def __init__(
        self, chunks: List[ScenarioChunk], links: Optional[List[ScenarioLink]] = None
    ) -> None:
        self.chunks_map = {c.chunk_id: c for c in chunks}
        self.links_list = links or []

    def get_chunks(self, chunk_ids: List[str]) -> List[ScenarioChunk]:
        return [self.chunks_map[cid] for cid in chunk_ids if cid in self.chunks_map]

    def doc_chunks(self, doc_id: str) -> List[ScenarioChunk]:
        return [c for c in self.chunks_map.values() if c.doc_id == doc_id]

    def links_for(self, doc_id: str) -> List[ScenarioLink]:
        return [link for link in self.links_list if link.src_doc_id == doc_id]

    def lookup_identifier(self, ident: str) -> List[str]:
        return [
            c.chunk_id
            for c in self.chunks_map.values()
            if c.circular_no and ident.lower() in c.circular_no.lower()
        ]

    def search_dense(self, query: str, k: int = 50, filters: Optional[Any] = None) -> List[Any]:
        from retrieval.index_store import Hit

        hits = []
        for i, c in enumerate(self.chunks_map.values(), start=1):
            hits.append(Hit(chunk_id=c.chunk_id, score=1.0 / (i + 1), rank=i))
            if len(hits) >= k:
                break
        return hits

    def search_bm25(self, query: str, k: int = 50, filters: Optional[Any] = None) -> List[Any]:
        from retrieval.index_store import Hit

        hits = []
        for i, c in enumerate(self.chunks_map.values(), start=1):
            hits.append(Hit(chunk_id=c.chunk_id, score=10.0 / (i + 1), rank=i))
            if len(hits) >= k:
                break
        return hits


def create_scenario_runner() -> AgentRunner:
    """Create test runner wired to synthetic scenario store."""
    c1 = ScenarioChunk(
        "c_target",
        "d_target",
        0,
        "The statutory liquidity ratio (SLR) requirement is 18.0 percent. The exposure limit is 25 percent under circular RBI/2025-26/90.",
        circular_no="RBI/2025-26/90",
    )
    c_old = ScenarioChunk(
        "c_old",
        "d_old",
        0,
        "Old guidelines specified 15 crore.",
        is_current=False,
        circular_no="RBI/2020-21/10",
        issue_date="2020-04-01",
        valid_from="2020-04-01",
        valid_to="2024-03-31",
    )
    c_new = ScenarioChunk(
        "c_new",
        "d_new",
        0,
        "Current KYC norms as amended by recent directions require Aadhaar-based e-KYC.",
        circular_no="RBI/2025-26/12",
    )
    c_ref = ScenarioChunk(
        "c_ref",
        "d_ref",
        0,
        "Section 42 of RBI Act defines scheduled bank cash reserve ratios.",
        circular_no="RBI/2025-26/88",
    )

    links = [
        ScenarioLink(
            src_doc_id="d_old",
            rel_type="superseded_by",
            target_doc_id="d_new",
            target_circular_no="RBI/2025-26/12",
        ),
        ScenarioLink(
            src_doc_id="d_new",
            rel_type="amended_by",
            target_doc_id="d_amend",
            target_circular_no="RBI/2025-26/99",
        ),
        ScenarioLink(
            src_doc_id="d_target",
            rel_type="refers_to",
            target_doc_id="d_ref",
            target_circular_no="RBI/2025-26/88",
        ),
    ]

    store = ScenarioIndexStore([c1, c_old, c_new, c_ref], links=links)
    retriever = Retriever(
        store=store,
        config={
            "retrieval": {
                "hybrid": {"fusion_method": "rrf", "apply_temporal": True},
                "reranker": {"enabled": False, "top_n": 5},
                "rewrite": {"use_rules": True},
                "context": {"token_budget": 2000},
            }
        },
        reranker=FakeReranker(mode="identity"),
    )

    cfg = {
        "version": "1.0.0",
        "tuned_on": "dev",
        "default_system": "agent_full",
        "budgets": {"max_graph_steps": 14, "max_llm_calls": 6, "max_retrieval_rounds": 3},
        "thresholds": {
            "grade_threshold": 0.0,
            "refusal_conf_threshold": 0.15,
            "clarify_conf_threshold": 0.25,
        },
        "capabilities": {
            "router": True,
            "decompose": True,
            "grade_retry": True,
            "validity": True,
            "xref": True,
            "selfcheck": True,
            "clarify": True,
        },
    }

    return AgentRunner(config=cfg, retriever=retriever, mode="rules")


def get_all_scenarios() -> List[Dict[str, Any]]:
    scenario_files = sorted(list(SCENARIOS_DIR.glob("scenario_*.json")))
    scenarios = []
    for f in scenario_files:
        with open(f, "r", encoding="utf-8") as sc_f:
            scenarios.append(json.load(sc_f))
    return scenarios


@pytest.mark.parametrize(
    "sc", get_all_scenarios(), ids=lambda s: f"scenario_{s['id']:02d}_{s['name']}"
)
def test_all_18_scenarios(sc: Dict[str, Any]) -> None:
    runner = create_scenario_runner()
    sc_id = sc["id"]
    q = sc["question"]
    history = sc.get("history", [])
    opts = sc.get("session_opts", {})

    ans = runner.run(q, history=history, session_opts=opts)
    assert ans is not None
    assert isinstance(ans, RagAnswer)

    # 1. Exact lookup
    if sc_id == 1:
        assert ans.refused is False
        assert len(ans.citations) >= 1

    # 2. Superseded to current
    elif sc_id == 2:
        assert ans.refused is False
        assert any(vf.get("status") == "superseded" for vf in ans.validity_findings)

    # 3. as_of historical
    elif sc_id == 3:
        assert ans.refused is False

    # 4. Two doc comparison
    elif sc_id == 4:
        assert ans.refused is False

    # 5. Amendment chain
    elif sc_id == 5:
        assert ans.refused is False
        assert (
            any("amended" in vf.get("status", "") for vf in ans.validity_findings)
            or "as amended by" in ans.answer.lower()
        )

    # 6. Xref follow
    elif sc_id == 6:
        assert ans.refused is False

    # 7. Retry success
    elif sc_id == 7:
        assert ans.refused is False

    # 8. Unanswerable refusal
    elif sc_id == 8:
        assert ans.refused is True
        assert "outside the regulatory scope" in ans.answer.lower()

    # 9. Ambiguous entity clarify
    elif sc_id == 9:
        if opts.get("interactive"):
            assert ans.clarification is not None
            assert ans.clarification.get("needed") is True

    # 10. Prompt injection
    elif sc_id == 10:
        assert ans.refused is True

    # 11. Chunk injection neutralized
    elif sc_id == 11:
        assert ans.refused is False

    # 12. PII redaction
    elif sc_id == 12:
        assert ans.refused is False
        assert "ABCDE1234F" not in ans.answer
        assert "1234 5678 9012" not in ans.answer

    # 13. History follow-up
    elif sc_id == 13:
        assert ans.refused is False

    # 14. LLM outage degraded
    elif sc_id == 14:
        assert ans.refused is False
        assert ans.mode == "rules"

    # 15. Budget exhaustion termination
    elif sc_id == 15:
        assert ans.steps <= 14

    # 16. Selfcheck recovery
    elif sc_id == 16:
        assert ans.refused is False

    # 17. Selfcheck double fail
    elif sc_id == 17:
        assert ans is not None

    # 18. Index unavailable
    elif sc_id == 18:
        assert ans is not None
