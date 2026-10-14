"""Independent review-only video. Never opens the training gate or writes Replay."""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from threading import Event, Thread

import cv2
import numpy as np

CAMERAS = ("camera_left", "camera_high", "camera_right")


def read_review_video(root):
    path = Path(root) / "review-video.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("episode_uuid") != Path(root).name:
            return None
        video = Path(root) / "review.mp4"
        if result.get("state") == "ready" and (not video.is_file() or video.is_symlink()):
            return dict(result, state="error", error="review_video_missing")
        return result
    except (OSError, ValueError):
        return None


class ReviewVideo:
    """Bounded CPU encoder, sampled separately from HIL at 15 fps, 960 x 240."""
    def __init__(self, root, cache, *, clock=time.monotonic, fps=15):
        self.root, self.cache, self.clock, self.fps = Path(root), cache, clock, fps
        self.stop_event = Event()
        self.timestamps = []
        self.missing_frames = 0
        self.error = None
        self.process = None
        self.thread = None

    def start(self):
        # Keep encoder diagnostics on disk, never let a stderr pipe fill up.
        self.log = (self.root / "review-video.log").open("wb")
        try:
            self.process = subprocess.Popen([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size", "960x240",
                "-framerate", str(self.fps), "-i", "pipe:0", "-an",
                "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast",
                "-crf", "25", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-f", "mp4", str(self.root / "review.mp4.incomplete")],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
            os.set_blocking(self.process.stdin.fileno(), False)
            self.thread = Thread(target=self._run, name="episode-review-video", daemon=True)
            self.thread.start()
        except Exception:
            self.log.close()
            raise

    def _run(self):
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdin, selectors.EVENT_WRITE)
                deadline = time.monotonic()
                while not self.stop_event.is_set():
                    snapshot = self.cache.snapshot(self.clock, keys=CAMERAS)
                    tiles, missing = [], False
                    for key in CAMERAS:
                        image = snapshot.get(key) if snapshot.is_fresh(key) else None
                        valid = isinstance(image, np.ndarray) and image.dtype == np.uint8 and image.ndim == 3 and image.shape[-1] == 3
                        tile = cv2.resize(image, (320, 240)) if valid else np.zeros((240, 320, 3), np.uint8)
                        missing |= not valid
                        cv2.putText(tile, key + (" unavailable" if not valid else ""), (6, 20), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 255), 1)
                        tiles.append(tile)
                    payload = memoryview(np.concatenate(tiles, axis=1).tobytes())
                    write_deadline = time.monotonic() + 2
                    while payload:
                        if time.monotonic() >= write_deadline:
                            raise TimeoutError("review_encoder_stalled")
                        if selector.select(.1):
                            try:
                                written = os.write(self.process.stdin.fileno(), payload)
                                payload = payload[written:]
                            except BlockingIOError:
                                pass
                    self.timestamps.append(float(snapshot.now))
                    self.missing_frames += int(missing)
                    deadline += 1 / self.fps
                    # Do not queue stale frames if the CPU was delayed.
                    deadline = max(deadline, time.monotonic())
                    self.stop_event.wait(max(0, deadline - time.monotonic()))
        except Exception as error:
            self.error = str(error)
        finally:
            self.process.stdin.close()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(3)
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait(timeout=2)
            self.error = "review_encoder_stop_timeout"
        if self.thread and self.thread.is_alive():
            self.thread.join(2)
        self.log.close()
        complete = not self.error and code == 0 and bool(self.timestamps)
        if complete:
            os.replace(self.root / "review.mp4.incomplete", self.root / "review.mp4")
        result = {"episode_uuid": self.root.name, "state": "ready" if complete else "error",
                  "review_only": True, "source_fps": self.fps,
                  "source_frame_count": len(self.timestamps), "frame_timestamps": self.timestamps,
                  "missing_camera_frames": self.missing_frames, "error": self.error or (None if complete else "review_encoder_failed")}
        temporary = self.root / "review-video.json.incomplete"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(result, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.root / "review-video.json")
        return result
