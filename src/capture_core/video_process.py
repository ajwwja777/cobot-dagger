"""Owned recording subprocess: separate ROS/GIL/encoder work from HTTP previews."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4
from .uncompressed_video import atomic_json


class ProcessVideo:
    def __init__(self, root, *, metadata=None, reserve_bytes=20*1024**3):
        self.root=Path(root);self.metadata=metadata or {};self.reserve=reserve_bytes
        self.worker_id=uuid4().hex;self.process=None;self.last=None
        self.status_file=self.root/"video-worker.json"

    def _command(self):
        return [sys.executable,"-u","-m","capture_core.video_process","--root",str(self.root),
                "--worker-id",self.worker_id,"--metadata",json.dumps(self.metadata),"--reserve-bytes",str(self.reserve)]

    def start(self):
        if self.root.exists():raise ValueError("video archive already exists")
        # ROS paths added during Web bootstrap must also be visible to a fresh interpreter.
        paths=list(dict.fromkeys([str(Path(__file__).resolve().parents[1])]+sys.path))
        env=dict(os.environ,PYTHONPATH=os.pathsep.join(paths))
        self.process=subprocess.Popen(self._command(),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL,env=env,start_new_session=True)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            status=self.status()
            if status.get("state")=="recording":return status
            if status.get("state")=="error":raise RuntimeError(status.get("error") or "video worker failed")
            time.sleep(.03)
        self.stop();raise RuntimeError("video worker readiness timeout")

    def status(self):
        if self.last and self.last.get("worker_complete"):return dict(self.last)
        try:
            if self.status_file.stat().st_size>262144:raise ValueError("invalid worker status")
            value=json.loads(self.status_file.read_text())
            if not isinstance(value,dict) or value.get("worker_id")!=self.worker_id:raise ValueError("worker identity mismatch")
            self.last=value
        except (OSError,ValueError):pass
        value=dict(self.last or {"state":"starting","directory":str(self.root),"error":None})
        if self.process and self.process.poll() is not None and not value.get("worker_complete"):
            value.update(state="error",error="video worker exited before final status",worker_exit_code=self.process.returncode)
        return value

    def stop(self):
        if self.process and self.process.poll() is None:
            try:self.process.stdin.write(b"stop\n");self.process.stdin.flush()
            except (BrokenPipeError,ValueError):pass
            try:self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                # Only the session we created, including its encoder children.
                if self.process.poll() is None and os.getpgid(self.process.pid)==self.process.pid:
                    os.killpg(self.process.pid,signal.SIGTERM)
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if self.process.poll() is None and os.getpgid(self.process.pid)==self.process.pid:os.killpg(self.process.pid,signal.SIGKILL)
                    self.process.wait(timeout=5)
                self.last={**self.status(),"state":"error","error":"video worker finalization timeout","worker_complete":True}
                if self.root.is_dir():atomic_json(self.root/"video.json",self.last)
        if self.process and self.process.stdin:self.process.stdin.close()
        return self.status()


def has_recording_camera(status):
    return any(not camera.get("error") for camera in status.get("cameras", {}).values())


def run_worker(args):
    from .ros_subscriber import _load_ros_bindings
    from .uncompressed_video import ThreeCameraVideo
    root=Path(args.root);status_file=root/"video-worker.json";stop=threading.Event();reason={"value":None}
    video=None;bindings=None;error=None
    def request_stop(value):reason["value"]=value;stop.set()
    def read_control():
        line=sys.stdin.readline()
        request_stop("stop" if line.strip()=="stop" else "owner control connection closed")
    for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,lambda *_:request_stop("worker terminated"))
    threading.Thread(target=read_control,daemon=True).start()
    def persist(value,complete=False):
        atomic_json(status_file,{**value,"worker_id":args.worker_id,"worker_pid":os.getpid(),
                                "worker_complete":complete,"updated_monotonic":time.monotonic()})
    try:
        bindings=_load_ros_bindings()
        bindings.rospy.init_node("three_camera_video_worker",anonymous=True,disable_signals=True)
        video=ThreeCameraVideo(root,metadata=json.loads(args.metadata),reserve_bytes=args.reserve_bytes)
        video.start()
        while not stop.is_set():
            value=video.status();persist(value)
            # One failed camera must not truncate the other two archives.
            if value.get("state")=="error" and not has_recording_camera(value):break
            stop.wait(.25)
    except Exception as exc:error=str(exc)
    finally:
        if video:
            if error or (reason["value"] and reason["value"]!="stop"):video.error=error or reason["value"]
            try:value=video.stop()
            except Exception as exc:value={"state":"error","error":str(exc),"directory":str(root)}
        else:value={"state":"error","error":error or "video worker did not initialize","directory":str(root)}
        root.mkdir(parents=True,exist_ok=True);persist(value,complete=True)
        if bindings:bindings.rospy.signal_shutdown("recording worker finalized")
    return 0 if value.get("state")=="saved" else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True);parser.add_argument("--worker-id",required=True)
    parser.add_argument("--metadata",default="{}");parser.add_argument("--reserve-bytes",type=int,default=20*1024**3)
    raise SystemExit(run_worker(parser.parse_args()))
