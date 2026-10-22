"""Unit tests for Global Daily LLM Budget Guard and State Transitions."""

from api.budget import GlobalBudgetGuard
from api.state import AppState, ServiceMode, ServiceStage


class FakeClock:
    def __init__(self, start_t: float = 1700000000.0):
        self.t = start_t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_budget_guard_transitions():
    clock = FakeClock()
    state = AppState()
    state.configured_mode = ServiceMode.FULL
    state.mode = ServiceMode.FULL

    guard = GlobalBudgetGuard(app_state=state, daily_call_limit=10, time_fn=clock)

    assert not guard.is_exhausted
    assert guard.percent_used == 0.0

    # Record 8 calls (80%) -> triggers warning
    guard.record_llm_calls(8)
    assert guard.warned_at_80 is True
    assert guard.percent_used == 80.0
    assert state.mode == ServiceMode.FULL
    assert state.degraded_notice is not None

    # Record 2 more calls (100%) -> switches to RULES mode
    guard.record_llm_calls(2)
    assert guard.is_exhausted is True
    assert state.mode == ServiceMode.RULES
    assert any("Daily LLM call budget exhausted" in r for r in state.degraded_reasons)

    # Advance clock by 24 hours (86400s) -> UTC reset restores FULL mode
    clock.advance(86400)
    assert not guard.is_exhausted
    assert state.mode == ServiceMode.FULL


def test_state_machine_durations():
    state = AppState()
    assert state.current_stage == ServiceStage.STARTING
    assert not state.is_ready

    state.transition_to(ServiceStage.LOADING_INDEX)
    assert state.current_stage == ServiceStage.LOADING_INDEX
    assert ServiceStage.STARTING.value in state.stage_durations

    state.transition_to(ServiceStage.READY)
    assert state.current_stage == ServiceStage.READY
    assert ServiceStage.LOADING_INDEX.value in state.stage_durations
    assert state.is_ready is False  # agent_runner not injected yet

    # Inject mock agent runner
    state.agent_runner = object()
    assert state.is_ready is True
