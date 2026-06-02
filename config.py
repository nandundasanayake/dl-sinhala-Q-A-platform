# config.py
import os
import platform
from dotenv import load_dotenv

load_dotenv()

# Cross-platform FFmpeg paths
FFMPEG_CMD = "ffmpeg" if platform.system() == "Windows" else "/usr/bin/ffmpeg"
FFPROBE_CMD = "ffprobe" if platform.system() == "Windows" else "/usr/bin/ffprobe"

# Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in environment variables.")

# AWS OpenSearch Configuration
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 443))
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASS = os.getenv("OPENSEARCH_PASS", "admin")
INDEX_NAME = "video-transcripts-v2"

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # Used for OpenSearch
S3_REGION = os.getenv("S3_REGION", "eu-north-1")  # Dedicated region for S3 buckets
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Input bucket for videos
OUTPUT_BUCKET_NAME = os.getenv("S3_OUTPUT_BUCKET_NAME") # Output bucket for transcripts/thumbnails

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Cache TTL constants
CHAT_CACHE_TTL = int(os.getenv("CHAT_CACHE_TTL", 604800))   # 7 days
STATUS_CACHE_TTL = int(os.getenv("STATUS_CACHE_TTL", 7200))  # 2 hours
EMBEDDING_CACHE_TTL = int(os.getenv("EMBEDDING_CACHE_TTL", 7200))  # 2 hours

# Directories
UPLOAD_DIR = "temp_uploads"