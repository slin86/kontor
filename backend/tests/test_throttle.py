from kontor.core.throttle import Throttle


def test_blocks_after_limit_and_recovers_with_the_window() -> None:
    now = [0.0]
    t = Throttle(limit=3, window=60, clock=lambda: now[0])
    for _ in range(3):
        assert t.retry_after("k") == 0
        t.fail("k")
    assert 0 < t.retry_after("k") <= 61
    assert t.retry_after("other") == 0
    now[0] = 61
    assert t.retry_after("k") == 0


def test_reset_clears_a_key() -> None:
    t = Throttle(limit=1, window=60)
    t.fail("k")
    assert t.retry_after("k") > 0
    t.reset("k")
    assert t.retry_after("k") == 0
