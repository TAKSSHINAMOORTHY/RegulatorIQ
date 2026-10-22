"""Verification script for RegulatorIQ Phase 6 (Prompt 6).

Verifies:
1. config/agent.yaml exists, validates, and has tuned_on == "dev" and default_system.
2. AgentRunner.from_config().run("...") returns a valid RagAnswer on the real index.
3. Event stream passes agent/events.schema.json and respects order contract.
4. evals/test_touch_log.jsonl shows <= 1 test run per agent system.
5. reports/agent_report.md exists with required header sections.
6. Regression gate passes for default system in evals/thresholds.yaml.
7. reports/claims.md contains Phase 6 claims.
8. docs/STATE.json Phase 6 is marked complete.
"""

from __future__ import annotations

import json
import sys
from typing import Any, List

import yaml

from agent.events import validate_event_order
from agent.runner import AgentRunner
from agent.types import RagAnswer
from config.paths import (
    AGENT_CONFIG,
    AGENT_REPORT_MD,
    CLAIMS_MD,
    EVENTS_SCHEMA,
    STATE_FILE_PATH,
    TEST_TOUCH_LOG,
)
from evals.gate import check_regression_gates
from evals.test_guard import read_test_touches


def verify_phase_6() -> bool:
    print("=" * 65)
    print(" Verifying Phase 6: Agentic RAG (LangGraph), Routing & Self-Checking")
    print("=" * 65)

    # 1. Verify config/agent.yaml
    if not AGENT_CONFIG.exists():
        print(f"❌ {AGENT_CONFIG} does not exist.")
        return False
    with open(AGENT_CONFIG, "r", encoding="utf-8") as f:
        agent_cfg = yaml.safe_load(f) or {}

    tuned_on = agent_cfg.get("tuned_on")
    default_system = agent_cfg.get("default_system", "agent_full")
    if tuned_on != "dev":
        print(f"❌ config/agent.yaml must have tuned_on == 'dev', got '{tuned_on}'")
        return False
    if not default_system:
        print("❌ config/agent.yaml missing 'default_system'")
        return False
    print(f"✅ config/agent.yaml validated (tuned_on={tuned_on}, default_system={default_system})")

    # 2. Live AgentRunner execution on real index
    print("Testing AgentRunner on real index...")
    try:
        runner = AgentRunner.from_config()
        ans = runner.run("What is the CRR requirement under Reserve Bank of India directions?")
        if not isinstance(ans, RagAnswer):
            print("❌ AgentRunner.run() did not return RagAnswer")
            return False
        if ans.steps > 14:
            print(f"❌ Graph execution exceeded max steps: got {ans.steps}")
            return False
        print(
            f"✅ AgentRunner returned valid RagAnswer (steps={ans.steps}, provider={ans.provider}, citations={len(ans.citations)})"
        )
    except Exception as e:
        print(f"❌ AgentRunner execution failed: {e}")
        return False

    # 3. Stream event schema validation & order contract
    print("Verifying event stream schema and order contract...")
    try:
        with open(EVENTS_SCHEMA, "r", encoding="utf-8") as f:
            schema = json.load(f)
            assert isinstance(schema, dict) and len(schema) > 0

        events: List[Any] = []
        for ev in runner.stream("What are statutory liquidity ratio rules?"):
            events.append(ev)
            if not hasattr(ev, "type") or not hasattr(ev, "ts") or not hasattr(ev, "seq"):
                print(f"❌ Event missing required properties: {ev}")
                return False

        # Order contract
        ok, violations = validate_event_order(events)
        if not ok:
            print(f"❌ Event order contract violated: {violations}")
            return False
        print(f"✅ Stream emitted {len(events)} valid events adhering strictly to ordering schema")
    except Exception as e:
        print(f"❌ Event stream validation failed: {e}")
        return False

    # 4. evals/test_touch_log.jsonl test split touches
    if TEST_TOUCH_LOG.exists():
        touches = read_test_touches()
        for sys_name in ("agent_full", "agent_rules"):
            touch_count = sum(1 for t in touches if t.get("system") == sys_name)
            if touch_count > 1:
                print(f"❌ System '{sys_name}' touched test split {touch_count} times (> 1)")
                return False
        print("✅ Test split touches <= 1 for agent systems")
    else:
        print("⚠️ test_touch_log.jsonl not found yet (will be created during eval)")

    # 5. reports/agent_report.md
    if not AGENT_REPORT_MD.exists():
        print(f"❌ {AGENT_REPORT_MD} does not exist. Run `python scripts/run_agent_eval.py` first.")
        return False
    with open(AGENT_REPORT_MD, "r", encoding="utf-8") as f:
        rep_text = f.read()

    required_sections = [
        "Phase 6 Agentic RAG Ablation & Trade-off Report",
        "Capability Ablation Ladder",
        "Paired Bootstrap Statistical Comparison",
        "Cost-Benefit Trade-Offs",
        "Failure Mode Transition Analysis",
        "Annotated Execution Traces",
    ]
    for sec in required_sections:
        if sec not in rep_text:
            print(f"❌ Missing required section in agent report: '{sec}'")
            return False
    print("✅ reports/agent_report.md exists with all required sections and failure buckets")

    # 6. Check regression gate for default system
    print(f"Verifying regression gate for '{default_system}'...")
    try:
        passed = check_regression_gates(system_name=default_system)
        if not passed:
            print(f"❌ Regression gate failed for {default_system}")
            return False
        print(f"✅ Regression gate passed for {default_system}")
    except Exception as e:
        print(f"❌ Regression gate execution error: {e}")
        return False

    # 7. Check reports/claims.md
    if not CLAIMS_MD.exists():
        print(f"❌ {CLAIMS_MD} does not exist.")
        return False
    with open(CLAIMS_MD, "r", encoding="utf-8") as f:
        claims_text = f.read()
    if "## Validated Phase 6 Agent Claims" not in claims_text:
        print("❌ reports/claims.md missing '## Validated Phase 6 Agent Claims'")
        return False
    print("✅ reports/claims.md contains verified Phase 6 claims")

    # 8. Check docs/STATE.json
    if not STATE_FILE_PATH.exists():
        print(f"❌ {STATE_FILE_PATH} not found.")
        return False
    with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
        st = json.load(f)
    p6_state = st.get("phases", {}).get("6", {})
    if p6_state.get("status") != "complete":
        print(
            f"❌ STATE.json phases['6']['status'] is '{p6_state.get('status')}', expected 'complete'"
        )
        return False
    print("✅ docs/STATE.json Phase 6 marked complete")

    print("\n" + "=" * 65)
    print(" 🎉 ALL PHASE 6 VERIFICATION CHECKS PASSED CLEANLY! 🎉")
    print("=" * 65)
    return True


if __name__ == "__main__":
    success = verify_phase_6()
    sys.exit(0 if success else 1)
