# services/redis_service.py
import redis
import json
from typing import Dict
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, STATUS_CACHE_TTL

# Global variables (kept for compatibility)
redis_client = None
upload_statuses: Dict[str, Dict] = {}
chat_response_cache: Dict[str, str] = {}

def init_redis():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, 
            port=REDIS_PORT,
            db=REDIS_DB, 
            decode_responses=True,
            socket_connect_timeout=5
        )
        redis_client.ping()
        print("✅ Connected to Redis successfully!")
    except Exception as e:
        print(f"⚠️ Redis connection failed: {e}. Falling back to in-memory dictionary cache.")
        redis_client = None

def save_to_redis(key: str, value: dict, ttl_seconds: int = 3600):
    """Save data to Redis with expiration"""
    if redis_client:
        try:
            redis_client.setex(key, ttl_seconds, json.dumps(value))
            return True
        except Exception as e:
            print(f"Redis save error: {e}")
    return False

def get_from_redis(key: str):
    """Get data from Redis"""
    if redis_client:
        try:
            data = redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"Redis get error: {e}")
    return None

def delete_from_redis(key: str):
    """Delete data from Redis"""
    if redis_client:
        try:
            redis_client.delete(key)
        except Exception as e:
            print(f"Redis delete error: {e}")