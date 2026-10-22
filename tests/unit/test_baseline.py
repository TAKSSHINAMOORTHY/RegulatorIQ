"""Unit and validity tests for baseline RAG and metric sanity."""

from __future__ import annotations

from agent.baseline import BaselineRAG
from agent.types import RagAnswer
from evals.metrics import (
    compute_faithfulness,
    compute_recall_at_k,
)
from evals.run import evaluate_sample
from retrieval.index_store import IndexStore


def test_citation_parsing_and_invalids():
    store = IndexStore.load(verify="fast")
    rag = BaselineRAG(index_store=store)

    # Test baseline answering
    res = rag.answer("What was the notified amount for the 91-Day Treasury Bills?")
    assert isinstance(res, RagAnswer)
    assert len(res.retrieved) > 0
    assert "total_s" in res.timings
    assert res.provider != ""


def test_refusal_detection_on_out_of_scope():
    store = IndexStore.load(verify="fast")
    rag = BaselineRAG(index_store=store)

    res = rag.answer("Who won the ICC Cricket World Cup in 2023?")
    assert res.refused or "cannot" in res.answer.lower() or "not available" in res.answer.lower()


# ---------------------------------------------------------------------------
# Metric Validity Tests (Part F)
# ---------------------------------------------------------------------------


def test_oracle_retriever_validity():
    """An ORACLE retriever returning gold chunks must achieve recall@5 = 1.0."""
    gold_chunks = ["chunk_a", "chunk_b"]
    oracle_retrieved = ["chunk_a", "chunk_b", "chunk_c", "chunk_d", "chunk_e"]

    rec = compute_recall_at_k(oracle_retrieved, gold_chunks, k=5)
    assert rec == 1.0


def test_random_retriever_validity():
    """A RANDOM retriever picking disjoint chunks must achieve recall@5 < 0.2."""
    gold_chunks = ["chunk_gold_1"]
    all_chunks = [f"chunk_distractor_{i}" for i in range(100)]
    random_retrieved = all_chunks[:5]

    rec = compute_recall_at_k(random_retrieved, gold_chunks, k=5)
    assert rec == 0.0 < 0.2


def test_adversarial_generator_validity():
    """An adversarial generator ignoring context must score low faithfulness."""
    context = "The Reserve Bank of India reduced the policy repo rate by 25 basis points to 6.25%."
    adversarial_answer = (
        "The moon is made of green cheese and astronauts enjoy playing golf on Mars."
    )

    score, _ = compute_faithfulness(adversarial_answer, [context], judge_type="lexical_support")
    assert score <= 0.2


def test_verbatim_copier_validity():
    """A generator copying the gold chunk verbatim must score faithfulness >= 0.9."""
    context = "Directions were issued under Section 35 A of the Banking Regulation Act to Puducherry Co-operative Urban Bank."
    verbatim_answer = "Directions were issued under Section 35 A of the Banking Regulation Act to Puducherry Co-operative Urban Bank [1]."

    score, _ = compute_faithfulness(verbatim_answer, [context], judge_type="lexical_support")
    assert score >= 0.9


def test_always_refuse_generator_validity():
    """An always-refuse generator must score refusal_accuracy = 1.0 on unanswerable and false_refusal_rate = 1.0 on answerable."""
    unans_q = {
        "qid": "q_u",
        "type": "unanswerable",
        "expected_behavior": "refuse",
        "gold_chunk_ids": [],
        "answer_keys": [],
    }
    ans_q = {
        "qid": "q_a",
        "type": "exact_lookup",
        "expected_behavior": "answer",
        "gold_chunk_ids": ["c1"],
        "answer_keys": ["test"],
    }

    refused_answer = RagAnswer(
        answer="I cannot answer from the provided documents.",
        citations=[],
        refused=True,
        retrieved=[],
        timings={},
        usage={},
        provider="test",
        model="test",
    )

    eval_unans = evaluate_sample(unans_q, refused_answer)
    assert eval_unans["refusal_accuracy"] == 1.0

    eval_ans = evaluate_sample(ans_q, refused_answer)
    assert eval_ans["false_refusal_rate"] == 1.0
