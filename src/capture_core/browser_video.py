"""Offline, CPU-only browser copies of finalized legacy camera AVI archives."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from .storage import _reject_symlink_components
from .video_encoding import browser_encoding_args
from .uncompressed_video import atomic_json, CAMERAS


def sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):digest.update(block)
    return digest.hexdigest()


def convert_archive(folder):
    folder=Path(folder).absolute();_reject_symlink_components(folder)
    manifest=folder/"video.json";_reject_symlink_components(manifest)
    value=json.loads(manifest.read_text())
    if value.get("state")!="saved" or value.get("uncompressed") is not True:
        raise ValueError("only finalized legacy AVI archives can be converted")
    marker=folder/"browser-video.json";_reject_symlink_components(marker)
    lock=folder/".browser-video.lock";_reject_symlink_components(lock)
    with lock.open("a") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=json.loads(marker.read_text()) if marker.exists() else {"format":"mp4","cameras":{}}
        for key in CAMERAS:
            camera=value.get("cameras",{}).get(key,{})
            if camera.get("file")!=key+".avi":raise ValueError("invalid legacy camera file")
            source=folder/(key+".avi");_reject_symlink_components(source)
            before=source.stat();output=folder/(key+".mp4");_reject_symlink_components(output)
            previous=result["cameras"].get(key,{})
            if output.exists():
                if previous.get("source_bytes")==before.st_size and previous.get("source_mtime_ns")==before.st_mtime_ns and previous.get("sha256")==sha256(output):continue
                raise ValueError("existing MP4 is not a verified copy; refusing overwrite")
            original_sha=sha256(source)
            temporary=folder/(key+"."+uuid4().hex+".pending.mp4")
            try:
                subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-n","-threads","1","-i",str(source),"-map","0:v:0","-an"]+browser_encoding_args()+[str(temporary)],check=True,timeout=3600)
                probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(temporary)]))["streams"][0]
                if probe.get("codec_name")!="h264" or probe.get("pix_fmt")!="yuv420p" or probe["width"]>1920 or probe["height"]>1080:raise ValueError("invalid browser encoding")
                if int(probe["nb_read_frames"])!=int(camera["frames"]):raise ValueError("converted frame count mismatch")
                after=source.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or sha256(source)!=original_sha:raise ValueError("source changed during conversion")
                output_sha=sha256(temporary);os.replace(temporary,output)
                result["cameras"][key]={"file":output.name,"codec":"h264","pixel_format":"yuv420p","width":probe["width"],"height":probe["height"],"frames":int(probe["nb_read_frames"]),"bytes":output.stat().st_size,"sha256":output_sha,"source_bytes":before.st_size,"source_mtime_ns":before.st_mtime_ns,"source_sha256":original_sha}
                atomic_json(marker,result)
                print(json.dumps({"directory":str(folder),"camera":key,**result["cameras"][key]}),flush=True)
            finally:
                if temporary.exists():temporary.unlink()
        return result
