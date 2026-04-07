# utils/helpers.py
import subprocess
from config import FFPROBE_CMD

def get_video_duration_seconds(video_url):
    """Get raw video duration in seconds using ffprobe from the remote URL."""
    try:
        result = subprocess.run(
            [FFPROBE_CMD, "-v", "error", "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", video_url],
            capture_output=True, text=True, timeout=60
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"⚠️ Could not get video duration: {e}")
        return 0