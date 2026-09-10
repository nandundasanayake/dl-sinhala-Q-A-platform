# services/redis_service.py
import redis
import json
from typing import Dict
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, STATUS_CACHE_TTL, ENABLE_REDIS_CACHE

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
        if ENABLE_REDIS_CACHE:
            print("[OK] Connected to Redis successfully!")
        else:
            print("[INFO] Redis connected, but Redis caching is TEMPORARILY DISABLED via ENABLE_REDIS_CACHE=false")
    except Exception as e:
        print(f"[WARN] Redis connection failed: {e}. Falling back to in-memory dictionary cache.")
        redis_client = None

def save_to_redis(key: str, value: dict, ttl_seconds: int = 3600):
    """Save data to Redis with expiration (disabled when ENABLE_REDIS_CACHE is False)"""
    if not ENABLE_REDIS_CACHE:
        return False
    if redis_client:
        try:
            redis_client.setex(key, ttl_seconds, json.dumps(value))
            return True
        except Exception as e:
            print(f"Redis save error: {e}")
    return False

def get_from_redis(key: str):
    """Get data from Redis (disabled when ENABLE_REDIS_CACHE is False)"""
    if not ENABLE_REDIS_CACHE:
        return None
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