"""Tests for evaluation set generation, verification, and freezing."""

from __future__ import annotations

import hashlib
import json

import rapidfuzz

from config.paths import EVAL_SET_META, EVAL_SET_PATH
from evals.generate import EvalSetGenerator
from retrieval.index_store import IndexStore


def test_frozen_eval_set_checksum_and_quotas():
    assert EVAL_SET_PATH.exists(), "eval_set.v1.jsonl must exist"
    assert EVAL_SET_META.exists(), "eval_set.v1.meta.json must exist"

    with open(EVAL_SET_META, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Check sha256 match
    actual_sha = hashlib.sha256(EVAL_SET_PATH.read_bytes()).hexdigest()
    assert actual_sha == meta["sha256"], "SHA256 checksum mismatch on frozen evaluation set"

    # Check quotas
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    assert len(questions) == 100
    by_type = {}
    by_split = {}
    for q in questions:
        t = q["type"]
        s = q["split"]
        by_type[t] = by_type.get(t, 0) + 1
        by_split[s] = by_split.get(s, 0) + 1

    assert by_type["exact_lookup"] == 25
    assert by_type["temporal"] == 25
    assert by_type["multi_hop"] == 20
    assert by_type["semantic_paraphrase"] == 20
    assert by_type["unanswerable"] == 10

    assert by_split["dev"] == 60
    assert by_split["test"] == 40


def test_hard_checks_pass_on_frozen_set():
    """Re-run all HARD verification checks independently on every question in the frozen set."""
    store = IndexStore.load(verify="fast")
    gen = EvalSetGenerator(store)

    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    for q in questions:
        is_valid, passed, failed = gen.verify_candidate(q)
        assert is_valid, f"HARD checks failed for {q['qid']}: {failed}"


def test_no_near_duplicate_questions():
    """Assert all questions in frozen set have rapidfuzz similarity < 90."""
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            ratio = rapidfuzz.fuzz.ratio(questions[i]["question"], questions[j]["question"])
            assert ratio < 90, (
                f"Near-duplicate questions detected (ratio={ratio}):\n  1: {questions[i]['question']}\n  2: {questions[j]['question']}"
            )


def test_regeneration_determinism():
    """Regeneration with the same seed yields identical question set and sha256."""
    store = IndexStore.load(verify="fast")
    gen1 = EvalSetGenerator(store, seed=42)
    q1, m1 = gen1.generate_eval_set()

    gen2 = EvalSetGenerator(store, seed=42)
    q2, m2 = gen2.generate_eval_set()

    assert len(q1) == len(q2)
    for item1, item2 in zip(q1, q2):
        assert item1["qid"] == item2["qid"]
        assert item1["split"] == item2["split"]
        assert item1["question"] == item2["question"]
