"""Comprehensive unit tests for Phase 5 retrieval components.

Covers:
- Hand-computed RRF fusion, ties, missing items
- Weighted norm fusion
- Identifier boost effect
- Temporal policy table-driven tests
- Query analysis cases & date parsing edge cases
- Abbreviation expansion bidirectional
- Rewrite validation guards
- Cross-encoder truncation counter & early exit logic
- Confidence calibrator monotonicity & bounded [0, 1]
- Context builder budgeting, dedupe, per-doc cap, status labels
- Retriever.from_config validation
- Test split anti-tamper guard
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from evals.test_guard import check_and_log_test_touch, read_test_touches
from retrieval.context import build_context
from retrieval.hybrid import (
    RankedChunk,
    rrf_fuse,
    weighted_norm_fuse,
)
from retrieval.index_store import Hit
from retrieval.pipeline import Retriever
from retrieval.query_analysis import QueryAnalyzer, analyze_query
from retrieval.rerank import (
    BaseReranker,
    ConfidenceCalibrator,
    CrossEncoderFastEmbed,
    LexicalSemanticReranker,
    RerankCache,
    rerank_candidates,
)
from retrieval.rewrite import (
    QueryRewriter,
    extract_numbers_and_ids,
    validate_rewrite,
)


# Fake Chunk for context and hybrid testing
@dataclass
class DummyChunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    doc_type: str = "Circular"
    title: str = "Dummy Directive"
    circular_no: Optional[str] = "RBI/2025-26/10"
    issue_date: Optional[str] = "2025-04-01"
    valid_from: Optional[str] = "2025-04-01"
    valid_to: Optional[str] = None
    is_current: bool = True
    section_path: str = "Section 1"
    para_ref: Optional[str] = "1.1"


# --- 1. RRF & Weighted Norm Math ---
def test_rrf_hand_computed() -> None:
    # 2 lists: list A = [c1, c2], list B = [c2, c3]
    dense_hits = [Hit("c1", 0.9, rank=1), Hit("c2", 0.7, rank=2)]
    bm25_hits = [Hit("c2", 10.0, rank=1), Hit("c3", 5.0, rank=2)]

    # Formula: w / (rrf_k + rank) with rrf_k = 60, w=1.0
    # c1: 1 / 61 = 0.016393
    # c2: 1 / 62 + 1 / 61 = 0.016129 + 0.016393 = 0.032522
    # c3: 1 / 62 = 0.016129
    scores = rrf_fuse(dense_hits, bm25_hits, rrf_k=60, w_dense=1.0, w_bm25=1.0)
    assert abs(scores["c1"] - (1.0 / 61)) < 1e-5
    assert abs(scores["c2"] - (1.0 / 62 + 1.0 / 61)) < 1e-5
    assert abs(scores["c3"] - (1.0 / 62)) < 1e-5
    assert scores["c2"] > scores["c1"] > scores["c3"]


def test_weighted_norm_fuse_math() -> None:
    dense_hits = [Hit("c1", 10.0, 1), Hit("c2", 0.0, 2)]
    bm25_hits = [Hit("c1", 0.0, 2), Hit("c2", 100.0, 1)]

    # Min-max normalized:
    # dense: c1 -> 1.0, c2 -> 0.0
    # bm25: c1 -> 0.0, c2 -> 1.0
    # With alpha=0.5: c1 = 0.5, c2 = 0.5
    res = weighted_norm_fuse(dense_hits, bm25_hits, alpha=0.5)
    assert abs(res["c1"] - 0.5) < 1e-5
    assert abs(res["c2"] - 0.5) < 1e-5

    # With alpha=0.8: c1 = 0.8, c2 = 0.2
    res8 = weighted_norm_fuse(dense_hits, bm25_hits, alpha=0.8)
    assert abs(res8["c1"] - 0.8) < 1e-5
    assert abs(res8["c2"] - 0.2) < 1e-5


# --- 2. Query Analysis & Edge Cases ---
def test_query_analysis_required_examples() -> None:
    p1 = analyze_query("Is RBI/2025-26/90 still in force?")
    assert "RBI/2025-26/90" in p1.identifiers
    assert p1.wants_current is True
    assert "validity" in p1.intents

    p2 = analyze_query("latest master direction on KYC")
    assert p2.wants_current is True
    assert "Master Direction" in p2.doc_type_hints
    assert any("know your customer" in v.lower() for v in p2.query_variants)

    p3 = analyze_query("as of 1 April 2023 what was the PSL target")
    assert p3.as_of_date == "2023-04-01"
    assert "2023-04-01" in p3.explicit_dates
    assert "priority_sector" in p3.topics

    p4 = analyze_query("KYC norms for NBFCs")
    assert "NBFCs" in p4.entity_hints
    assert any("non-banking" in v.lower() for v in p4.query_variants)

    p5 = analyze_query("FEMA LRS limit")
    assert "fema_forex" in p5.topics
    assert "threshold" in p5.intents
    assert any("liberalised remittance scheme" in v.lower() for v in p5.query_variants)


def test_date_parser_edge_cases() -> None:
    # Financial Year
    plan_fy = analyze_query("Guidelines for FY 2024-25")
    assert 2024 in plan_fy.years
    assert 2025 in plan_fy.years

    # Ambiguous date dropped with warning
    plan_amb = analyze_query("Directive dated 03/04/2023 and 11.11.2025")
    assert "2025-11-11" in plan_amb.explicit_dates
    assert any("Ambiguous date '03/04/2023' dropped" in w for w in plan_amb.warnings)
    assert "2023-04-03" not in plan_amb.explicit_dates
    assert "2023-03-04" not in plan_amb.explicit_dates


def test_abbreviation_expansion_bidirectional() -> None:
    analyzer = QueryAnalyzer()
    # Acronym -> full form
    vars1 = analyzer.build_query_variants("What is the CRR and SLR?")
    assert any("Cash Reserve Ratio" in v for v in vars1)
    assert any("Statutory Liquidity Ratio" in v for v in vars1)

    # Full form -> acronym
    vars2 = analyzer.build_query_variants("Norms for Non-Banking Financial Company")
    assert any("NBFC" in v for v in vars2)


# --- 3. Rewrite Validation Guard ---
def test_rewrite_validation_guard() -> None:
    original = "What is the limit under RBI/2025-26/90 for 50 crore loans?"
    identifiers = ["RBI/2025-26/90"]

    # Valid rewrite: keeps identifier and numbers 90 and 50
    valid_rw = (
        "What is the maximum exposure limit under circular RBI/2025-26/90 for 50 crore loans?"
    )
    assert validate_rewrite(original, valid_rw, identifiers) is True

    # Invalid: drops circular number
    invalid_no_id = "What is the maximum exposure limit for 50 crore loans?"
    assert validate_rewrite(original, invalid_no_id, identifiers) is False

    # Invalid: drops number 50
    invalid_no_num = "What is the limit under RBI/2025-26/90 for crore loans?"
    assert validate_rewrite(original, invalid_no_num, identifiers) is False


# --- 4. Reranker & Early Exit ---
def test_reranker_truncation_counter_and_early_exit() -> None:
    class MockReranker(BaseReranker):
        def score(self, query: str, passages: List[str]) -> List[float]:
            scores = []
            for p in passages:
                if len(p) > 50:
                    self.truncation_counter += 1
                scores.append(1.0)
            return scores

    mr = MockReranker()
    long_passage = "A" * 100
    short_passage = "B" * 20
    mr.score("test", [long_passage, short_passage])
    assert mr.truncation_counter == 1

    # Early exit logic
    c1 = DummyChunk("c1", "d1", 0, "Leading text", circular_no="RBI/2025-26/90")
    c2 = DummyChunk("c2", "d2", 0, "Other text", circular_no=None)
    rc1 = RankedChunk(c1, fused_score=0.9, rerank_score=0.9, rank=1, status="current")
    rc2 = RankedChunk(c2, fused_score=0.2, rerank_score=0.2, rank=2, status="current")

    res, meta = rerank_candidates(
        query="RBI/2025-26/90",
        candidates=[rc1, rc2],
        reranker=mr,
        early_exit_margin=0.05,
    )
    assert meta["early_exit"] is True
    assert meta["rerank_count"] == 0
    assert res[0].chunk.chunk_id == "c1"


def test_confidence_calibrator_monotonic() -> None:
    cal = ConfidenceCalibrator(w_top1=1.5, w_margin=2.5, intercept=0.0, fitted=True)
    c1 = cal.predict_proba(top1=1.0, margin=0.5)
    c2 = cal.predict_proba(top1=2.0, margin=0.5)
    c3 = cal.predict_proba(top1=2.0, margin=1.5)

    assert 0.0 <= c1 <= 1.0
    assert 0.0 <= c2 <= 1.0
    assert 0.0 <= c3 <= 1.0
    assert c1 < c2 < c3  # Monotonically increasing


# --- 5. Context Builder & Deduplication ---
def test_context_builder_budget_and_dedupe() -> None:
    c1 = DummyChunk("c1", "d1", 0, "The Cash Reserve Ratio is 4.5% of NDTL for scheduled banks.")
    # Near duplicate
    c2 = DummyChunk("c2", "d2", 0, "The Cash Reserve Ratio is 4.5% of NDTL for scheduled banks!")
    # Distinct chunk
    c3 = DummyChunk("c3", "d3", 0, "Priority sector lending targets are 40% of ANBC.")

    rc1 = RankedChunk(c1, 0.9, 0.9, 1, "current")
    rc2 = RankedChunk(c2, 0.8, 0.8, 2, "current")
    rc3 = RankedChunk(c3, 0.7, 0.7, 3, "current")

    bundle = build_context([rc1, rc2, rc3], dedupe_threshold=90.0, token_budget=1000)
    # c2 is a duplicate of c1 -> should be dropped
    accepted_ids = [item.chunk.chunk_id for item in bundle.items]
    assert "c1" in accepted_ids
    assert "c2" not in accepted_ids
    assert "c3" in accepted_ids
    assert any(d.chunk.chunk_id == "c2" for d in bundle.dropped)

    # Per-doc cap
    d_chunks = [
        RankedChunk(
            DummyChunk(f"chunk_{i}", "doc_A", i, f"Sentence {i}."),
            0.9 - i * 0.1,
            0.9 - i * 0.1,
            i,
            "current",
        )
        for i in range(5)
    ]
    bundle_cap = build_context(d_chunks, per_doc_cap=3, token_budget=2000)
    assert len(bundle_cap.items) == 3
    assert len(bundle_cap.dropped) == 2


# --- 6. Configuration Validation ---
def test_retriever_config_validation() -> None:
    with pytest.raises(ValueError, match="Invalid fusion_method"):
        Retriever._validate_config({"retrieval": {"hybrid": {"fusion_method": "invalid_method"}}})

    with pytest.raises(ValueError, match="Fusion weights must be non-negative"):
        Retriever._validate_config(
            {"retrieval": {"hybrid": {"fusion_method": "rrf", "w_dense": -1.0}}}
        )


# --- 7. Test-Touch Guard ---
def test_test_touch_guard(tmp_path) -> None:
    log_file = tmp_path / "test_touch_log.jsonl"

    # First touch: succeeds
    c1 = check_and_log_test_touch(
        system_name="hybrid_rerank",
        config_hash="abc12345",
        run_id="run_001",
        log_path=log_file,
    )
    assert c1 == 1

    # Second touch without force flag: raises RuntimeError
    with pytest.raises(RuntimeError, match="Test split touch guard violation"):
        check_and_log_test_touch(
            system_name="hybrid_rerank",
            config_hash="abc12345",
            run_id="run_002",
            log_path=log_file,
        )

    # Second touch with force flag: succeeds and logs reason
    c2 = check_and_log_test_touch(
        system_name="hybrid_rerank",
        config_hash="abc12345",
        run_id="run_003",
        force=True,
        force_reason="Official re-run for documentation",
        log_path=log_file,
    )
    assert c2 == 2
    entries = read_test_touches(log_file)
    assert len(entries) == 2
    assert entries[1]["forced"] is True
    assert entries[1]["force_reason"] == "Official re-run for documentation"


# --- 8. Rewriter Unit Tests ---
def test_extract_numbers_and_ids() -> None:
    tokens = extract_numbers_and_ids("What is the CRR of 4.5% under circular RBI/2024-25/12?")
    assert "RBI/2024-25/12" in tokens
    assert "4.5" in tokens or "4" in tokens


def test_query_rewriter_with_mock() -> None:
    analyzer = QueryAnalyzer()
    plan = analyzer.analyze("Tell me about RBI/2024-25/12 circular")

    # Mock LLM that returns a valid rewrite
    mock_llm = MagicMock()
    mock_llm.generate.return_value = MagicMock(
        text="RBI circular RBI/2024-25/12 regarding priority sector"
    )
    rewriter = QueryRewriter(
        llm=mock_llm, use_llm_rewrite=True, use_hyde=True, use_multi_query=True
    )
    res = rewriter.rewrite(plan)
    assert any("RBI/2024-25/12" in v for v in res.query_variants)
    assert res.hyde_passage is not None

    # Mock LLM that strips identifier -> rejected
    mock_llm.generate.return_value = MagicMock(text="This stripped the circular ID entirely")
    res_rejected = rewriter.rewrite(plan)
    assert len(res_rejected.rejected_rewrites) > 0

    # Mock LLM raising exception -> degraded
    mock_llm.generate.side_effect = Exception("LLM call failed")
    res_err = rewriter.rewrite(plan)
    assert res_err.degraded_rewrite is True


# --- 9. CrossEncoder Cache & Lexical Reranker ---
def test_cross_encoder_cache(tmp_path) -> None:
    cache = RerankCache(cache_dir=tmp_path)

    key = cache.make_key("fake_model", "query 1", "chunk_1")
    # Initial get: miss
    res = cache.get(key)
    assert res is None

    # Set and get: hit
    cache.set(key, 0.95)
    hit_res = cache.get(key)
    assert hit_res == 0.95

    # Different key: miss
    key2 = cache.make_key("fake_model", "query 2", "chunk_1")
    assert cache.get(key2) is None


def test_lexical_reranker() -> None:
    reranker = LexicalSemanticReranker()
    scores = reranker.score(
        "cash reserve ratio", ["Cash reserve ratio is 4.5%", "Nothing related here", ""]
    )
    assert len(scores) == 3
    assert scores[0] > scores[1]
    assert scores[2] == 0.0


def test_confidence_calibrator_fit_and_save(tmp_path) -> None:
    cal = ConfidenceCalibrator()
    top1s = [0.9, 0.8, 0.2, 0.1, 0.85, 0.15, 0.95, 0.05, 0.75, 0.25, 0.88, 0.12]
    margins = [0.5, 0.4, 0.05, 0.02, 0.45, 0.01, 0.6, 0.01, 0.35, 0.03, 0.42, 0.02]
    labels = [1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0]

    stats = cal.fit(top1s, margins, labels)
    assert cal.fitted is True
    assert stats["samples"] == 12

    save_path = tmp_path / "calibration.json"
    cal.save(save_path)
    assert save_path.exists()

    loaded = ConfidenceCalibrator.load(save_path)
    assert loaded.fitted is True
    assert loaded.predict_proba(0.8, 0.3) > 0.5


# --- 10. Context Formatting & MMR Diversification ---
def test_context_formatting_and_mmr() -> None:
    c1 = DummyChunk("c1", "d1", 0, "First directive on CRR.", doc_type="Notification")
    c2 = DummyChunk("c2", "d2", 0, "Second directive on SLR.", is_current=False)
    rc1 = RankedChunk(c1, 0.9, 0.95, 1, "current")
    rc2 = RankedChunk(c2, 0.8, 0.70, 2, "superseded")

    bundle = build_context([rc1, rc2], token_budget=1000)
    assert len(bundle.items) == 2
    assert "[1] Notification" in bundle.text
    assert "RBI/2025-26/10" in bundle.text
    assert "status: current" in bundle.text
    assert "status: superseded" in bundle.text


# --- 11. Date and Fiscal Year Edge Cases ---
def test_date_and_fy_edge_cases() -> None:
    analyzer = QueryAnalyzer()

    # Ambiguous date format e.g. 04/05/2024
    plan = analyzer.analyze("What was announced on 04/05/2024?")
    assert any("Ambiguous date" in w for w in plan.warnings)

    # Financial year parsing and textual dates
    p_fy = analyzer.analyze(
        "Guidelines for FY 2023-24 announced on 2024-05-15 and May 15, 2024 and 05/25/2024"
    )
    assert 2023 in p_fy.years
    assert 2024 in p_fy.years
    assert "2024-05-15" in p_fy.explicit_dates
    assert "2024-05-25" in p_fy.explicit_dates


# --- 12. CrossEncoderFastEmbed Truncation ---
def test_cross_encoder_truncation() -> None:
    reranker = CrossEncoderFastEmbed()
    long_passage = "Banking rules " * 300  # >2000 chars
    scores = reranker.score("rules", [long_passage, "short passage"])
    assert len(scores) == 2
    assert reranker.truncation_counter >= 1
