"""Unit tests for state management."""

from scripts.state import read_state, update_phase


def test_update_phase():
    update_phase(
        1,
        status="complete",
        counts={"total_documents": 42},
    )
    s = read_state()
    assert s["phases"]["1"]["status"] == "complete"
    assert s["phases"]["1"]["counts"]["total_documents"] == 42
