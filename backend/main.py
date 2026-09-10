# app.py
import os
import re
import uuid
import hashlib
from typing import Dict, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from google.genai import types
from datetime import datetime
import urllib.parse

from config import UPLOAD_DIR, BUCKET_NAME, AWS_REGION, REDIS_DB, STATUS_CACHE_TTL, CHAT_CACHE_TTL, OPENSEARCH_HOST, OPENSEARCH_PORT, ENABLE_REDIS_CACHE
from services.redis_service import init_redis, save_to_redis, get_from_redis, redis_client, upload_statuses, chat_response_cache
from services.opensearch_service import init_opensearch, setup_opensearch_index, get_opensearch_client, opensearch_client, INDEX_NAME
from services.s3_service import s3_client
from services.gemini_service import client as gemini_client, get_chat_system_prompt, get_rewrite_prompt_template, get_query_embedding
from services.video_processor import process_video_background, generate_and_upload_thumbnail
from utils.helpers import get_video_duration_seconds
from prompts.Roadmap_prompt import ROADMAP_KEYWORDS, ROADMAP_HEADER, ROADMAP_CHAPTER_BULLET, ROADMAP_SUBTOPIC_BULLET, ROADMAP_VERTICAL_CONNECTOR, ROADMAP_CLOSING_MESSAGE, ROADMAP_NOT_FOUND_MESSAGE
from models.schemas import ChatMessage, ChatRequest, ProcessVideoRequest

# Initialize services
init_redis()
init_opensearch()
setup_opensearch_index()

# Create upload directory
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize FastAPI
app = FastAPI(title="Enterprise Video RAG API", version="3.0")

# Middleware
@app.middleware("http")
async def add_ngrok_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://dl-sinhala-q-a-platform.vercel.app",
        "https://intimidatory-divergently-yen.ngrok-free.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ API ENDPOINTS ============

@app.get("/")
async def root():
    return {"status": "healthy"}

@app.get("/api/upload-status/{video_id}")
async def get_upload_status(video_id: str):
    status = get_from_redis(f"video_status:{video_id}")
    if status:
        return status

    if video_id in upload_statuses:
        status_data = upload_statuses[video_id]
        if status_data.get("status") == "completed":
            return status_data

    # Fail-safe check: If transcript file already exists on S3, mark completed
    transcript_key = f"transcripts/{video_id}.txt"
    try:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
        video_s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video_id}"
        transcript_s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{transcript_key}"
        thumbnail_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/thumbnails/{video_id}.jpg"
        display_name = video_id.split("---")[-1] if "---" in video_id else video_id
        original_title = display_name.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title()

        formatted_duration = "00:00"
        if opensearch_client:
            try:
                res = opensearch_client.search(
                    index=INDEX_NAME,
                    body={"query": {"term": {"video_id": video_id}}, "size": 1, "_source": ["duration"]}
                )
                if res.get('hits', {}).get('hits'):
                    formatted_duration = res['hits']['hits'][0]['_source'].get('duration', '00:00')
            except Exception:
                pass

        if formatted_duration in ["00:00", "0:00"]:
            try:
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
                    ExpiresIn=3600
                )
                duration_sec = get_video_duration_seconds(presigned_url)
                if duration_sec > 0:
                    hours = int(duration_sec // 3600)
                    minutes = int((duration_sec % 3600) // 60)
                    seconds = int(duration_sec % 60)
                    formatted_duration = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
            except Exception as e:
                print(f"⚠️ Could not extract duration in status endpoint: {e}")

        completed_data = {
            "status": "completed",
            "message": "Processing complete!",
            "progress": 100,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "video_s3_url": video_s3_url,
                "transcript_s3_url": transcript_s3_url,
                "duration": formatted_duration,
                "thumbnail_url": thumbnail_url,
                "original_title": original_title
            }
        }
        upload_statuses[video_id] = completed_data
        return completed_data
    except Exception:
        pass

    if video_id not in upload_statuses:
        raise HTTPException(status_code=404, detail="Status not found")
    return upload_statuses[video_id]

@app.get("/api/generate-upload-url")
async def generate_upload_url(filename: str):
    # Keep original filename for display purposes
    original_filename = filename

    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename.replace(" ", "_"))
    unique_id = str(uuid.uuid4())[:8]
    video_id = f"{unique_id}---{safe_filename}"
    
    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
            ExpiresIn=21600
        )
        return {"upload_url": presigned_url, "video_id": video_id, "original_filename": original_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-video")
async def process_video(request: ProcessVideoRequest, background_tasks: BackgroundTasks):
    try:
        initial_status = {
            "status": "starting", "message": "Starting processing...", "progress": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        if not save_to_redis(f"video_status:{request.video_id}", initial_status, ttl_seconds=STATUS_CACHE_TTL):
            upload_statuses[request.video_id] = initial_status
        
        background_tasks.add_task(process_video_background, request.video_id, request.original_title, request.transcription_mode or "video")
        print(f"[PROCESS] Processing started for {request.video_id} | Mode: {request.transcription_mode}")
        return {"status": "processing", "video_id": request.video_id, "message": "Processing started", "transcription_mode": request.transcription_mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    print("\n" + "="*70)
    print("[CHAT] CHAT REQUEST RECEIVED")
    print("="*70)
    print(f"   Video ID: {request.video_id}")
    print(f"   Question: {request.question}")
    print(f"   Chat History Length: {len(request.chat_history)} messages")
    try:
        # ROADMAP INTERCEPTION
        question_lower = request.question.lower()
        
        if any(keyword in question_lower for keyword in ROADMAP_KEYWORDS):
            print("\n[ROADMAP] ROADMAP REQUEST DETECTED - Checking transcript...")
            
            # Fetch transcript from S3
            transcript_key = f"transcripts/{request.video_id}.txt"
            try:
                transcript_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=transcript_key)
                transcript_text = transcript_obj['Body'].read().decode('utf-8')
                
                # Check if roadmap exists in transcript
                if "=== VIDEO ROADMAP ===" in transcript_text:
                    print("[OK] Roadmap found in transcript - Serving directly")
                    roadmap_section = transcript_text.split("=== VIDEO ROADMAP ===")[1].strip()
                    
                    try:
                        import json
                        roadmap_json = json.loads(roadmap_section)
                        
                        # Handle wrapping: extract list from dict or use directly
                        if isinstance(roadmap_json, dict):
                            roadmap_list = roadmap_json.get("roadmap") or roadmap_json.get("chapters") or []
                        elif isinstance(roadmap_json, list):
                            roadmap_list = roadmap_json
                        else:
                            roadmap_list = []
                        
                        # Build vertical timeline roadmap
                        formatted_text = f"{ROADMAP_HEADER}\n\n"
                        
                        for idx, item in enumerate(roadmap_list, 1):
                            chapter_title = (
                                item.get("chapter_title") or 
                                item.get("title") or 
                                item.get("topic") or 
                                item.get("chapter") or 
                                f"Chapter {idx}"
                            )
                            
                            formatted_text += f"{ROADMAP_CHAPTER_BULLET} **{idx:02d}. {chapter_title}**\n"
                            
                            sub_topics = item.get("sub_topics", []) or item.get("subtopics", [])
                            if isinstance(sub_topics, list):
                                for sub in sub_topics:
                                    if isinstance(sub, str):
                                        sub_title = sub
                                    elif isinstance(sub, dict):
                                        sub_title = sub.get("title") or sub.get("topic") or sub.get("name") or ""
                                    else:
                                        continue
                                    
                                    if sub_title:
                                        formatted_text += f"{ROADMAP_SUBTOPIC_BULLET} {sub_title}\n"
                            
                            if idx < len(roadmap_list):
                                formatted_text += f"{ROADMAP_VERTICAL_CONNECTOR}\n"
                        
                        formatted_text += ROADMAP_CLOSING_MESSAGE
                        
                        async def roadmap_stream():
                            yield formatted_text
                        
                        return StreamingResponse(roadmap_stream(), media_type='text/plain')
                    except Exception as parse_e:
                        print(f"[WARN] Roadmap parsing failed: {parse_e}")
                else:
                    print("[INFO] Roadmap not found in transcript")
            except Exception as e:
                print(f"[WARN] Could not fetch transcript: {e}")
            
            async def no_roadmap_stream():
                yield ROADMAP_NOT_FOUND_MESSAGE
            return StreamingResponse(no_roadmap_stream(), media_type='text/plain')
        
        print("\n[CACHE] STEP 1: Checking Cache")
        history_str = "".join([m.content for m in request.chat_history[-2:]])
        raw_key = f"{request.video_id}_{request.question}_{history_str}"
        cache_key = hashlib.md5(raw_key.encode()).hexdigest()

        cached = get_from_redis(f"chat_cache:{cache_key}")
        print(f"Cache lookup for key: chat_cache:{cache_key} - {'HIT' if cached else 'MISS'}")
        if cached:
            print(f"[FAST] Returning from Redis Cache! Saved API cost for: {request.question}")
            async def cached_stream():
                yield cached.get("answer", "")
            return StreamingResponse(cached_stream(), media_type='text/plain')
        
        if cache_key in chat_response_cache:
            print(f"[FAST] Returning from Memory Cache! Saved API cost for: {request.question}")
            async def cached_stream():
                yield chat_response_cache[cache_key]
            return StreamingResponse(cached_stream(), media_type='text/plain')

        if not request.chat_history:
            search_query_text = request.question
            print(f"   [INFO] First question in chat session - skipping question rewrite")
        else:
            history_text = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history[-2:]])
            print(f"   History text: {history_text[:100]}...")
            rewrite_template = get_rewrite_prompt_template()
            rewrite_prompt = rewrite_template.format(history_text=history_text, question=request.question)
            print(f"   Rewrite prompt created (length: {len(rewrite_prompt)} chars)")
            rewritten_q = gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite", contents=rewrite_prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            search_query_text = rewritten_q.text.strip()
            print(f"   [OK] Rewritten query: {search_query_text}")

        vector = get_query_embedding(search_query_text)
        print(f"   [OK] Embedding ready (dimensions: {len(vector)})")
        
        search_query = {
            "size": 10,
            "query": {
                "bool": {
                    "filter": [{"term": {"video_id": request.video_id}}],
                    "should": [
                        {"knn": {"embedding": {"vector": vector, "k": 10}}},
                        {"match": {"text_chunk": {"query": search_query_text, "boost": 2.0}}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }

        os_client = get_opensearch_client()
        context = "Context unavailable."
        if os_client:
            try:
                res = os_client.search(index=INDEX_NAME, body=search_query)
                context = "\n---\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
                print(f"   [OK] OpenSearch returned {len(res['hits']['hits'])} chunks")
                print(f"   Context length: {len(context)} chars")
            except Exception as e:
                print(f"   [WARN] OpenSearch search error: {e}")
        else:
            print(f"   [WARN] OpenSearch client not available")

        system_instr = get_chat_system_prompt()
        print(f"   System instruction loaded (length: {len(system_instr)} chars)")

        formatted_contents = []
        for msg in request.chat_history:
            role = "user" if msg.role == "user" else "model"
            formatted_contents.append({"role": role, "parts": [{"text": msg.content}]})
            
        final_prompt = f"Video Context:\n{context}\n\nUser Question: {request.question}"
        formatted_contents.append({"role": "user", "parts": [{"text": final_prompt}]})
        
        async def generate_stream():
            full_response = ""
            chunk_count = 0
            for chunk in gemini_client.models.generate_content_stream(
                model="gemini-2.5-flash-lite", 
                contents=formatted_contents, 
                config=types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
            ):
                if chunk.text:
                    full_response += chunk.text
                    chunk_count += 1
                    yield chunk.text

            print(f"   [OK] Stream completed: {chunk_count} chunks, {len(full_response)} characters total")

            if not save_to_redis(f"chat_cache:{cache_key}", {
                "answer": full_response,
                "timestamp": datetime.utcnow().isoformat()
            }, ttl_seconds=CHAT_CACHE_TTL):
                chat_response_cache[cache_key] = full_response
                print(f"   [OK] Answer saved to Memory cache")
            else:
                print(f"   [OK] Answer saved to Redis cache (TTL: {CHAT_CACHE_TTL} seconds)")
                    
        return StreamingResponse(generate_stream(), media_type='text/plain')
        
    except Exception as e:
        print(f"\n❌ CHAT REQUEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("="*70 + "\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/clear/{video_id}")
async def clear_chat_cache(video_id: str):
    try:
        message = ""
        cleared_count = len(chat_response_cache)
        chat_response_cache.clear()
        message = f"Memory cache cleared. {cleared_count} entries removed."
        
        if redis_client:
            try:
                keys = redis_client.keys("chat_cache:*")
                for key in keys:
                    redis_client.delete(key)
                message += f" Redis chat cache cleared. {len(keys)} keys removed."
            except Exception as e:
                message += f" Could not clear Redis cache: {e}"
            
        return {"status": "success", "message": message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    redis_status = "connected" if redis_client and redis_client.ping() else "disconnected"
    return {
        "status": "healthy",
        "redis": redis_status,
        "redis_db": REDIS_DB,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/videos")
async def list_videos():
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="videos/")
        videos = []

        # Get titles and durations from OpenSearch
        title_map = {}
        duration_map = {}
        if opensearch_client:
            try:
                search = {
                    "size": 0,
                    "aggs": {
                        "videos": {
                            "terms": {"field": "video_id", "size": 100},
                            "aggs": {
                                "latest_data": {
                                    "top_hits": {
                                        "size": 1,
                                        "_source": ["original_title", "duration"]
                                    }
                                }
                            }
                        }
                    }
                }
                result = opensearch_client.search(index=INDEX_NAME, body=search)
                for bucket in result['aggregations']['videos']['buckets']:
                    if bucket.get('latest_data', {}).get('hits', {}).get('hits'):
                        source = bucket['latest_data']['hits']['hits'][0]['_source']
                        title_map[bucket['key']] = source.get('original_title', '')
                        duration_map[bucket['key']] = source.get('duration', '0:00')
            except Exception as e:
                print(f"Warning: Could not fetch data from OpenSearch: {e}")

        if 'Contents' in response:
            for obj in response['Contents']:
                video_key = obj['Key']
                video_filename = video_key.replace('videos/', '')
                
                video_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video_key}"
                
                transcript_key = f"transcripts/{video_filename}.txt"
                try:
                    s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
                    transcript_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{transcript_key}"
                except:
                    transcript_url = None
                
                thumbnail_s3_key = f"thumbnails/{video_filename}.jpg"
                thumbnail_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
                
                # Get title and duration from OpenSearch
                title = title_map.get(video_filename)
                duration = duration_map.get(video_filename, '0:00')
                if not duration or duration in ['0:00', '00:00']:
                    if video_filename in upload_statuses and upload_statuses[video_filename].get('data', {}).get('duration'):
                        duration = upload_statuses[video_filename]['data']['duration']
                
                # Fallback to extracting from filename if no title in OpenSearch
                if not title:
                    display_name = video_filename.split("---")[-1] if "---" in video_filename else video_filename
                    title = display_name.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title()

                videos.append({
                    "id": video_filename, 
                    "video_id": video_filename,
                    "title": title,
                    "video_url": video_url, 
                    "transcript_url": transcript_url,
                    "thumbnail_url": thumbnail_url, 
                    "duration": duration,
                    "uploaded_at": obj['LastModified'].isoformat(), "file_size": obj['Size']
                })
        
        videos.sort(key=lambda x: x['uploaded_at'], reverse=True)
        return {"status": "success", "videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    try:
        video_id = urllib.parse.unquote(video_id)
        video_key = f"videos/{video_id}"
        video_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video_key}"
        
        try:
            response = s3_client.head_object(Bucket=BUCKET_NAME, Key=video_key)
        except:
            raise HTTPException(status_code=404, detail="Video not found")
        
        transcript_key = f"transcripts/{video_id}.txt"
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
            transcript_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{transcript_key}"
        except: 
            transcript_url = None
        
        thumbnail_filename = f"{video_id.replace('.mp4', '')}.jpg"
        thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
        
        display_name = video_id.split("---")[-1] if "---" in video_id else video_id
        title = display_name.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title()
        
        return {"status": "success", "video": {
            "id": video_id, "video_id": video_id,
            "title": title,
            "video_url": video_url, "transcript_url": transcript_url,
            "thumbnail_url": thumbnail_url, "uploaded_at": response['LastModified'].isoformat(),
            "file_size": response['ContentLength']
        }}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    try:
        video_id = urllib.parse.unquote(video_id)
        
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"videos/{video_id}")
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"thumbnails/{video_id}.jpg")
        try: 
            s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"transcripts/{video_id}.txt")
        except: pass
        
        try:
            opensearch_client.delete_by_query(index=INDEX_NAME, body={"query": {"term": {"video_id": video_id}}})
        except: pass
        
        return {"status": "success", "message": "Video deleted"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/thumbnail/{video_id:path}")
async def get_thumbnail(video_id: str):
    try:
        video_id = urllib.parse.unquote(video_id)
        thumbnail_filename = video_id.replace('.mp4', '.jpg')
        thumbnail_path = os.path.join("static", "thumbnails", thumbnail_filename)
        
        if not os.path.exists(thumbnail_path):
            raise HTTPException(status_code=404, detail="Thumbnail not found")
            
        return FileResponse(thumbnail_path, media_type="image/jpeg", headers={
            "ngrok-skip-browser-warning": "true", "Cache-Control": "public, max-age=3600"
        })
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/redis/keys")
async def list_redis_keys():
    if not redis_client:
        return {"error": "Redis not connected"}
    
    keys = redis_client.keys("*")
    result = {}
    
    for key in keys[:50]:
        key_type = key.split(":")[0] if ":" in key else "other"
        if key_type not in result:
            result[key_type] = []
        
        value = redis_client.get(key)
        if value and len(str(value)) > 200:
            value = str(value)[:200] + "..."
        
        result[key_type].append({
            "key": key,
            "ttl": redis_client.ttl(key),
            "value_preview": value
        })
    
    return {"total_keys": len(keys), "keys": result}

# Then in your debug endpoint:
@app.get("/api/debug/opensearch")
async def debug_opensearch():
    """Debug: See what's in OpenSearch"""
    client = get_opensearch_client()
    if not client:
        return {"error": "OpenSearch not connected"}
    
    try:
        response = client.search(
            index=INDEX_NAME,
            body={
                "size": 0,
                "aggs": {
                    "unique_videos": {
                        "terms": {"field": "video_id", "size": 100}
                    }
                }
            }
        )
        
        videos = []
        for bucket in response['aggregations']['unique_videos']['buckets']:
            videos.append({
                "video_id": bucket['key'],
                "chunk_count": bucket['doc_count']
            })
        
        sample = client.search(
            index=INDEX_NAME,
            body={"size": 1}
        )
        
        return {
            "videos_in_opensearch": videos,
            "total_chunks": response['hits']['total']['value'],
            "sample_document": sample['hits']['hits'][0]['_source'] if sample['hits']['hits'] else None
        }
    except Exception as e:
        return {"error": str(e)}
    
@app.get("/api/debug/opensearch-status")
async def debug_opensearch_status():
    """Check OpenSearch client status"""
    return {
        "opensearch_client_is_none": opensearch_client is None,
        "opensearch_client_type": str(type(opensearch_client)),
        "INDEX_NAME": INDEX_NAME,
        "host": OPENSEARCH_HOST,
        "port": OPENSEARCH_PORT
    }