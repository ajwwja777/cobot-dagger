"""Three independent native BGR video files; no resize, JPEG or lossy codec.

The ROS adapter only subscribes. A bounded queue isolates disk I/O from camera
callbacks. Overflow, stale input and write failures are visible archive errors;
they never stop a model or publish robot commands.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Queue, Empty, Full
import shutil
import subprocess
import threading
import time
from uuid import uuid4

import numpy as np
from .topics import REQUIRED_TOPICS

CAMERAS = ("camera_left", "camera_high", "camera_right")


def atomic_json(path, value):
    path=Path(path); pending=path.with_name(path.name+"."+uuid4().hex+".tmp")
    pending.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.replace(pending,path)


class CameraFile:
    def __init__(self, root, key, *, fps=30, queue_frames=64, reserve_bytes=20*1024**3):
        self.root=Path(root);self.key=key;self.fps=fps;self.reserve=reserve_bytes
        self.queue=Queue(maxsize=queue_frames);self.end=threading.Event()
        self.thread=None;self.process=None;self.error=None;self.frames=0
        self.last_arrival=None;self.shape=None;self.last_seq=None;self.log=None

    def start(self):
        self.thread=threading.Thread(target=self._run,name="raw-"+self.key,daemon=True);self.thread.start()

    def offer(self, image, *, stamp, sequence=None):
        if self.end.is_set() or self.error:return
        try:
            value=np.asarray(image)
            if value.dtype!=np.uint8 or value.ndim!=3 or value.shape[2]!=3:raise ValueError("expected BGR8 image")
            if self.shape is not None and value.shape!=self.shape:raise ValueError("camera dimensions changed")
            if sequence is not None and self.last_seq is not None and sequence!=self.last_seq+1:
                raise ValueError("source sequence gap: %s -> %s"%(self.last_seq,sequence))
            self.last_seq=sequence;self.last_arrival=time.monotonic()
            self.queue.put_nowait((np.array(value,copy=True),float(stamp),sequence,self.last_arrival))
        except (ValueError,Full) as exc:
            self.error=str(exc) or "video queue full; archive incomplete"
            self.end.set()

    def _run(self):
        try:
            with (self.root/(self.key+".timestamps.jsonl")).open("x") as timestamps:
                while not self.end.is_set() or not self.queue.empty():
                    try:image,stamp,seq,arrival=self.queue.get(timeout=.1)
                    except Empty:continue
                    if self.process is None:
                        self.shape=image.shape
                        self.log=(self.root/(self.key+".log")).open("xb")
                        self.process=subprocess.Popen([
                            "ffmpeg","-nostdin","-hide_banner","-loglevel","error","-n",
                            "-f","rawvideo","-pixel_format","bgr24","-video_size","%dx%d"%(image.shape[1],image.shape[0]),
                            "-framerate",str(self.fps),"-i","pipe:0","-an","-threads","1","-c:v","rawvideo","-pix_fmt","bgr24","-f","avi",
                            str(self.root/(self.key+".incomplete.avi"))],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log)
                    if image.shape!=self.shape:raise ValueError("camera dimensions changed")
                    if self.frames%30==0 and shutil.disk_usage(self.root).free<self.reserve:
                        raise OSError("video disk reserve reached")
                    self.process.stdin.write(image.tobytes(order="C"))
                    timestamps.write(json.dumps({"frame":self.frames,"source_stamp":stamp,"sequence":seq,"arrival_monotonic":arrival})+"\n")
                    self.frames+=1
                timestamps.flush();os.fsync(timestamps.fileno())
        except Exception as exc:
            self.error=str(exc);self.end.set()
        finally:
            if self.process:
                try:
                    self.process.stdin.close()
                    if self.process.wait(timeout=8)!=0:self.error=self.error or "ffmpeg failed"
                except Exception as exc:
                    self.error=self.error or str(exc)
                    self.process.kill();self.process.wait(timeout=3)
            if self.log:self.log.close()
            if not self.error and self.frames:
                os.replace(self.root/(self.key+".incomplete.avi"),self.root/(self.key+".avi"))
            elif not self.frames:self.error=self.error or "no camera frames"

    def stop(self):
        self.end.set()
        if self.thread:self.thread.join(timeout=12)
        if self.thread and self.thread.is_alive():
            self.error=self.error or "video finalization timeout"
            if self.process and self.process.poll() is None:self.process.kill()
            self.thread.join(timeout=3)

    def status(self):
        age=time.monotonic()-self.last_arrival if self.last_arrival is not None else None
        if not self.end.is_set() and age is not None and age>2:
            self.error=self.error or "camera stream stale";self.end.set()
        error=self.error
        return {"frames":self.frames,"error":error,"width":self.shape[1] if self.shape else None,
                "height":self.shape[0] if self.shape else None,"codec":"rawvideo","pixel_format":"bgr24",
                "container_fps":self.fps,"timestamps":self.key+".timestamps.jsonl",
                "file":self.key+(".avi" if self.end.is_set() and not error else ".incomplete.avi")}


class ThreeCameraVideo:
    def __init__(self, root, *, metadata=None, reserve_bytes=20*1024**3):
        self.root=Path(root);self.metadata=metadata or {};self.writers={}
        self.subscribers=[];self.stopped=False;self.error=None;self.reserve=reserve_bytes

    def start(self):
        if shutil.which("ffmpeg") is None:raise RuntimeError("ffmpeg unavailable")
        from .asset_storage import require_storage
        require_storage(self.root,write=True)
        self.root.mkdir(parents=True,exist_ok=False)
        if shutil.disk_usage(self.root).free<self.reserve:raise RuntimeError("insufficient free space for uncompressed video")
        from .ros_subscriber import _load_ros_bindings
        bindings=_load_ros_bindings();bridge=bindings.cv_bridge_factory()
        try:
            for key in CAMERAS:
                writer=CameraFile(self.root,key,reserve_bytes=self.reserve);self.writers[key]=writer;writer.start()
                def receive(msg, writer=writer):
                    try:
                        image=bridge.imgmsg_to_cv2(msg,desired_encoding="bgr8")
                        writer.offer(image,stamp=msg.header.stamp.to_sec(),sequence=msg.header.seq)
                    except Exception as exc:writer.error=str(exc);writer.end.set()
                self.subscribers.append(bindings.rospy.Subscriber(REQUIRED_TOPICS[key],bindings.image_type,receive,queue_size=64,buff_size=64*1024*1024))
            deadline=time.monotonic()+5
            while not all(w.frames>0 for w in self.writers.values()):
                errors=[w.error for w in self.writers.values() if w.error]
                if errors:raise RuntimeError("; ".join(errors))
                if time.monotonic()>deadline:raise RuntimeError("three camera recording not ready")
                time.sleep(.02)
            self._persist()
        except Exception as exc:
            self.error=str(exc);self.stop();raise
        return self.status()

    def status(self):
        cameras={k:w.status() for k,w in self.writers.items()}
        errors=[v["error"] for v in cameras.values() if v["error"]]
        return {"state":"error" if self.error or errors else "saved" if self.stopped else "recording",
                "error":self.error or "; ".join(errors) or None,"directory":str(self.root),
                "uncompressed":True,"cameras":cameras,**self.metadata}

    def _persist(self):atomic_json(self.root/"video.json",self.status())

    def stop(self):
        if self.stopped:return self.status()
        for sub in self.subscribers:sub.unregister()
        self.subscribers=[]
        for writer in self.writers.values():writer.stop()
        self.stopped=True;self._persist()
        return self.status()
