from capture_core.ros_cache import LatestMessageCache


def test_live_preflight_time_follows_callback_under_cache_lock():
    cache = LatestMessageCache()
    cache.put("front_left", {"position": [0] * 7}, 10.001, 10.001)
    assert not cache.snapshot(10.0).is_fresh("front_left")
    def clock():
        assert cache._lock.locked()
        return 10.002
    assert cache.snapshot(clock).is_fresh("front_left")
    cache.put("front_left", {"position": [0] * 7}, 1000, 1000)
    assert not cache.snapshot(clock).is_fresh("front_left")
