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
        writer=CameraFile(tmp_path,key,reserve_bytes=0,encoding="rawvideo");writer.start()
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
    assert not (tmp_path/"camera_left.mp4").exists()
    assert (tmp_path/"camera_left.incomplete.mp4").exists()


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
    assert "reserve" in writer.error and not (tmp_path/"camera_left.mp4").exists()


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
    assert manifest["uncompressed"] is False and manifest["format"]=="mp4"
    for key in CAMERAS:
        path=root/(key+".mp4");assert path.is_file()
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-of","json",str(path)]))["streams"][0]
        assert probe["codec_name"]=="h264" and probe["pix_fmt"]=="yuv420p"
        assert (probe["width"],probe["height"])==(16,12)
        assert path.read_bytes().index(b"moov")<path.read_bytes().index(b"mdat")


def test_mp4_downscales_to_1080p_without_upscaling(tmp_path):
    writer=CameraFile(tmp_path,"camera_left",reserve_bytes=0);writer.start()
    writer.offer(np.zeros((1440,2560,3),dtype=np.uint8),stamp=1,sequence=1);writer.stop()
    assert writer.error is None
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-of","json",str(tmp_path/"camera_left.mp4")]))["streams"][0]
    assert (probe["width"],probe["height"])==(1920,1080)


def test_legacy_export_preserves_sources_and_exact_frames(tmp_path):
    from capture_core.browser_video import convert_archive,sha256
    root=tmp_path/"archive";root.mkdir();cameras={};original={}
    for key in ["camera_left","camera_high","camera_right"]:
        writer=CameraFile(root,key,reserve_bytes=0,encoding="rawvideo");writer.start()
        for i in range(4):writer.offer(np.full((48,64,3),i*40,dtype=np.uint8),stamp=i/30,sequence=i)
        writer.stop();cameras[key]=writer.status();original[key]=sha256(root/(key+".avi"))
    manifest=root/"video.json";manifest.write_text(json.dumps({"state":"saved","uncompressed":True,"cameras":cameras}));before=manifest.read_bytes()
    output=convert_archive(root)
    assert all(row["frames"]==4 and row["codec"]=="h264" for row in output["cameras"].values())
    assert all(sha256(root/(key+".avi"))==digest for key,digest in original.items())
    assert manifest.read_bytes()==before and convert_archive(root)==output
    manifest.write_text(json.dumps({"state":"recording","uncompressed":True}))
    with pytest.raises(ValueError):convert_archive(root)


def test_native_high_resolution_source_encodes_1440x1080_at_high_quality(tmp_path):
    writer=CameraFile(tmp_path,"camera_left",reserve_bytes=0);writer.start()
    # Native camera mode is 4:3. No upscaling or 16:9 stretching.
    image=np.zeros((1224,1632,3),dtype=np.uint8);image[:,::8]=220;image[::8]=220
    for i in range(3):writer.offer(image,stamp=i/30,sequence=i)
    writer.stop();assert writer.error is None
    path=tmp_path/'camera_left.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))['streams'][0]
    assert (probe['width'],probe['height'])==(1440,1080)
    assert probe['codec_name']=='h264' and probe['pix_fmt']=='yuv420p'
    status=writer.status();assert status['crf']==14 and (status['source_width'],status['source_height'])==(1632,1224)
    assert (status['width'],status['height'])==(1440,1080)


def test_native_rgb_ros_path_skips_cv_conversion_and_preserves_stride_and_colors(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from capture_core import ros_subscriber
    from capture_core.uncompressed_video import ThreeCameraVideo,CAMERAS
    image=np.zeros((12,16,3),dtype=np.uint8);image[:,:,0]=200
    padded=np.zeros((12,16*3+8),dtype=np.uint8);padded[:,:48]=image.reshape(12,48)
    def subscribe(topic,kind,callback,**kwargs):
        for i in range(3):callback(SimpleNamespace(encoding='rgb8',height=12,width=16,step=56,data=padded.tobytes(),header=SimpleNamespace(seq=i,stamp=SimpleNamespace(to_sec=lambda i=i:i/30))))
        return SimpleNamespace(unregister=lambda:None)
    bridge=SimpleNamespace(imgmsg_to_cv2=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('unnecessary color conversion')))
    bindings=SimpleNamespace(rospy=SimpleNamespace(Subscriber=subscribe),image_type=object,cv_bridge_factory=lambda:bridge)
    monkeypatch.setattr(ros_subscriber,'_load_ros_bindings',lambda:bindings)
    root=tmp_path/'native';video=ThreeCameraVideo(root,encoding='rawvideo',reserve_bytes=0)
    video.start();status=video.stop();assert status['state']=='saved'
    expected=image[:,:,::-1].copy().tobytes()*3
    for key in CAMERAS:
        assert status['cameras'][key]['input_pixel_format']=='rgb24'
        actual=subprocess.check_output(['ffmpeg','-v','error','-i',str(root/(key+'.avi')),'-threads','1','-f','rawvideo','-pix_fmt','bgr24','pipe:1'])
        assert actual==expected
