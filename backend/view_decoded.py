import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Get the cached key
key = "chat_cache:0002417afa256b9b9a8a62cbf06bab78"
value = r.get(key)

if value:
    data = json.loads(value)
    print("=" * 70)
    print("CACHED CHAT RESPONSE")
    print("=" * 70)
    print(f"\n📝 Answer:\n{data.get('answer', 'N/A')}")
    print(f"\n⏰ Timestamp: {data.get('timestamp', 'N/A')}")
    print(f"\n🔑 Key: {key}")
    print(f"⏱️ TTL: {r.ttl(key)} seconds remaining")