import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
import pytest
from capture_core.uncompressed_video import CameraFile


def test_three_raw_avi_files_decode_to_exact_native_pixels(tmp_path):
    assert shutil.which("ffmpeg")
    expected={}
    for index,key in enumerate(["camera_left","camera_high","camera_right"]):
        writer=CameraFile(tmp_path,key,reserve_bytes=0);writer.start()
        frames=[np.full((12,16,3),index*30+i,dtype=np.uint8) for i in range(3)]
        expected[key]=b"".join(f.tobytes() for f in frames)
        for i,frame in enumerate(frames):writer.offer(frame,stamp=100+i/30,sequence=i)
        writer.stop()
        assert writer.error is None and writer.frames==3
        path=tmp_path/(key+".avi");assert path.is_file()
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-of","json",str(path)]))["streams"][0]
        assert probe["codec_name"]=="rawvideo" and (probe["width"],probe["height"])==(16,12)
        actual=subprocess.check_output(["ffmpeg","-v","error","-i",str(path),"-threads","1","-f","rawvideo","-pix_fmt","bgr24","pipe:1"])
        assert actual==expected[key]
        stamps=[json.loads(line) for line in (tmp_path/(key+".timestamps.jsonl")).read_text().splitlines()]
        assert [s["source_stamp"] for s in stamps]==[100,100+1/30,100+2/30]


def test_overflow_is_visible_and_not_reported_as_complete(tmp_path):
    writer=CameraFile(tmp_path,"camera_left",queue_frames=1,reserve_bytes=0)
    image=np.zeros((12,16,3),dtype=np.uint8)
    writer.offer(image,stamp=1,sequence=1);writer.offer(image,stamp=2,sequence=2)
    assert writer.error and writer.end.is_set()
    writer.start();writer.stop()
    assert not (tmp_path/"camera_left.avi").exists()
    assert (tmp_path/"camera_left.incomplete.avi").exists()


def test_source_gaps_and_staleness_retained_after_stop(tmp_path):
    writer=CameraFile(tmp_path,"camera_high",reserve_bytes=0)
    image=np.zeros((12,16,3),dtype=np.uint8)
    writer.offer(image,stamp=1,sequence=4);writer.offer(image,stamp=2,sequence=6)
    assert "sequence gap" in writer.error
    stale=CameraFile(tmp_path,"camera_right",reserve_bytes=0)
    stale.last_arrival=time.monotonic()-3
    assert stale.status()["error"]=="camera stream stale"
    stale.end.set()
    assert stale.status()["error"]=="camera stream stale"


def test_low_disk_retains_partial_and_error(tmp_path):
    writer=CameraFile(tmp_path,"camera_left",reserve_bytes=2**70)
    writer.start();writer.offer(np.zeros((12,16,3),dtype=np.uint8),stamp=1,sequence=1);writer.stop()
    assert "reserve" in writer.error and not (tmp_path/"camera_left.avi").exists()


def test_ros_adapter_subscribes_three_original_topics_and_saves_manifest(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from capture_core.uncompressed_video import ThreeCameraVideo,CAMERAS
    from capture_core import ros_subscriber
    topics=[];closed=[]
    image=np.arange(16*12*3,dtype=np.uint8).reshape(12,16,3)
    def subscribe(topic,kind,callback,**kwargs):
        topics.append(topic)
        for i in range(3):callback(SimpleNamespace(header=SimpleNamespace(seq=i,stamp=SimpleNamespace(to_sec=lambda i=i:100+i/30)),image=image))
        return SimpleNamespace(unregister=lambda:closed.append(topic))
    bindings=SimpleNamespace(rospy=SimpleNamespace(Subscriber=subscribe),image_type=object,
                             cv_bridge_factory=lambda:SimpleNamespace(imgmsg_to_cv2=lambda msg,desired_encoding:msg.image))
    monkeypatch.setattr(ros_subscriber,"_load_ros_bindings",lambda:bindings)
    root=tmp_path/"trial";video=ThreeCameraVideo(root,metadata={"run_id":"test"},reserve_bytes=0)
    assert video.start()["state"]=="recording"
    state=video.stop()
    assert state["state"]=="saved" and len(topics)==len(closed)==3
    assert set(state["cameras"])==set(CAMERAS)
    manifest=json.loads((root/"video.json").read_text())
    assert manifest["run_id"]=="test" and all(v["frames"]==3 for v in manifest["cameras"].values())
    assert all((root/(key+".avi")).is_file() for key in CAMERAS)
