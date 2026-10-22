# RegulatorIQ Evaluation Set v1: Human Review Checklist (Optional)

This checklist provides an optional, non-blocking sampling of 20 questions from `eval_set.v1.jsonl` (sampled across question categories and splits) for future regulatory expert review.

| QID | Type | Split | Question | Expected Gold Answer / Behavior | Verified by Script | Expert Audit Sign-off |
|---|---|---|---|---|---|---|
| `q_exact_001` | exact_lookup | dev | Who delivered the special address titled 'Preserving Financial Stability in an Evolving World'? | Shri Sanjay Malhotra, Governor, Reserve Bank of India. | [x] | [ ] |
| `q_exact_003` | exact_lookup | dev | Who delivered the special address titled 'Growth with Responsibility: The Next Balance Sheet'? | Shri Swaminathan J, Deputy Governor, Reserve Bank of India. | [x] | [ ] |
| `q_exact_007` | exact_lookup | test | Under which sections of the Banking Regulation Act were directions issued to Puducherry Co-operative Urban Bank Ltd? | Section 35 A read with Section 56 of the Banking Regulation Act, 1949. | [x] | [ ] |
| `q_exact_009` | exact_lookup | dev | What is the maximum withdrawal amount permitted to a depositor of Puducherry Co-operative Urban Bank? | ₹5,000/- (Rupees Five Thousand only). | [x] | [ ] |
| `q_exact_010` | exact_lookup | test | What is the monetary ceiling for deposit insurance claim amount entitlement from DICGC? | ₹5,00,000/- (Rupees Five Lakh only). | [x] | [ ] |
| `q_exact_015` | exact_lookup | dev | What was the notified face value amount for the 91-Day T-Bill in the auction held on October 21, 2026? | ₹8,000 crore. | [x] | [ ] |
| `q_exact_018` | exact_lookup | test | What was the notified amount for the Overnight Variable Rate Repo auction held on October 21, 2026? | ₹50,000 crore. | [x] | [ ] |
| `q_temporal_001` | temporal | dev | On what date was Governor Sanjay Malhotra's address at the Fifth Kautilya Economic Conclave delivered? | October 03, 2026. | [x] | [ ] |
| `q_temporal_004` | temporal | dev | From what date did the supervisory directions on Puducherry Co-operative Urban Bank take effect? | Close of business on October 21, 2026. | [x] | [ ] |
| `q_temporal_009` | temporal | test | What auction conduct date was scheduled in the VRR press release dated October 21, 2026? | Thursday, October 22, 2026. | [x] | [ ] |
| `q_temporal_013` | temporal | test | What was the date of Press Release 2021-2022/1572 providing operational guidelines for VRR auctions? | January 20, 2022. | [x] | [ ] |
| `q_temporal_021` | temporal | dev | As of October 2026, does the issuance of directions to Puducherry Co-operative Urban Bank constitute cancellation of its banking license? | No, not cancellation of banking license. | [x] | [ ] |
| `q_multihop_001` | multi_hop | dev | Which press release announced the VRR auction for October 21, 2026, and what notified amount was confirmed in the subsequent auction result? | Announced Oct 19; confirmed ₹50,000 crore in Oct 21 auction result. | [x] | [ ] |
| `q_multihop_002` | multi_hop | test | Compare the notified amount of 91-Day Treasury Bills with the notified amount of the Overnight VRR auction held on October 21, 2026. | 91-Day T-Bills: ₹8,000 crore vs Overnight VRR: ₹50,000 crore. | [x] | [ ] |
| `q_multihop_005` | multi_hop | test | Which Deputy General Manager signed both the Treasury Bill cut-off results and the Overnight VRR auction results on October 21, 2026? | Ajit Prasad, Deputy General Manager (Communications). | [x] | [ ] |
| `q_paraphrase_001` | semantic_paraphrase | dev | In what manner must financial institutions handle customer grievances to gather intelligence on operational exposure? | Complaints as a valuable source of risk intelligence. | [x] | [ ] |
| `q_paraphrase_002` | semantic_paraphrase | test | What rationale explains why delegating technical infrastructure does not absolve institutional leadership of ultimate supervisory liability? | Technology may be outsourced, but not accountability. | [x] | [ ] |
| `q_paraphrase_012` | semantic_paraphrase | dev | Why does the central bank clarify that placing a cooperative entity under Section 35 A does not terminate its banking charter? | Not per se cancellation; continues operations subject to limits. | [x] | [ ] |
| `q_unans_001` | unanswerable | dev | Who won the ICC Cricket World Cup in 2023? | Refuse (out-of-scope sports). | [x] | [ ] |
| `q_unans_006` | unanswerable | test | What was the repo rate decided in the October 2018 Monetary Policy Committee meeting? | Refuse (near-miss absent from corpus). | [x] | [ ] |

## Review Guidelines
1. Verification checks have been executed by machine checks in `evals/generate.py`.
2. All answer keys are strictly contained in gold chunks.
3. Word-span overlap for semantic paraphrases is verified strictly <= 6 words.
4. Source documents are 100% official `*.rbi.org.in` publications.
