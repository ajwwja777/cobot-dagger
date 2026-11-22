"""Shared CPU/browser recording profile: H.264/yuv420p MP4, at most 1080p."""
# Even dimensions, preserve aspect ratio, never upscale a smaller source.
SCALE = "scale=w='trunc(iw*min(1,min(1920/iw,1080/ih))/2)*2':h='trunc(ih*min(1,min(1920/iw,1080/ih))/2)*2'"

def browser_encoding_args():
    return ["-filter_threads", "1", "-vf", SCALE, "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "14",
            "-profile:v", "main", "-level:v", "4.1", "-pix_fmt", "yuv420p",
            "-threads", "2", "-g", "60", "-movflags", "+faststart", "-f", "mp4"]


def live_encoding_args(encoder):
    if encoder == "h264_nvenc":
        return ["-filter_threads", "1", "-vf", SCALE, "-c:v", "h264_nvenc",
                "-preset", "fast", "-rc", "constqp", "-qp", "18", "-bf", "0",
                "-pix_fmt", "yuv420p", "-g", "60", "-movflags", "+faststart", "-f", "mp4"]
    return browser_encoding_args()


def select_live_encoder():
    """Probe actual hardware support once per archive, before subscribing."""
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=s=320x240:r=30", "-frames:v", "1",
            "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if result.returncode == 0:
            return "h264_nvenc"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "libx264"
