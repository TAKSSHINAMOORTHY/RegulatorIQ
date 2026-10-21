"""Unit tests for RegulatoryTokenizer, DualBM25Index, and IdentifierIndex."""

import numpy as np

from retrieval.lexical import (
    DualBM25Index,
    IdentifierIndex,
    RegulatoryTokenizer,
)


def test_tokenizer_fixtures():
    tok = RegulatoryTokenizer()

    # Circular patterns
    text1 = "Refer to RBI/2025-26/90 and RBI/FMRD/2025-26/142"
    tokens1 = tok.tokenize(text1)
    assert "rbi/2025-26/90" in tokens1
    assert "rbi/fmrd/2025-26/142" in tokens1

    # Department Circular
    text2 = "In terms of DOR.MCS.REC.59/01.01.003/2025-26 issued today"
    tokens2 = tok.tokenize(text2)
    assert "dor.mcs.rec.59/01.01.003/2025-26" in tokens2

    # A.P. (DIR Series)
    text3 = "Vide A.P. (DIR Series) Circular No. 23 on remittances"
    tokens3 = tok.tokenize(text3)
    assert "ap_dir_series_circular_23" in tokens3
    assert "23" in tokens3

    # Clause reference 5.2(a)
    text4 = "As per paragraph 5.2(a) of the directions"
    tokens4 = tok.tokenize(text4)
    assert "5.2(a)" in tokens4
    assert "5.2" in tokens4
    assert "a" in tokens4

    # Currency and Percentage
    text5 = "Exposure limit is 25% or Rs. 5 crore per entity"
    tokens5 = tok.tokenize(text5)
    assert "25%" in tokens5
    assert "rs" in tokens5
    assert "5" in tokens5
    assert "crore" in tokens5

    # Protected regulatory stopwords
    text6 = "The entity shall not lend unless approved and no exception may apply without notice"
    tokens6 = tok.tokenize(text6)
    assert "shall" in tokens6
    assert "not" in tokens6
    assert "unless" in tokens6
    assert "no" in tokens6
    assert "may" in tokens6
    assert "without" in tokens6
    # "and", "the" should be filtered
    assert "and" not in tokens6


def test_tokenizer_stemming():
    tok = RegulatoryTokenizer()
    unstemmed = tok.tokenize("banking regulations applicable to borrowers", stem=False)
    stemmed = tok.tokenize("banking regulations applicable to borrowers", stem=True)

    assert "banking" in unstemmed
    assert "bank" in stemmed or "borrow" in stemmed


def test_dual_bm25_index(tmp_path):
    bm25 = DualBM25Index(k1=1.2, b=0.75)
    cids = ["c1", "c2", "c3"]
    corpus = [
        "[Circular] Digital Lending Guidelines | RBI/2024-25/10 | KYC norms and borrower consent",
        "[Master Direction] Priority Sector Lending | Targets for small and marginal farmers",
        "[Direction] Capital Adequacy Framework | Tier 1 capital requirements and CRAR 9%",
    ]
    bm25.index(cids, corpus)

    # Search without filter
    ids, scores, ranks = bm25.search("digital lending kyc", k=2)
    assert len(ids) == 2
    assert ids[0] == "c1"
    assert scores[0] > 0

    # Search with allow mask (filter out c1)
    mask = np.array([False, True, True], dtype=bool)
    ids_f, scores_f, _ = bm25.search("digital lending kyc", k=2, allow_mask=mask)
    assert "c1" not in ids_f

    # Persistence roundtrip
    bm25.save(tmp_path / "bm25")
    loaded = DualBM25Index.load(tmp_path / "bm25")
    assert loaded.chunk_ids == cids
    ids_l, _, _ = loaded.search("priority sector farmers", k=1)
    assert ids_l[0] == "c2"


def test_identifier_index(tmp_path):
    idx = IdentifierIndex()
    idx.add("RBI/2025-26/90", "chunk_101")
    idx.add("A.P. (DIR Series) Circular No. 23", "chunk_202")

    # Direct lookup
    assert idx.lookup("RBI/2025-26/90") == ["chunk_101"]
    assert idx.lookup("rbi/2025-26/90") == ["chunk_101"]
    assert idx.lookup("A.P. (DIR Series) Circular No. 23") == ["chunk_202"]

    # Persistence roundtrip with zstd
    filepath = tmp_path / "identifiers.json.zst"
    idx.save(filepath)
    loaded = IdentifierIndex.load(filepath)
    assert loaded.lookup("RBI/2025-26/90") == ["chunk_101"]
    assert loaded.lookup("ap_dir_series_circular_23") == ["chunk_202"]
    assert loaded.lookup("unknown") == []
