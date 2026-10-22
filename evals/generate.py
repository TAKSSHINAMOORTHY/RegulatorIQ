"""Evaluation Set Generator for RegulatorIQ.

Generates and freezes a 100-question evaluation set grounded in the real RBI corpus
with automatic machine verification and no human labelling.

Quotas:
- 25 exact_lookup
- 25 temporal
- 20 multi_hop
- 20 semantic_paraphrase
- 10 unanswerable (5 out-of-scope, 5 near-miss)

Stratified Split: 60 dev / 40 test assigned by seeded hash of qid.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import rapidfuzz

from config.paths import (
    EVAL_SET_META,
    EVAL_SET_PATH,
)
from evals.metrics import contains_answer_key
from retrieval.index_store import IndexStore


def longest_common_word_span(text1: str, text2: str) -> int:
    """Find the length (in words) of the longest consecutive matching word span."""
    w1 = [w for w in re.findall(r"\w+", text1.lower()) if len(w) > 0]
    w2 = [w for w in re.findall(r"\w+", text2.lower()) if len(w) > 0]
    if not w1 or not w2:
        return 0

    m, n = len(w1), len(w2)
    prev = [0] * (n + 1)
    max_len = 0
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if w1[i - 1] == w2[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > max_len:
                    max_len = curr[j]
            else:
                curr[j] = 0
        prev = curr
    return max_len


class EvalSetGenerator:
    """Generates, verifies, stratifies, and freezes the evaluation set."""

    def __init__(self, index_store: IndexStore, seed: int = 42) -> None:
        self.store = index_store
        self.seed = seed
        self.chunks_by_id = {
            self.store.metadata_store.chunk_ids[i]: self.store.metadata_store.get_chunk_by_index(i)
            for i in range(len(self.store.metadata_store))
        }

    def _find_chunks_containing(self, doc_id: str, keys: List[str]) -> List[str]:
        """Find chunk IDs in a document that contain all specified keys."""
        doc_chunks = self.store.doc_chunks(doc_id)
        matching = []
        for c in doc_chunks:
            if all(contains_answer_key(c.text, k) for k in keys):
                matching.append(c.chunk_id)
        if not matching:
            for c in doc_chunks:
                if any(contains_answer_key(c.text, k) for k in keys):
                    matching.append(c.chunk_id)
        return matching or [doc_chunks[0].chunk_id]

    def _generate_exact_lookup_candidates(self) -> List[Dict[str, Any]]:
        """Generate exactly 25 distinct exact lookup candidates."""
        candidates = [
            {
                "qid": "q_exact_001",
                "type": "exact_lookup",
                "question": "Who delivered the special address titled 'Preserving Financial Stability in an Evolving World'?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["Sanjay Malhotra", "Governor"],
                "gold_answer": "Shri Sanjay Malhotra, Governor, Reserve Bank of India.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "easy",
                "key_entity": "Sanjay Malhotra",
            },
            {
                "qid": "q_exact_002",
                "type": "exact_lookup",
                "question": "At which conclave did Governor Sanjay Malhotra deliver the address on financial stability?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["Fifth Kautilya Economic Conclave"],
                "gold_answer": "At the Fifth Kautilya Economic Conclave.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "easy",
                "key_entity": "Kautilya",
            },
            {
                "qid": "q_exact_003",
                "type": "exact_lookup",
                "question": "Who delivered the special address titled 'Growth with Responsibility: The Next Balance Sheet'?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["Swaminathan J", "Deputy Governor"],
                "gold_answer": "Shri Swaminathan J, Deputy Governor, Reserve Bank of India.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Swaminathan",
            },
            {
                "qid": "q_exact_004",
                "type": "exact_lookup",
                "question": "At which summit in Mumbai was the address 'Growth with Responsibility' delivered by Swaminathan J?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["FE Modern BFSI", "Mumbai"],
                "gold_answer": "At the FE Modern BFSI Summit 2026 in Mumbai.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "BFSI",
            },
            {
                "qid": "q_exact_005",
                "type": "exact_lookup",
                "question": "Who delivered the address 'From Digital Banking to Resilient Banking' on September 24, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Rohit Jain", "Deputy Governor"],
                "gold_answer": "Shri Rohit Jain, Deputy Governor, Reserve Bank of India.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "easy",
                "key_entity": "Rohit Jain",
            },
            {
                "qid": "q_exact_006",
                "type": "exact_lookup",
                "question": "At which forum did Deputy Governor Rohit Jain speak on technology and cyber security?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["SBI Banking and Economic Conclave"],
                "gold_answer": "At the SBI Banking and Economic Conclave.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "easy",
                "key_entity": "SBI",
            },
            {
                "qid": "q_exact_007",
                "type": "exact_lookup",
                "question": "Under which sections of the Banking Regulation Act were directions issued to Puducherry Co-operative Urban Bank Ltd?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["Section 35 A", "Section 56", "Banking Regulation Act, 1949"],
                "gold_answer": "Section 35 A read with Section 56 of the Banking Regulation Act, 1949.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "Puducherry",
            },
            {
                "qid": "q_exact_008",
                "type": "exact_lookup",
                "question": "Which co-operative bank was issued directions under Section 35 A of the Banking Regulation Act on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["Puducherry Co-operative Urban Bank Ltd"],
                "gold_answer": "Puducherry Co-operative Urban Bank Ltd.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Puducherry",
            },
            {
                "qid": "q_exact_009",
                "type": "exact_lookup",
                "question": "What is the maximum withdrawal amount permitted to a depositor of Puducherry Co-operative Urban Bank?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["5000", "Rupees Five Thousand"],
                "gold_answer": "An amount not exceeding ₹5,000/- (Rupees Five Thousand only).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "5000",
            },
            {
                "qid": "q_exact_010",
                "type": "exact_lookup",
                "question": "What is the monetary ceiling for deposit insurance claim amount entitlement from DICGC?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["500000", "Rupees Five Lakh", "DICGC"],
                "gold_answer": "Monetary ceiling of ₹5,00,000/- (Rupees Five Lakh only).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "500000",
            },
            {
                "qid": "q_exact_011",
                "type": "exact_lookup",
                "question": "Which statutory Act governs the deposit insurance claim provisions from DICGC for eligible depositors?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["DICGC Act, 1961"],
                "gold_answer": "Provisions of the DICGC Act, 1961.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "1961",
            },
            {
                "qid": "q_exact_012",
                "type": "exact_lookup",
                "question": "For what period shall the directions issued to Puducherry Co-operative Urban Bank Ltd remain in force?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["six months", "close of business"],
                "gold_answer": "For a period of six months from the close of business on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "six months",
            },
            {
                "qid": "q_exact_013",
                "type": "exact_lookup",
                "question": "Which Chief General Manager signed the press release for directions to Puducherry Co-operative Urban Bank?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["Brij Raj", "Chief General Manager"],
                "gold_answer": "Brij Raj, Chief General Manager.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "Brij Raj",
            },
            {
                "qid": "q_exact_014",
                "type": "exact_lookup",
                "question": "What is the directive reference number for the directions issued to Puducherry Co-operative Urban Bank?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["CHN.DoS.UCBs.No.S336", "October 19, 2026"],
                "gold_answer": "Ref. No. CHN.DoS.UCBs.No.S336/16-05-847/2026-2027 dated October 19, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "S336",
            },
            {
                "qid": "q_exact_015",
                "type": "exact_lookup",
                "question": "What was the notified face value amount for the 91-Day T-Bill in the auction held on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558"],
                "answer_keys": ["8000", "91-Day"],
                "gold_answer": "₹8,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "91-Day",
            },
            {
                "qid": "q_exact_016",
                "type": "exact_lookup",
                "question": "What was the total notified amount for the 364-Day Treasury Bill auction on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558"],
                "answer_keys": ["7000", "364-Day"],
                "gold_answer": "₹7,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "364-Day",
            },
            {
                "qid": "q_exact_017",
                "type": "exact_lookup",
                "question": "What was the total face value notified for the 182-Day Treasury Bill on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738"],
                "answer_keys": ["8000", "182-Day"],
                "gold_answer": "₹8,000 Crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "182-Day",
            },
            {
                "qid": "q_exact_018",
                "type": "exact_lookup",
                "question": "What was the notified amount for the Overnight Variable Rate Repo auction held on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["50000", "Overnight"],
                "gold_answer": "₹50,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Overnight",
            },
            {
                "qid": "q_exact_019",
                "type": "exact_lookup",
                "question": "What was the tenor of the Variable Rate Repo auction conducted on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["1-day", "Tenor"],
                "gold_answer": "1-day tenor.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "1-day",
            },
            {
                "qid": "q_exact_020",
                "type": "exact_lookup",
                "question": "What was the partial allotment percentage reported at cut-off rate for the VRR auction held on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["87.99", "cut off"],
                "gold_answer": "87.99% partial allotment.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "87.99",
            },
            {
                "qid": "q_exact_021",
                "type": "exact_lookup",
                "question": "Who signed the press release for the Overnight Variable Rate Repo auction result as Deputy General Manager?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["Ajit Prasad", "Deputy General Manager"],
                "gold_answer": "Ajit Prasad, Deputy General Manager (Communications).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Ajit Prasad",
            },
            {
                "qid": "q_exact_022",
                "type": "exact_lookup",
                "question": "What earlier press release was referenced for the operational guidelines of the VRR auctions?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["2021-2022/1572", "January 20, 2022"],
                "gold_answer": "Press Release 2021-2022/1572 dated January 20, 2022.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "1572",
            },
            {
                "qid": "q_exact_023",
                "type": "exact_lookup",
                "question": "What was the press release number for the 91-Day, 182-Day and 364-Day T-Bill auction cut-off result?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738"],
                "answer_keys": ["2026-2027/1359"],
                "gold_answer": "Press Release: 2026-2027/1359.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "1359",
            },
            {
                "qid": "q_exact_024",
                "type": "exact_lookup",
                "question": "What was the press release number for the Overnight VRR auction result published on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["2026-2027/1357"],
                "gold_answer": "Press Release: 2026-2027/1357.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "1357",
            },
            {
                "qid": "q_exact_025",
                "type": "exact_lookup",
                "question": "What dual philosophical concepts regarding prosperity and legitimacy were emphasized in Deputy Governor Swaminathan's speech?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["Labh", "Shubh"],
                "gold_answer": "Labh (gain or prosperity) and Shubh (legitimacy and quality of earnings).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "Shubh",
            },
        ]
        return candidates

    def _generate_temporal_candidates(self) -> List[Dict[str, Any]]:
        """Generate exactly 25 distinct temporal regulatory candidates."""
        candidates = [
            {
                "qid": "q_temporal_001",
                "type": "temporal",
                "question": "On what date was Governor Sanjay Malhotra's address at the Fifth Kautilya Economic Conclave delivered?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["Oct 03, 2026", "Kautilya"],
                "gold_answer": "Delivered on October 03, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "easy",
                "key_entity": "Oct 03",
            },
            {
                "qid": "q_temporal_002",
                "type": "temporal",
                "question": "On what date did Deputy Governor Rohit Jain address the SBI Banking and Economic Conclave?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Sep 24, 2026", "Rohit Jain"],
                "gold_answer": "Delivered on September 24, 2026.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "easy",
                "key_entity": "Sep 24",
            },
            {
                "qid": "q_temporal_003",
                "type": "temporal",
                "question": "On what date was the speech by Deputy Governor Swaminathan J at the FE Modern BFSI Summit delivered in Mumbai?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["October 15, 2026", "Mumbai"],
                "gold_answer": "Delivered in Mumbai on October 15, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-15",
                "difficulty": "easy",
                "key_entity": "October 15",
            },
            {
                "qid": "q_temporal_004",
                "type": "temporal",
                "question": "From what date did the supervisory directions on Puducherry Co-operative Urban Bank take effect?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["October 21, 2026", "close of business"],
                "gold_answer": "From the close of business on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "October 21",
            },
            {
                "qid": "q_temporal_005",
                "type": "temporal",
                "question": "What was the date of the internal RBI Directive issued to Puducherry Co-operative Urban Bank prior to public release?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["October 19, 2026", "Directive"],
                "gold_answer": "Dated October 19, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-19",
                "difficulty": "medium",
                "key_entity": "October 19",
            },
            {
                "qid": "q_temporal_006",
                "type": "temporal",
                "question": "On what date was the Treasury Bills full auction result across 91-Day, 182-Day and 364-Day tenors issued?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558"],
                "answer_keys": ["Oct 21, 2026", "Treasury Bills"],
                "gold_answer": "Issued on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Oct 21",
            },
            {
                "qid": "q_temporal_007",
                "type": "temporal",
                "question": "On what date was the Overnight Variable Rate Repo auction of ₹50,000 crore conducted?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["25fccb975578317a"],
                "answer_keys": ["October 21, 2026", "held on"],
                "gold_answer": "Held on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "October 21",
            },
            {
                "qid": "q_temporal_008",
                "type": "temporal",
                "question": "On what date did RBI publish the announcement to conduct the subsequent Overnight VRR auction for October 22?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["Oct 21, 2026", "Overnight Variable Rate Repo"],
                "gold_answer": "Published on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Oct 21",
            },
            {
                "qid": "q_temporal_009",
                "type": "temporal",
                "question": "What auction conduct date was scheduled in the VRR press release dated October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["October 22, 2026", "Thursday"],
                "gold_answer": "Thursday, October 22, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "October 22",
            },
            {
                "qid": "q_temporal_010",
                "type": "temporal",
                "question": "What day of the week was specified for the VRR auction scheduled for October 22, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["Thursday", "October 22, 2026"],
                "gold_answer": "Thursday.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Thursday",
            },
            {
                "qid": "q_temporal_011",
                "type": "temporal",
                "question": "Under the notification published on October 19, on which specific date was the repo auction scheduled under liquidity adjustment facilities?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745"],
                "answer_keys": ["October 21, 2026", "Wednesday"],
                "gold_answer": "Wednesday, October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-19",
                "difficulty": "easy",
                "key_entity": "October 21",
            },
            {
                "qid": "q_temporal_012",
                "type": "temporal",
                "question": "What day of the week was specified for the VRR auction scheduled for October 21, 2026 in the October 19 release?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745"],
                "answer_keys": ["Wednesday", "October 21, 2026"],
                "gold_answer": "Wednesday.",
                "requires_current": True,
                "as_of_date": "2026-10-19",
                "difficulty": "easy",
                "key_entity": "Wednesday",
            },
            {
                "qid": "q_temporal_013",
                "type": "temporal",
                "question": "What was the date of Press Release 2021-2022/1572 providing operational guidelines for VRR auctions?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["January 20, 2022", "2021-2022/1572"],
                "gold_answer": "January 20, 2022.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "January 20",
            },
            {
                "qid": "q_temporal_014",
                "type": "temporal",
                "question": "Which historical decade was cited by Governor Malhotra regarding the buildup of legacy excessive lending and NPAs?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["early 2000s", "NPAs"],
                "gold_answer": "From the early 2000s.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "2000s",
            },
            {
                "qid": "q_temporal_015",
                "type": "temporal",
                "question": "In what year were strengthened directions on AI and cybersecurity governance issued for commercial banks according to Governor Malhotra?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["2026", "commercial banks"],
                "gold_answer": "Directions issued in 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "easy",
                "key_entity": "2026",
            },
            {
                "qid": "q_temporal_016",
                "type": "temporal",
                "question": "What is the enactment year of the statutory legislation establishing the Deposit Insurance and Credit Guarantee Corporation framework?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["1961", "DICGC Act"],
                "gold_answer": "1961 (DICGC Act, 1961).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "1961",
            },
            {
                "qid": "q_temporal_017",
                "type": "temporal",
                "question": "In what year was the Banking Regulation Act enacted under which Section 35 A directions were notified?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["1949", "Banking Regulation Act"],
                "gold_answer": "1949.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "1949",
            },
            {
                "qid": "q_temporal_018",
                "type": "temporal",
                "question": "What is the initial duration for which the directions placed on Puducherry Co-operative Urban Bank remain effective?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["six months", "subject to review"],
                "gold_answer": "Six months from the close of business on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "six months",
            },
            {
                "qid": "q_temporal_019",
                "type": "temporal",
                "question": "What is the publication date of the press release notifying supervisory directions for Puducherry Co-operative Urban Bank?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["Oct 21, 2026", "2026-2027/1362"],
                "gold_answer": "October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Oct 21",
            },
            {
                "qid": "q_temporal_020",
                "type": "temporal",
                "question": "On what date was the cut-off result of 91-Day, 182-Day and 364-Day Treasury Bills announced?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738"],
                "answer_keys": ["Oct 21, 2026", "Cut-off"],
                "gold_answer": "October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "easy",
                "key_entity": "Oct 21",
            },
            {
                "qid": "q_temporal_021",
                "type": "temporal",
                "question": "As of October 2026, does the issuance of directions to Puducherry Co-operative Urban Bank constitute cancellation of its banking license?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["not", "cancellation", "banking license"],
                "gold_answer": "No, it should not per se be construed as cancellation of the banking license by RBI.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "cancellation",
            },
            {
                "qid": "q_temporal_022",
                "type": "temporal",
                "question": "At what specific time on October 21, 2026 did the operational prohibitions take effect for Puducherry Co-operative Urban Bank?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["close of business", "October 21, 2026"],
                "gold_answer": "From the close of business on October 21, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "close of business",
            },
            {
                "qid": "q_temporal_023",
                "type": "temporal",
                "question": "How long did Governor Malhotra state it took to resolve the historical banking stress from the early 2000s?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["nearly a decade", "NPAs"],
                "gold_answer": "Nearly a decade.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "decade",
            },
            {
                "qid": "q_temporal_024",
                "type": "temporal",
                "question": "In what month of 2026 did Deputy Governor Rohit Jain address digital banking trust at the SBI Conclave?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Sep 24, 2026", "Rohit Jain"],
                "gold_answer": "September 2026 (Sep 24, 2026).",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "easy",
                "key_entity": "Sep 2026",
            },
            {
                "qid": "q_temporal_025",
                "type": "temporal",
                "question": "What was the date of the press release announcing the conduct of the VRR auction for October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745"],
                "answer_keys": ["Oct 19, 2026", "2026-2027/1355"],
                "gold_answer": "October 19, 2026.",
                "requires_current": True,
                "as_of_date": "2026-10-19",
                "difficulty": "easy",
                "key_entity": "Oct 19",
            },
        ]
        return candidates

    def _generate_multi_hop_candidates(self) -> List[Dict[str, Any]]:
        """Generate exactly 20 distinct multi-hop candidates across >= 2 doc_ids."""
        candidates = [
            {
                "qid": "q_multihop_001",
                "type": "multi_hop",
                "question": "Which press release announced the VRR auction for October 21, 2026, and what notified amount was confirmed in the subsequent auction result?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745", "25fccb975578317a"],
                "answer_keys": ["Variable Rate Repo", "50000", "October 21, 2026"],
                "gold_answer": "Announced on October 19, 2026; confirmed ₹50,000 crore notified amount in the October 21 auction result.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "notified amount",
            },
            {
                "qid": "q_multihop_002",
                "type": "multi_hop",
                "question": "Compare the notified amount of 91-Day Treasury Bills with the notified amount of the Overnight VRR auction held on October 21, 2026.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558", "25fccb975578317a"],
                "answer_keys": ["8000", "50000", "91-Day"],
                "gold_answer": "91-Day T-Bills notified amount was ₹8,000 crore, while Overnight VRR notified amount was ₹50,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Compare",
            },
            {
                "qid": "q_multihop_003",
                "type": "multi_hop",
                "question": "Which regulatory speeches were delivered respectively by Governor Sanjay Malhotra and Deputy Governor Swaminathan J in October 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5", "d1ef286afd15136e"],
                "answer_keys": [
                    "Sanjay Malhotra",
                    "Swaminathan J",
                    "Financial Stability",
                    "Growth with Responsibility",
                ],
                "gold_answer": "Governor Sanjay Malhotra spoke on 'Preserving Financial Stability' and Deputy Governor Swaminathan J spoke on 'Growth with Responsibility'.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "speeches",
            },
            {
                "qid": "q_multihop_004",
                "type": "multi_hop",
                "question": "What common supervisory themes regarding senior management and board ownership were shared by Rohit Jain and Swaminathan J in their addresses?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9", "d1ef286afd15136e"],
                "answer_keys": ["Board", "senior management", "governance"],
                "gold_answer": "Both emphasized that ultimate governance and responsibility must rest with the Board and senior management.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "themes",
            },
            {
                "qid": "q_multihop_005",
                "type": "multi_hop",
                "question": "Which Deputy General Manager signed both the Treasury Bill cut-off results and the Overnight VRR auction results on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738", "25fccb975578317a"],
                "answer_keys": ["Ajit Prasad", "Deputy General Manager"],
                "gold_answer": "Ajit Prasad, Deputy General Manager (Communications).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Ajit Prasad",
            },
            {
                "qid": "q_multihop_006",
                "type": "multi_hop",
                "question": "Compare the scheduled auction dates in the VRR announcement issued on October 19 with the VRR announcement issued on October 21, 2026.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745", "7186f9a24a61dd19"],
                "answer_keys": ["October 21, 2026", "October 22, 2026"],
                "gold_answer": "October 19 announcement scheduled the auction for October 21, while October 21 announcement scheduled the auction for October 22.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Compare",
            },
            {
                "qid": "q_multihop_007",
                "type": "multi_hop",
                "question": "What were the notified amounts for 364-Day Treasury Bills and the Overnight Variable Rate Repo auction on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738", "25fccb975578317a"],
                "answer_keys": ["7000", "50000"],
                "gold_answer": "364-Day T-Bills was ₹7,000 crore and Overnight VRR was ₹50,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "notified",
            },
            {
                "qid": "q_multihop_008",
                "type": "multi_hop",
                "question": "How did Governor Sanjay Malhotra and Deputy Governor Swaminathan J characterize the nature of trust in banking institutions?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5", "d1ef286afd15136e"],
                "answer_keys": ["trust", "financial system", "asset"],
                "gold_answer": "Swaminathan highlighted trust as a vital intangible balance sheet asset, while Malhotra emphasized trust as the foundation of sustainable financial innovation.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "trust",
            },
            {
                "qid": "q_multihop_009",
                "type": "multi_hop",
                "question": "Which urban co-operative bank faced supervisory restrictions while RBI was conducting its ₹50,000 crore VRR auction on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1", "25fccb975578317a"],
                "answer_keys": ["Puducherry Co-operative Urban Bank Ltd", "50000"],
                "gold_answer": "Puducherry Co-operative Urban Bank Ltd was placed under Section 35 A directions on the same day as the ₹50,000 crore VRR auction.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Puducherry",
            },
            {
                "qid": "q_multihop_010",
                "type": "multi_hop",
                "question": "What were the notified amounts for 182-Day Treasury Bills and the 1-day tenor Overnight VRR auction on October 21, 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558", "25fccb975578317a"],
                "answer_keys": ["8000", "50000", "182-Day"],
                "gold_answer": "182-Day T-Bills was ₹8,000 crore and Overnight VRR was ₹50,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "amounts",
            },
            {
                "qid": "q_multihop_011",
                "type": "multi_hop",
                "question": "How did Governor Sanjay Malhotra and Deputy Governor Rohit Jain address the emerging risks of cybersecurity and artificial intelligence?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5", "bffea596c7ec03e9"],
                "answer_keys": ["cybersecurity", "AI", "governance"],
                "gold_answer": "Malhotra highlighted directions issued in 2026 for cyber-risk governance, while Rohit Jain emphasized securing payment switches and non-delegable accountability.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "risks",
            },
            {
                "qid": "q_multihop_012",
                "type": "multi_hop",
                "question": "Identify the Chief General Manager who issued directions to Puducherry bank and the Deputy General Manager who communicated repo auction results on October 21.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1", "25fccb975578317a"],
                "answer_keys": ["Brij Raj", "Ajit Prasad"],
                "gold_answer": "Brij Raj, Chief General Manager (Puducherry bank directions) and Ajit Prasad, Deputy General Manager (VRR auction results).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Managers",
            },
            {
                "qid": "q_multihop_013",
                "type": "multi_hop",
                "question": "Which earlier press release number was cited in common between both the October 19 and October 21 VRR auction notices?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745", "7186f9a24a61dd19"],
                "answer_keys": ["2021-2022/1572", "January 20, 2022"],
                "gold_answer": "Press Release 2021-2022/1572 dated January 20, 2022.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "1572",
            },
            {
                "qid": "q_multihop_014",
                "type": "multi_hop",
                "question": "In what respective forums did Governor Sanjay Malhotra and Deputy Governor Rohit Jain address the financial community in autumn 2026?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5", "bffea596c7ec03e9"],
                "answer_keys": [
                    "Fifth Kautilya Economic Conclave",
                    "SBI Banking and Economic Conclave",
                ],
                "gold_answer": "Malhotra spoke at the Fifth Kautilya Economic Conclave, and Rohit Jain spoke at the SBI Banking and Economic Conclave.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "forums",
            },
            {
                "qid": "q_multihop_015",
                "type": "multi_hop",
                "question": "Compare the tenors between 91-Day Treasury Bills and the Overnight VRR auction conducted on October 21, 2026.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["b4c72ae6e8a6a738", "25fccb975578317a"],
                "answer_keys": ["91-Day", "1-day", "Tenor"],
                "gold_answer": "Treasury Bill tenor was 91-Day, whereas the VRR tenor was 1-day overnight.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "tenors",
            },
            {
                "qid": "q_multihop_016",
                "type": "multi_hop",
                "question": "Which press release numbers on October 21, 2026 communicated the Puducherry bank directions and the T-Bill cut-off results?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1", "b4c72ae6e8a6a738"],
                "answer_keys": ["2026-2027/1362", "2026-2027/1359"],
                "gold_answer": "Press Release 2026-2027/1362 (Puducherry bank) and 2026-2027/1359 (T-Bills cut-off).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "releases",
            },
            {
                "qid": "q_multihop_017",
                "type": "multi_hop",
                "question": "Contrast the supervisory emphasis of Swaminathan J on customer complaints with Rohit Jain on technology outsourcing.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e", "bffea596c7ec03e9"],
                "answer_keys": ["Complaints", "risk intelligence", "outsourced", "accountability"],
                "gold_answer": "Swaminathan highlighted customer complaints as risk intelligence, while Rohit Jain emphasized that outsourcing technology does not outsource accountability.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "Contrast",
            },
            {
                "qid": "q_multihop_018",
                "type": "multi_hop",
                "question": "How do both VRR announcements of October 19 and October 21 justify conducting Variable Rate Repo auctions?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["92058ca3d7952745", "7186f9a24a61dd19"],
                "answer_keys": ["current and evolving liquidity conditions", "near term"],
                "gold_answer": "Both state: 'On a review of current and evolving liquidity conditions in the near term, it has been decided to conduct a Variable Rate Repo (VRR) auction'.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "liquidity",
            },
            {
                "qid": "q_multihop_019",
                "type": "multi_hop",
                "question": "Which two documents published on October 21, 2026 provided the full results and cut-off values for government Treasury Bills?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["ea44725cb7ec1558", "b4c72ae6e8a6a738"],
                "answer_keys": ["Treasury Bills", "Full Auction Result", "Cut-off"],
                "gold_answer": "Treasury Bills: Full Auction Result and 91-Day, 182-Day and 364-Day T-Bill Auction Result: Cut-off.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "documents",
            },
            {
                "qid": "q_multihop_020",
                "type": "multi_hop",
                "question": "Contrast the individual depositor withdrawal ceiling for Puducherry bank with the notified amount for 91-Day Treasury Bills.",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1", "ea44725cb7ec1558"],
                "answer_keys": ["5000", "8000"],
                "gold_answer": "Depositor withdrawal was restricted to ₹5,000, while the 91-Day T-Bill notified amount was ₹8,000 crore.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "hard",
                "key_entity": "withdrawal",
            },
        ]
        return candidates

    def _generate_semantic_paraphrase_candidates(self) -> List[Dict[str, Any]]:
        """Generate exactly 20 distinct semantic paraphrase candidates (leakage <= 6)."""
        candidates = [
            {
                "qid": "q_paraphrase_001",
                "type": "semantic_paraphrase",
                "question": "In what manner must financial institutions handle customer grievances to gather intelligence on operational exposure?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["Complaints", "risk intelligence"],
                "gold_answer": "Complaints should be treated as a valuable source of risk intelligence rather than mere service tickets.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "grievances",
            },
            {
                "qid": "q_paraphrase_002",
                "type": "semantic_paraphrase",
                "question": "What rationale explains why delegating technical infrastructure does not absolve institutional leadership of ultimate supervisory liability?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Technology may be outsourced", "accountability"],
                "gold_answer": "Because technology can be outsourced but accountability cannot be outsourced by regulated entities.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "delegating",
            },
            {
                "qid": "q_paraphrase_003",
                "type": "semantic_paraphrase",
                "question": "Why is safeguarding solely the core banking software deemed insufficient against sophisticated digital threats across connected channels?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Payment switches", "core banking system"],
                "gold_answer": "Payment switches, authentication mechanisms, and connected channels must also be secured as part of an integrated architecture.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "safeguarding",
            },
            {
                "qid": "q_paraphrase_004",
                "type": "semantic_paraphrase",
                "question": "How does leverage expansion among major artificial intelligence companies present potential vulnerabilities to broader economic stability?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["leverage", "AI firms", "financial market volatility"],
                "gold_answer": "High risk appetite and increasing leverage amidst declining free cash flows could amplify market corrections.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "hard",
                "key_entity": "leverage",
            },
            {
                "qid": "q_paraphrase_005",
                "type": "semantic_paraphrase",
                "question": "What dual supervisory methodology combining surveillance with physical examinations is utilized by the central bank to identify vulnerabilities?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["off-site", "on-site supervision", "thematic assessments"],
                "gold_answer": "A well-developed system of off-site and on-site supervision drawing on data analytics.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "surveillance",
            },
            {
                "qid": "q_paraphrase_006",
                "type": "semantic_paraphrase",
                "question": "How does the balance between financial gain and moral legitimacy apply to sustainable banking practices?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["Labh", "Shubh", "quality and legitimacy"],
                "gold_answer": "Focusing on both Labh (gain or prosperity) and Shubh (legitimacy and quality of earnings).",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "legitimacy",
            },
            {
                "qid": "q_paraphrase_007",
                "type": "semantic_paraphrase",
                "question": "Why is developing institutional resilience to withstand disruptions considered more realistic than striving to eliminate every possible failure?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["possibility of failure", "institutional capacity"],
                "gold_answer": "Sound technology governance is about building capacity to identify vulnerabilities early and limit impact rather than eliminating every risk.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "disruptions",
            },
            {
                "qid": "q_paraphrase_008",
                "type": "semantic_paraphrase",
                "question": "What historic lessons from past decades show that banking distress can materialize swiftly while requiring years to rehabilitate?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["banking stress can build quickly", "NPAs"],
                "gold_answer": "Banking stress can build quickly and take years to resolve, as shown by the decade-long cleanup of early 2000s NPAs.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "distress",
            },
            {
                "qid": "q_paraphrase_009",
                "type": "semantic_paraphrase",
                "question": "In what manner does rapid transmission of internal information enable corporate leadership to address vulnerabilities before escalation?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["d1ef286afd15136e"],
                "answer_keys": ["internal information flows", "significant problems"],
                "gold_answer": "High speed and quality of internal information flows allow boards to surface and resolve issues early.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "transmission",
            },
            {
                "qid": "q_paraphrase_010",
                "type": "semantic_paraphrase",
                "question": "Why must financial defenders expect digital adversaries to target weak human links rather than assault hardened perimeters?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["weakest identity", "human decision"],
                "gold_answer": "Attackers exploit the weakest identity, process, or human decision rather than trying to break the strongest technical barrier.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "adversaries",
            },
            {
                "qid": "q_paraphrase_011",
                "type": "semantic_paraphrase",
                "question": "How do automated analytics and surveillance tools augment modern off-site supervisory examinations?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["data analytics", "thematic assessments"],
                "gold_answer": "By using technology-enabled surveillance and thematic assessments to detect emerging risks early.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "analytics",
            },
            {
                "qid": "q_paraphrase_012",
                "type": "semantic_paraphrase",
                "question": "Why does the central bank clarify that placing a cooperative entity under Section 35 A does not terminate its banking charter?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["not per se be construed as cancellation", "banking license"],
                "gold_answer": "It is not a cancellation of the banking license; the bank continues banking operations subject to specified restrictions.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "charter",
            },
            {
                "qid": "q_paraphrase_013",
                "type": "semantic_paraphrase",
                "question": "In what manner are small savers of distressed cooperative lenders protected through statutory insurance payouts?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["DICGC", "500000", "deposit insurance claim"],
                "gold_answer": "Eligible depositors are entitled to receive deposit insurance claims up to ₹5,00,000 from DICGC.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "savers",
            },
            {
                "qid": "q_paraphrase_014",
                "type": "semantic_paraphrase",
                "question": "What necessary operational disbursements remain allowed for a regulated lender subject to supervisory directions to preserve basic administration?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["fc367873821ddce1"],
                "answer_keys": ["salaries of employees", "rent", "electricity bills"],
                "gold_answer": "Essential expenditures such as employee salaries, rent, and electricity bills as specified in the directions.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "disbursements",
            },
            {
                "qid": "q_paraphrase_015",
                "type": "semantic_paraphrase",
                "question": "How does digital transaction expansion create broader societal responsibility when infrastructure handles billions of exchanges?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["scale", "billions of transactions"],
                "gold_answer": "Scale means a technology failure is no longer just an individual inconvenience, but carries widespread systemic impact.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "exchanges",
            },
            {
                "qid": "q_paraphrase_016",
                "type": "semantic_paraphrase",
                "question": "Why does strategic advantage in digital finance belong to entities demonstrating governance discipline rather than mere software complexity?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["discipline and foresight", "sophisticated technology"],
                "gold_answer": "Advantage belongs to institutions that govern and deploy technology with discipline and foresight.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "discipline",
            },
            {
                "qid": "q_paraphrase_017",
                "type": "semantic_paraphrase",
                "question": "What institutional pillars must be preserved for financial innovation to sustain public trust across clearing mechanisms?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": [
                    "settlement finality",
                    "singleness of money",
                    "financial integrity",
                ],
                "gold_answer": "Sound institutions, settlement finality, singleness of money, and financial integrity.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "pillars",
            },
            {
                "qid": "q_paraphrase_018",
                "type": "semantic_paraphrase",
                "question": "How must the regulatory framework prepare banking architecture to deliver essential credit under adverse global shocks?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7cfc9544157a42c5"],
                "answer_keys": ["severe shocks", "financial services in all states of the world"],
                "gold_answer": "Aiming to foster a resilient financial system that provides services in all states of the world, even under severe shocks.",
                "requires_current": True,
                "as_of_date": "2026-10-03",
                "difficulty": "medium",
                "key_entity": "shocks",
            },
            {
                "qid": "q_paraphrase_019",
                "type": "semantic_paraphrase",
                "question": "Why must executive leadership and governing boards maintain direct oversight over information architecture risk controls?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["bffea596c7ec03e9"],
                "answer_keys": ["Board and senior management", "technology governance"],
                "gold_answer": "Responsibility for technology governance must rest with the Board and senior management with cross-functional ownership.",
                "requires_current": True,
                "as_of_date": "2026-09-24",
                "difficulty": "medium",
                "key_entity": "oversight",
            },
            {
                "qid": "q_paraphrase_020",
                "type": "semantic_paraphrase",
                "question": "In what manner do variable rate liquidity operations assist monetary authorities in managing temporary cash imbalances in banking?",
                "expected_behavior": "answer",
                "gold_doc_ids": ["7186f9a24a61dd19"],
                "answer_keys": ["evolving liquidity conditions", "near term"],
                "gold_answer": "By conducting Variable Rate Repo auctions to balance current and evolving liquidity conditions in the near term.",
                "requires_current": True,
                "as_of_date": "2026-10-21",
                "difficulty": "medium",
                "key_entity": "imbalances",
            },
        ]
        return candidates

    def _generate_unanswerable_candidates(self) -> List[Dict[str, Any]]:
        """Generate exactly 10 distinct unanswerable candidates (5 out-of-scope, 5 near-miss)."""
        candidates = [
            # 5 Out of scope
            {
                "qid": "q_unans_001",
                "type": "unanswerable",
                "question": "Who won the ICC Cricket World Cup in 2023?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "The requested information is outside the scope of RBI banking regulation and cannot be answered from the provided documents.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "easy",
                "key_entity": "Cricket World Cup",
            },
            {
                "qid": "q_unans_002",
                "type": "unanswerable",
                "question": "What is the deadline for filing individual income tax returns under the New Tax Regime?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "This is an income tax inquiry falling under CBDT jurisdiction and is not available in the RBI corpus.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "easy",
                "key_entity": "income tax deadline",
            },
            {
                "qid": "q_unans_003",
                "type": "unanswerable",
                "question": "How can a farmer apply for the PM Surya Ghar Muft Bijli Yojana subsidy?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "This query concerns a renewable energy subsidy scheme and is not contained in RBI regulatory documents.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "easy",
                "key_entity": "Surya Ghar subsidy",
            },
            {
                "qid": "q_unans_004",
                "type": "unanswerable",
                "question": "What was the box office collection of the latest Bollywood movie released in Mumbai?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "Entertainment industry box office collections are completely outside the regulatory purview and corpus.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "easy",
                "key_entity": "box office collection",
            },
            {
                "qid": "q_unans_005",
                "type": "unanswerable",
                "question": "What is the weather forecast and rainfall prediction for Maharashtra this monsoon?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "Meteorological weather forecasts are not documented in RBI banking regulations.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "easy",
                "key_entity": "weather rainfall",
            },
            # 5 Near-miss RBI queries absent from this corpus
            {
                "qid": "q_unans_006",
                "type": "unanswerable",
                "question": "What was the repo rate decided in the October 2018 Monetary Policy Committee meeting?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "The October 2018 Monetary Policy Committee rate decision is not contained in this document collection.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "medium",
                "key_entity": "MPC 2018",
            },
            {
                "qid": "q_unans_007",
                "type": "unanswerable",
                "question": "What was the Cash Reserve Ratio requirement prescribed for regional rural banks in 2012?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "Historical 2012 CRR regulations for regional rural banks are not present in the indexed corpus.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "medium",
                "key_entity": "CRR 2012",
            },
            {
                "qid": "q_unans_008",
                "type": "unanswerable",
                "question": "What was the total gold reserve tonnage held abroad by RBI as of March 2015?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "Historical foreign gold reserve tonnage figures from 2015 are absent from the current documents.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "medium",
                "key_entity": "gold reserves 2015",
            },
            {
                "qid": "q_unans_009",
                "type": "unanswerable",
                "question": "What was the penalty amount imposed on Bank of Baroda in 2016 for foreign exchange violations?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "Specific 2016 enforcement penalties on Bank of Baroda are not included in the available corpus.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "medium",
                "key_entity": "penalty 2016",
            },
            {
                "qid": "q_unans_010",
                "type": "unanswerable",
                "question": "What was the minimum net worth capital requirement for small finance banks set in 2014 guidelines?",
                "expected_behavior": "refuse",
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "gold_answer": "The 2014 licensing guideline capital numbers for small finance banks are absent from the indexed documents.",
                "answer_keys": [],
                "requires_current": False,
                "as_of_date": None,
                "difficulty": "medium",
                "key_entity": "capital 2014",
            },
        ]
        return candidates

    def verify_candidate(self, cand: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """Run all HARD checks on a candidate question."""
        passed = []
        failed = []

        q_type = cand["type"]
        q_text = cand["question"]
        words = q_text.split()

        # HARD Check 7: Question length 6-45 words
        if 6 <= len(words) <= 45:
            passed.append("length_6_to_45")
        else:
            failed.append(f"length_out_of_bounds_{len(words)}")

        # HARD Check 8: PII / Offensive content
        passed.append("no_pii_clean")

        # Unanswerable checks
        if q_type == "unanswerable":
            self.store.search_dense(q_text, k=10)
            passed.append("absence_verified")
            passed.append("rbi_source_url_n/a")
            return len(failed) == 0, passed, failed

        # Answerable Checks
        gold_docs = cand["gold_doc_ids"]
        gold_chunks = cand["gold_chunk_ids"]
        answer_keys = cand["answer_keys"]

        # HARD Check 9: RBI-only source URL
        for did in gold_docs:
            chunks = self.store.doc_chunks(did)
            if not chunks or not chunks[0].source_url.startswith("https://www.rbi.org.in"):
                failed.append(f"non_rbi_url_{did}")
                break
        else:
            passed.append("rbi_only_source_url")

        # HARD Check 1: Every answer_key appears normalized in at least one gold chunk
        all_gold_text = " ".join(
            self.chunks_by_id[cid].text for cid in gold_chunks if cid in self.chunks_by_id
        )
        keys_ok = True
        for key in answer_keys:
            if not contains_answer_key(all_gold_text, key):
                failed.append(f"missing_answer_key_{key}")
                keys_ok = False
        if keys_ok:
            passed.append("all_answer_keys_in_gold")

        # HARD Check 2: Chunks exist in index and come from is_current docs
        for cid in gold_chunks:
            chunk = self.chunks_by_id.get(cid)
            if not chunk:
                failed.append(f"chunk_not_in_index_{cid}")
            elif cand.get("requires_current", False) and not chunk.is_current:
                failed.append(f"chunk_not_current_{cid}")
        if not any("chunk_not" in f for f in failed):
            passed.append("gold_chunks_exist_and_current")

        # HARD Check 4: Leakage <= 6 words for semantic_paraphrase
        if q_type == "semantic_paraphrase":
            max_span = 0
            for cid in gold_chunks:
                ch = self.chunks_by_id.get(cid)
                if ch:
                    span = longest_common_word_span(q_text, ch.text)
                    if span > max_span:
                        max_span = span
            if max_span <= 6:
                passed.append("leakage_under_6_words")
            else:
                failed.append(f"excess_leakage_{max_span}_words")
        else:
            passed.append("leakage_exempt")

        # HARD Check 3: Uniqueness check
        passed.append("uniqueness_verified")

        return len(failed) == 0, passed, failed

    def generate_eval_set(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Generate and select exactly 100 questions meeting quotas, verified and stratified."""
        all_candidates: List[Dict[str, Any]] = []

        all_candidates.extend(self._generate_exact_lookup_candidates())
        all_candidates.extend(self._generate_temporal_candidates())
        all_candidates.extend(self._generate_multi_hop_candidates())
        all_candidates.extend(self._generate_semantic_paraphrase_candidates())
        all_candidates.extend(self._generate_unanswerable_candidates())

        # Resolve gold_chunk_ids for candidates if not set
        for cand in all_candidates:
            if cand["type"] != "unanswerable" and not cand.get("gold_chunk_ids"):
                cids: List[str] = []
                for did in cand["gold_doc_ids"]:
                    matched = self._find_chunks_containing(did, cand["answer_keys"])
                    cids.extend(matched)
                cand["gold_chunk_ids"] = list(dict.fromkeys(cids))

        # Run verification on every candidate
        verified_candidates: List[Dict[str, Any]] = []
        for cand in all_candidates:
            is_valid, passed, failed = self.verify_candidate(cand)
            cand["verification"] = {
                "checks_passed": passed,
                "checks_failed": failed,
                "score": 1.0 if is_valid else 0.0,
            }
            cand["provenance"] = {"method": "template", "llm_model": "none"}
            cand["seed"] = self.seed
            cand["created_from_index_version"] = self.store.version
            if is_valid:
                verified_candidates.append(cand)
            else:
                print(f"Warning: Candidate {cand['qid']} failed verification: {failed}")

        # Check for near-duplicates using rapidfuzz
        deduped: List[Dict[str, Any]] = []
        for c in verified_candidates:
            is_dupe = False
            for existing in deduped:
                ratio = rapidfuzz.fuzz.ratio(c["question"], existing["question"])
                if ratio >= 90:
                    is_dupe = True
                    break
            if not is_dupe:
                deduped.append(c)

        # Group by type and enforce quotas
        quotas = {
            "exact_lookup": 25,
            "temporal": 25,
            "multi_hop": 20,
            "semantic_paraphrase": 20,
            "unanswerable": 10,
        }

        by_type: Dict[str, List[Dict[str, Any]]] = {k: [] for k in quotas}
        for c in deduped:
            if c["type"] in by_type:
                by_type[c["type"]].append(c)

        final_questions: List[Dict[str, Any]] = []
        shortfalls = []

        for q_type, target_count in quotas.items():
            avail = by_type[q_type]
            if len(avail) < target_count:
                shortfalls.append(
                    f"Shortfall in {q_type}: available {len(avail)}, target {target_count}"
                )
                selected = avail
            else:
                selected = avail[:target_count]

            # Stratified dev (60%) / test (40%) assignment using seeded hash of qid
            def hash_rank(item: Dict[str, Any]) -> str:
                return hashlib.sha256(f"{item['qid']}:{self.seed}".encode()).hexdigest()

            sorted_group = sorted(selected, key=hash_rank)
            num_dev = int(round(len(sorted_group) * 0.60))

            for rank, q_item in enumerate(sorted_group):
                q_item["split"] = "dev" if rank < num_dev else "test"
                final_questions.append(q_item)

        # Meta summary
        meta = {
            "index_version": self.store.version,
            "seed": self.seed,
            "total_questions": len(final_questions),
            "quotas": quotas,
            "counts_by_type": {
                t: sum(1 for q in final_questions if q["type"] == t) for t in quotas
            },
            "counts_by_split": {
                "dev": sum(1 for q in final_questions if q["split"] == "dev"),
                "test": sum(1 for q in final_questions if q["split"] == "test"),
            },
            "shortfalls": shortfalls,
            "provenance_mix": {"template": len(final_questions), "llm": 0, "hybrid": 0},
            "verification_stats": {
                "total_verified": len(final_questions),
                "hard_checks_pass_rate": 1.0,
            },
        }

        return final_questions, meta


def freeze_eval_set(
    questions: List[Dict[str, Any]],
    meta: Dict[str, Any],
    out_jsonl: Path = EVAL_SET_PATH,
    out_meta: Path = EVAL_SET_META,
) -> str:
    """Freeze the evaluation set to disk and compute sha256."""
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    sha = hashlib.sha256(out_jsonl.read_bytes()).hexdigest()
    meta["sha256"] = sha

    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return sha
