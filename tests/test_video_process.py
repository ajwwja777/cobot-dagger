import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from capture_core.video_process import ProcessVideo,run_worker


@pytest.fixture
def child(tmp_path):
    script=tmp_path/'child.py'
    script.write_text("""import argparse,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root');p.add_argument('--worker-id');p.add_argument('--metadata');p.add_argument('--reserve-bytes');a=p.parse_args()
root=Path(a.root);root.mkdir();meta=json.loads(a.metadata);status=root/'video-worker.json'
def write(state,complete=False,error=None):
 value={'worker_id':a.worker_id,'worker_pid':os.getpid(),'worker_complete':complete,'state':state,'error':error,'directory':str(root),'cameras':{'camera_left':{'frames':42}}}
 temp=root/'pending';temp.write_text(json.dumps(value));temp.replace(status)
if meta.get('fail'):
 write('error',True,'synthetic startup failure');raise SystemExit(1)
write('recording');line=input();write('saved',True)
""")
    return script


def make_proxy(tmp_path,child,metadata=None):
    video=ProcessVideo(tmp_path/'archive',metadata=metadata,reserve_bytes=0)
    command=video._command();video._command=lambda:[sys.executable,'-u',str(child)]+command[4:]
    return video


def test_real_child_handshake_and_clean_single_stop_without_ros(tmp_path,child):
    video=make_proxy(tmp_path,child)
    try:
        result=video.start();assert result['worker_pid']!=os.getpid() and result['state']=='recording'
        assert video.process.poll() is None
        saved=video.stop();assert saved['state']=='saved' and saved['worker_complete']
        assert video.process.poll()==0 and video.stop()==saved
    finally:
        if video.process and video.process.poll() is None:video.stop()


def test_startup_error_is_returned_and_child_is_reaped(tmp_path,child):
    video=make_proxy(tmp_path,child,{'fail':True})
    with pytest.raises(RuntimeError,match='synthetic startup failure'):video.start()
    value=video.stop();assert value['state']=='error' and video.process.poll() is not None


@pytest.mark.parametrize('control,expected',[('stop\n','saved'),('','error')])
def test_worker_owns_ros_initialization_and_eof_finalizes(tmp_path,monkeypatch,control,expected):
    import capture_core.ros_subscriber as subscriber
    import capture_core.uncompressed_video as module
    ros=SimpleNamespace(init_node=Mock(),signal_shutdown=Mock())
    monkeypatch.setattr(subscriber,'_load_ros_bindings',lambda:SimpleNamespace(rospy=ros))
    class Video:
        def __init__(self,root,**kw):self.root=root;self.error=None
        def start(self):self.root.mkdir()
        def status(self):return {'state':'recording','directory':str(self.root)}
        def stop(self):return {'state':'error' if self.error else 'saved','error':self.error,'directory':str(self.root)}
    monkeypatch.setattr(module,'ThreeCameraVideo',Video);monkeypatch.setattr(sys,'stdin',io.StringIO(control))
    args=SimpleNamespace(root=str(tmp_path/'archive'),worker_id='identity',metadata='{}',reserve_bytes=0)
    code=run_worker(args);status=json.loads((Path(args.root)/'video-worker.json').read_text())
    assert status['state']==expected and status['worker_complete'] and status['worker_id']=='identity'
    assert code==(0 if expected=='saved' else 1)
    ros.init_node.assert_called_once();ros.signal_shutdown.assert_called_once()


def test_existing_archive_cannot_be_reused_or_overwritten(tmp_path):
    root=tmp_path/'existing';root.mkdir();(root/'keep').write_text('data')
    with pytest.raises(ValueError):ProcessVideo(root).start()
    assert (root/'keep').read_text()=='data'


def test_one_failed_camera_does_not_end_healthy_camera_recordings():
    from capture_core.video_process import has_recording_camera
    assert has_recording_camera({'state':'error','cameras':{
        'left':{'frames':40,'error':None},'right':{'error':'queue full'}}})
    assert not has_recording_camera({'state':'error','cameras':{'right':{'error':'disk full'}}})


def test_live_encoder_falls_back_when_hardware_unavailable(monkeypatch):
    import subprocess
    from capture_core.video_encoding import select_live_encoder,live_encoding_args
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1))
    assert select_live_encoder()=='libx264'
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0))
    assert select_live_encoder()=='h264_nvenc'
    assert 'h264_nvenc' in live_encoding_args('h264_nvenc')
    assert 'libx264' in live_encoding_args('libx264')
