"""Unit tests for circuit breaker state machine."""

from ingest.download import CircuitBreaker


def test_circuit_breaker_threshold():
    cb = CircuitBreaker(block_threshold=3, max_trips=2, pause_seconds=0.1)

    assert not cb.record_block()
    assert not cb.record_block()
    # 3rd block trips breaker
    assert cb.record_block()
    assert cb.breaker_trips == 1
    assert not cb.listing_only_mode

    # Reset counter on success
    cb.record_success()
    assert cb.consecutive_blocks == 0

    # Trip second time
    cb.record_block()
    cb.record_block()
    assert cb.record_block()
    assert cb.breaker_trips == 2
    assert cb.listing_only_mode
