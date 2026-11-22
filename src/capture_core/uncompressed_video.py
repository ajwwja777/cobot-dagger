"""Three independent camera archives, H.264 MP4 by default.

Legacy raw AVI remains explicitly available via encoding="rawvideo". The ROS
adapter only subscribes; bounded queues isolate camera callbacks from encoding.
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
from .video_encoding import live_encoding_args, select_live_encoder

CAMERAS = ("camera_left", "camera_high", "camera_right")


def atomic_json(path, value):
    path=Path(path); pending=path.with_name(path.name+"."+uuid4().hex+".tmp")
    pending.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.replace(pending,path)


class CameraFile:
    def __init__(self, root, key, *, fps=30, queue_frames=64, reserve_bytes=20*1024**3, encoding="h264", encoder="libx264"):
        if encoding not in {"h264","rawvideo"}:raise ValueError("invalid_video_encoding")
        self.encoder=encoder
        self.encoding=encoding;self.extension="mp4" if encoding=="h264" else "avi"
        self.root=Path(root);self.key=key;self.fps=fps;self.reserve=reserve_bytes
        self.queue=Queue(maxsize=queue_frames);self.end=threading.Event()
        self.thread=None;self.process=None;self.error=None;self.frames=0
        self.last_arrival=None;self.shape=None;self.last_seq=None;self.log=None;self.input_pixel_format=None;self.received_frames=0;self.queue_peak=0

    def start(self):
        self.thread=threading.Thread(target=self._run,name="video-"+self.key,daemon=True);self.thread.start()

    def offer(self, image, *, stamp, sequence=None, pixel_format="bgr24"):
        if self.end.is_set() or self.error:return
        try:
            value=np.asarray(image)
            if value.dtype!=np.uint8 or value.ndim!=3 or value.shape[2]!=3:raise ValueError("expected RGB8/BGR8 image")
            if pixel_format not in {"rgb24","bgr24"}:raise ValueError("unsupported input pixel format")
            if self.input_pixel_format is not None and pixel_format!=self.input_pixel_format:raise ValueError("camera encoding changed")
            self.input_pixel_format=pixel_format
            if self.shape is not None and value.shape!=self.shape:raise ValueError("camera dimensions changed")
            if sequence is not None and self.last_seq is not None and sequence!=self.last_seq+1:
                raise ValueError("source sequence gap: %s -> %s"%(self.last_seq,sequence))
            self.last_seq=sequence;self.last_arrival=time.monotonic()
            self.received_frames+=1
            self.queue.put_nowait((np.array(value,copy=True,order="C"),float(stamp),sequence,self.last_arrival))
            self.queue_peak=max(self.queue_peak,self.queue.qsize())
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
                            "-f","rawvideo","-pixel_format",self.input_pixel_format,"-video_size","%dx%d"%(image.shape[1],image.shape[0]),
                            "-framerate",str(self.fps),"-i","pipe:0","-an"] +
                            (live_encoding_args(self.encoder) if self.encoding=="h264" else ["-threads","1","-c:v","rawvideo","-pix_fmt","bgr24","-f","avi"]) +
                            [str(self.root/(self.key+".incomplete."+self.extension))],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log)
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
                os.replace(self.root/(self.key+".incomplete."+self.extension),self.root/(self.key+"."+self.extension))
            elif not self.frames:self.error=self.error or "no camera frames"

    def stop(self):
        self.end.set()
        if self.thread:self.thread.join(timeout=12)
        if self.thread and self.thread.is_alive():
            self.error=self.error or "video finalization timeout"
            if self.process and self.process.poll() is None:self.process.kill()
            self.thread.join(timeout=3)

    def dimensions(self):
        height,width=self.shape[:2]
        ratio=min(1,1920/width,1080/height) if self.encoding=="h264" else 1
        if self.encoding=="rawvideo":return width,height
        return int(width*ratio)//2*2,int(height*ratio)//2*2

    def status(self):
        age=time.monotonic()-self.last_arrival if self.last_arrival is not None else None
        if not self.end.is_set() and age is not None and age>2:
            self.error=self.error or "camera stream stale";self.end.set()
        error=self.error
        return {"frames":self.frames,"received_frames":self.received_frames,"queue_depth":self.queue.qsize(),"queue_peak":self.queue_peak,"queue_capacity":self.queue.maxsize,"error":error,"width":self.dimensions()[0] if self.shape else None,
                "height":self.dimensions()[1] if self.shape else None,
                "input_pixel_format":self.input_pixel_format,"source_width":self.shape[1] if self.shape else None,"source_height":self.shape[0] if self.shape else None,"codec":self.encoding,
                "pixel_format":"yuv420p" if self.encoding=="h264" else "bgr24", "encoder":self.encoder if self.encoding=="h264" else "rawvideo", "qp":18 if self.encoding=="h264" and self.encoder=="h264_nvenc" else None, "crf":14 if self.encoding=="h264" and self.encoder=="libx264" else None, "max_resolution":[1920,1080] if self.encoding=="h264" else None,
                "container_fps":self.fps,"timestamps":self.key+".timestamps.jsonl",
                "file":self.key+("." if self.end.is_set() and not error else ".incomplete.")+self.extension}


class ThreeCameraVideo:
    def __init__(self, root, *, metadata=None, reserve_bytes=20*1024**3, encoding="h264"):
        if encoding not in {"h264","rawvideo"}:raise ValueError("invalid_video_encoding")
        self.encoding=encoding
        self.root=Path(root);self.metadata=metadata or {};self.writers={}
        self.subscribers=[];self.stopped=False;self.error=None;self.reserve=reserve_bytes

    def start(self):
        if shutil.which("ffmpeg") is None:raise RuntimeError("ffmpeg unavailable")
        from .asset_storage import require_storage
        require_storage(self.root,write=True)
        self.root.mkdir(parents=True,exist_ok=False)
        if shutil.disk_usage(self.root).free<self.reserve:raise RuntimeError("insufficient free space for video")
        from .ros_subscriber import _load_ros_bindings
        bindings=_load_ros_bindings();bridge=bindings.cv_bridge_factory()
        encoder=select_live_encoder() if self.encoding=="h264" else "rawvideo"
        try:
            for key in CAMERAS:
                writer=CameraFile(self.root,key,reserve_bytes=self.reserve,encoding=self.encoding,encoder=encoder);self.writers[key]=writer;writer.start()
                def receive(msg, writer=writer):
                    try:
                        encoding=getattr(msg,"encoding",None)
                        if encoding in {"rgb8","bgr8"}:
                            # Avoid a full-resolution RGB->BGR conversion. Feed the
                            # original channel order to ffmpeg; honor ROS row stride.
                            height,width,step=int(msg.height),int(msg.width),int(msg.step)
                            if min(height,width)<=0 or step<width*3 or len(msg.data)!=height*step:raise ValueError("invalid camera image layout")
                            image=np.frombuffer(msg.data,dtype=np.uint8).reshape(height,step)[:,:width*3].reshape(height,width,3)
                            pixel_format="rgb24" if encoding=="rgb8" else "bgr24"
                        else:
                            image=bridge.imgmsg_to_cv2(msg,desired_encoding="bgr8");pixel_format="bgr24"
                        writer.offer(image,stamp=msg.header.stamp.to_sec(),sequence=msg.header.seq,pixel_format=pixel_format)
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
                "uncompressed":self.encoding=="rawvideo","format":"mp4" if self.encoding=="h264" else "avi","cameras":cameras,**self.metadata}

    def _persist(self):atomic_json(self.root/"video.json",self.status())

    def stop(self):
        if self.stopped:return self.status()
        for sub in self.subscribers:sub.unregister()
        self.subscribers=[]
        for writer in self.writers.values():writer.stop()
        self.stopped=True;self._persist()
        return self.status()
