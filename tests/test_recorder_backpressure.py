"""Regression tests for missed ticks and bounded, observable writer backpressure."""
import time
from collections import namedtuple
from queue import Queue
from threading import Event
from types import SimpleNamespace

from capture_core.config import RecorderConfig
from capture_core.recorder import RecorderStartRequest, RolloutRecorder
from capture_core.schema import EpisodeIdentity

Disk = namedtuple("Disk", "total used free")


def identity():
    return EpisodeIdentity("synthetic", "diagnostic", "none", "offline")


def config(tmp_path, capacity=8):
    return RecorderConfig(data_root=tmp_path, sample_rate_hz=10,
        max_duration_seconds=10, min_free_disk_bytes=1, stop_free_disk_bytes=1,
        writer_queue_capacity=capacity)


def test_long_sample_gap_is_not_filled_with_catchup_frames(tmp_path):
    class Clock:
        now = 0.0
        def __call__(self): return self.now
    clock = Clock()
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def set(self): self.stopped = True
        def wait(self, delay): clock.now += delay
    times = []
    class Cache:
        def snapshot(self, now):
            # Production API samples clock while holding its cache lock.
            return now() if callable(now) else now
    class Sampler:
        def sample(self, snapshot, who, index):
            times.append(snapshot)
            if index == 0: clock.now += 1.0
            return SimpleNamespace(frame_index=index)
    recorder = RolloutRecorder(config(tmp_path), Cache(), sampler=Sampler(),
        clock=clock, disk_usage=lambda _: Disk(100, 0, 100))
    recorder._queue = Queue(maxsize=8)
    recorder._max_timesteps = 4
    recorder._stop_event = Stop()
    recorder._acquisition_loop(identity())
    assert len(times) == 4
    assert times[1] >= 1.09
    assert all(b-a > .09 for a,b in zip(times[1:], times[2:]))
    assert recorder.status()['timing']['missed_sample_ticks'] == 10
    assert recorder.status()['frames_sampled'] == 4
    assert recorder.status()['error'] is None


def test_blocked_writer_is_visible_and_overflow_never_publishes(tmp_path):
    entered, release = Event(), Event()
    class Writer:
        publication_status = 'open'
        def __init__(self, root, who, maximum, **kwargs):
            self.incomplete_path = root / 'synthetic.incomplete'
        def append(self, frame):
            entered.set()
            assert release.wait(3)
        def finalize(self, *args, **kwargs):
            raise AssertionError('overflow must not publish')
        def abort(self, reason):
            self.publication_status = 'revoked'
            return self.incomplete_path
    class Sampler:
        def sample(self, snapshot, who, index):
            return SimpleNamespace(frame_index=index)
    recorder = RolloutRecorder(config(tmp_path, capacity=2),
        SimpleNamespace(snapshot=lambda now: now()), sampler=Sampler(),
        writer_factory=Writer, disk_usage=lambda _: Disk(100,0,100))
    recorder.check_ready = lambda root: tmp_path
    recorder.start(RecorderStartRequest(identity()))
    try:
        assert entered.wait(1)
        deadline=time.monotonic()+2
        while recorder.status()['state'] != 'error' and time.monotonic()<deadline:
            time.sleep(.01)
        status=recorder.status()
        assert status['error'] == 'writer_queue_overflow'
        assert status['timing']['queue_depth'] == 2
        assert status['timing']['queue_high_watermark'] == 2
        assert status['timing']['writer_inflight_ms'] >= 100
        assert status['frames_written'] == 0
        assert not status['publication_allowed']
    finally:
        release.set()
        recorder._writer_thread.join(2)
        recorder._acquisition_thread.join(2)
    final=recorder.status()
    assert final['publication_status'] == 'revoked'
    assert final['timing']['writer_inflight_ms'] == 0
    assert final['timing']['writer_max_ms'] >= 100
