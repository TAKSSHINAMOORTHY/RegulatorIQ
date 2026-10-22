"""Unit tests for Token-Bucket Rate Limiter with Fake Clock."""

from api.ratelimit import DailyTracker, RateLimiter, TokenBucket


class FakeClock:
    def __init__(self, start_t: float = 1000000.0):
        self.t = start_t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_token_bucket_math():
    clock = FakeClock()
    # 1 token per second, burst 3
    bucket = TokenBucket(rate_per_second=1.0, capacity=3.0, time_fn=clock)

    # 3 immediate requests should pass (burst)
    assert bucket.consume(1.0)[0] is True
    assert bucket.consume(1.0)[0] is True
    assert bucket.consume(1.0)[0] is True

    # 4th request should fail immediately
    allowed, retry_after = bucket.consume(1.0)
    assert allowed is False
    assert retry_after >= 1

    # Advance clock by 1.5 seconds -> 1 token should replenish
    clock.advance(1.5)
    assert bucket.consume(1.0)[0] is True
    assert bucket.consume(1.0)[0] is False


def test_rate_limiter_ask_and_burst():
    clock = FakeClock()
    limiter = RateLimiter(
        ask_rpm=60,  # 1 token/sec
        ask_burst=2,
        ask_daily_cap=10,
        time_fn=clock,
    )

    client = "192.168.1.5"
    assert limiter.check_ask_rate_limit(client)[0] is True
    assert limiter.check_ask_rate_limit(client)[0] is True

    # 3rd request in same second fails
    allowed, retry_after = limiter.check_ask_rate_limit(client)
    assert allowed is False
    assert retry_after >= 1


def test_rate_limiter_daily_cap():
    clock = FakeClock()
    limiter = RateLimiter(
        ask_rpm=6000,
        ask_burst=100,
        ask_daily_cap=3,
        time_fn=clock,
    )

    client = "192.168.1.10"
    assert limiter.check_ask_rate_limit(client)[0] is True
    assert limiter.check_ask_rate_limit(client)[0] is True
    assert limiter.check_ask_rate_limit(client)[0] is True

    # 4th request exceeds daily cap
    allowed, retry_after = limiter.check_ask_rate_limit(client)
    assert allowed is False
    assert retry_after > 0


def test_rate_limiter_lru_eviction():
    limiter = RateLimiter(max_keys=2)
    limiter.check_ask_rate_limit("1.1.1.1")
    limiter.check_ask_rate_limit("2.2.2.2")
    assert len(limiter.ask_buckets) == 2

    # Accessing 3rd IP evicts oldest IP (1.1.1.1)
    limiter.check_ask_rate_limit("3.3.3.3")
    assert len(limiter.ask_buckets) == 2
    assert "1.1.1.1" not in limiter.ask_buckets
    assert "2.2.2.2" in limiter.ask_buckets
    assert "3.3.3.3" in limiter.ask_buckets
