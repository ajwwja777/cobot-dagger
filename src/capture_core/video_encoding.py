"""Shared CPU/browser recording profile: H.264/yuv420p MP4, at most 1080p."""
# Even dimensions, preserve aspect ratio, never upscale a smaller source.
SCALE = "scale=w='trunc(iw*min(1,min(1920/iw,1080/ih))/2)*2':h='trunc(ih*min(1,min(1920/iw,1080/ih))/2)*2'"

def browser_encoding_args():
    return ["-filter_threads", "1", "-vf", SCALE, "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "14",
            "-profile:v", "main", "-level:v", "4.1", "-pix_fmt", "yuv420p",
            "-threads", "2", "-g", "60", "-movflags", "+faststart", "-f", "mp4"]
