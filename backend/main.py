import redis
import os
import time
import subprocess
import math
import re
import uuid
from typing import Dict
import hashlib
import json  # ADDED for Redis
import boto3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from google import genai
import platform
from google.genai import types
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from pydantic import BaseModel
from typing import List
from datetime import datetime
import urllib.parse

# Cross-platform FFmpeg paths
FFMPEG_CMD = "ffmpeg" if platform.system() == "Windows" else "/usr/bin/ffmpeg"
FFPROBE_CMD = "ffprobe" if platform.system() == "Windows" else "/usr/bin/ffprobe"

# Load environment variables from the .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(title="Enterprise Video RAG API", version="3.0")

@app.middleware("http")
async def add_ngrok_header(request, call_next):
    """Adds ngrok-skip-browser-warning header to all responses"""
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

# Configure CORS to allow requests from the React frontend (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://dl-sinhala-q-a-platform.vercel.app", "https://intimidatory-divergently-yen.ngrok-free.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- External Services Configuration ---

# 1. Google Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in environment variables.")
client = genai.Client(api_key=GEMINI_API_KEY)

# 2. AWS OpenSearch Configuration
opensearch_client = OpenSearch(
    hosts=[{'host': os.getenv("OPENSEARCH_HOST", "localhost"), 'port': int(os.getenv("OPENSEARCH_PORT", 443))}],
    http_auth=(os.getenv("OPENSEARCH_USER", "admin"), os.getenv("OPENSEARCH_PASS", "admin")),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=60,
    max_retries=5,
    retry_on_timeout=True
)
INDEX_NAME = "video-transcripts-index"

# 3. AWS S3 Configuration for Cloud Storage
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1")
)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# 4. Redis Configuration (For Enterprise Caching)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Cache TTL constants (using their 7 days for production)
CHAT_CACHE_TTL = int(os.getenv("CHAT_CACHE_TTL", 604800))  # 7 days default
STATUS_CACHE_TTL = int(os.getenv("STATUS_CACHE_TTL", 7200))  # 2 hours
EMBEDDING_CACHE_TTL = int(os.getenv("EMBEDDING_CACHE_TTL", 7200))  # 2 hours

try:

    redis_client = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT,
        db=REDIS_DB, 
        password=REDIS_PASSWORD, 
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()
    print("✅ Connected to Redis successfully!")
except Exception as e:
    print(f"⚠️ Redis connection failed: {e}. Falling back to in-memory dictionary cache.")
    redis_client = None

# Fallback in-memory cache
upload_statuses: Dict[str, Dict] = {}
chat_response_cache: Dict[str, str] = {}
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --- Helper Functions ---

# NEW: Redis helper functions (ADDED)
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

def setup_opensearch_index():
    """Ensures the OpenSearch index exists and is configured for k-NN vector search."""
    try:
        if not opensearch_client.indices.exists(index=INDEX_NAME):
            index_body = {
                "settings": {"index.knn": True},
                "mappings": {
                    "properties": {
                        "video_id": {"type": "keyword"},
                        "timestamp": {"type": "text"},
                        "text_chunk": {"type": "text"},
                        "video_s3_url": {"type": "keyword"},
                        "transcript_s3_url": {"type": "keyword"},
                        "duration": {"type": "keyword"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 768
                        }
                    }
                }
            }
            opensearch_client.indices.create(index=INDEX_NAME, body=index_body)
            print(f"✅ Created OpenSearch Index: {INDEX_NAME}")
    except Exception as e:
        print(f"⚠️ OpenSearch Connection Warning: {e}")

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

def generate_and_upload_thumbnail(video_url, video_id, time_offset=5):
    """Generates a thumbnail from the video URL using FFmpeg and uploads it directly to S3."""
    try:
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"
        
        # Return existing URL if already in S3
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=thumbnail_s3_key)
            return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
        except:
            pass
        
        # Create a temporary file for the thumbnail
        temp_jpg = os.path.join(UPLOAD_DIR, f"{video_id}_thumb.jpg")
        
        # Use FFmpeg to extract a frame from the remote video URL
        subprocess.run([
            FFMPEG_CMD, "-y", "-ss", str(time_offset), "-i", video_url,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=320:180", temp_jpg
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        
        # Upload to S3
        with open(temp_jpg, 'rb') as f:
            s3_client.put_object(
                Bucket=BUCKET_NAME, 
                Key=thumbnail_s3_key,
                Body=f.read(), 
                ContentType='image/jpeg'
            )
        
        # Clean up temp file
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
    except Exception as e:
        print(f"⚠️ Could not generate thumbnail: {e}")
        # Clean up temp file on error
        temp_jpg = os.path.join(UPLOAD_DIR, f"{video_id}_thumb.jpg")
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        return None

def upload_file_to_s3(local_path, s3_file_key):
    """Uploads binary files (videos) to AWS S3."""
    try:
        s3_client.upload_file(local_path, BUCKET_NAME, s3_file_key)
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{s3_file_key}"
    except Exception as e:
        print(f"❌ S3 Video Upload Failed: {e}")
        return None

def upload_text_to_s3(text_content, s3_file_key):
    """Uploads raw transcript strings to AWS S3."""
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME, 
            Key=s3_file_key,
            Body=text_content.encode('utf-8'), 
            ContentType='text/plain'
        )
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{s3_file_key}"
    except Exception as e:
        print(f"❌ S3 Transcript Upload Failed: {e}")
        return None

def split_into_chunks(text, target_words=200, overlap_words=50):
    """
    Implements an advanced Semantic/Token-optimized chunking strategy.
    Groups sentences until a target word count (~200-300 tokens) is reached,
    maintaining a semantic overlap to preserve context between chunks.
    """
    
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        word_count = len(line.split())

        if current_word_count + word_count > target_words and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            
            # Semantic Overlap
            overlap_chunk = []
            overlap_count = 0
            for back_line in reversed(current_chunk):
                if overlap_count < overlap_words:
                    overlap_chunk.insert(0, back_line)
                    overlap_count += len(back_line.split())
                else:
                    break
            
            current_chunk = overlap_chunk
            current_word_count = overlap_count
        
        current_chunk.append(line)
        current_word_count += word_count
        i += 1
        
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        if chunk_text not in chunks:
            chunks.append(chunk_text)
            
    return chunks

def adjust_timestamps(transcript: str, offset_seconds: int) -> str:
    """Adjusts relative timestamps from Gemini, handling spaces and preventing double formatting."""
    
    # Clean up any weird double timestamps Gemini might have hallucinated 
    cleaned_transcript = re.sub(r'\]\s*\d{1,2}:\d{2}(?::\d{2})?\s*-\s*\d{1,2}:\d{2}(?::\d{2})?\s*', '] ', transcript)

    # Updated Regex to handle spaces inside brackets like [ 00:15 - 01:20 ]
    pattern = r'\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]'
    
    def time_to_seconds(time_str):
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return 0

    def seconds_to_time(total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"{m:02d}:{s:02d}"

    def replace_match(match):
        total_start_s = time_to_seconds(match.group(1)) + offset_seconds
        total_end_s = time_to_seconds(match.group(2)) + offset_seconds
        return f"[{seconds_to_time(total_start_s)} - {seconds_to_time(total_end_s)}]"

    return re.sub(pattern, replace_match, cleaned_transcript)

# Initialize OpenSearch
setup_opensearch_index()

# --- Data Models ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    video_id: str
    question: str
    chat_history: List[ChatMessage] = []

class ProcessVideoRequest(BaseModel):
    video_id: str

# --- Background Processing Logic (Chunking Large Videos) ---

def process_video_background(video_id: str):
    """Processes large videos in the background by streaming from S3 and splitting them into chunks to avoid memory and API limits."""
    
    def update_status(status, message, progress):
        """Helper function to update status - uses Redis if available, otherwise memory dict."""
        status_data = {
            "status": status,
            "message": message,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Try Redis first
        if not save_to_redis(f"video_status:{video_id}", status_data, ttl_seconds=STATUS_CACHE_TTL):
            # Fallback to memory dict
            upload_statuses[video_id] = status_data 
        print(f"[{video_id}] {status}: {message} ({progress}%)")
    
    try:
        # Status 1: UPLOADING
        # Initial status indicating the video is being processed and metadata is being extracted
        update_status("uploading", "Processing video from cloud storage...", 10)
        
        # Generate a pre-signed GET URL for reading the video from S3 (valid for 12 hours)
        video_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
            ExpiresIn=43200
        )
        
        # Construct the public S3 URL for storing in the database
        video_s3_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/videos/{video_id}"
        
        # Extract metadata using ffprobe with the presigned URL
        duration_sec = get_video_duration_seconds(video_url)
        
        # Calculate Hours, Minutes, and Seconds properly
        hours = int(duration_sec // 3600)
        minutes = int((duration_sec % 3600) // 60)
        seconds = int(duration_sec % 60)
        
        if hours > 0:
            formatted_duration = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            formatted_duration = f"{minutes}:{seconds:02d}"
        
        # Generate thumbnail using FFmpeg with the presigned URL
        thumbnail_url = generate_and_upload_thumbnail(video_url, video_id)

        # Status 2: UPLOADED 
        # The frontend UI expects "uploaded" to trigger the "Transcription Started" visual state
        update_status("uploaded", "Video uploaded, starting transcription...", 30)

        # CHUNKING LOGIC: Split video into 15-min chunks (900s)
        CHUNK_DURATION = 900  # 15 minutes in seconds
        total_parts = math.ceil(duration_sec / CHUNK_DURATION) if duration_sec > 0 else 1
        full_transcript = ""

        for i in range(total_parts):
            try:
                start_time = i * CHUNK_DURATION
                chunk_file = os.path.join(UPLOAD_DIR, f"{video_id}_part{i}.mp4")
                
                # Maintain the "uploaded" status for the frontend UI progress bar
                update_status("uploaded", f"Transcribing part {i+1} of {total_parts}...", 30 + int((i/total_parts)*40))
                
                # Fast-copy split using FFmpeg streaming directly from S3
                subprocess.run([
                    FFMPEG_CMD, "-y", "-i", video_url,
                    "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                    "-c", "copy", chunk_file
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Upload video chunk to Gemini File API
                video_file_gemini = client.files.upload(file=chunk_file)
                while video_file_gemini.state.name == "PROCESSING":
                    time.sleep(5)
                    video_file_gemini = client.files.get(name=video_file_gemini.name)

                prompt = """Provide a HIGHLY DETAILED, FULL transcript with timestamps in the ORIGINAL language spoken. 
                CRITICAL RULES:
                1. Format strictly as: [MM:SS - MM:SS] Text.
                2. Do NOT leave spaces inside the brackets (e.g., use [01:15 - 02:30], NOT [ 01:15 - 02:30 ]).
                3. Do NOT print the timestamp twice in a row. 
                4. Do NOT summarize or skip any spoken sentences.
                5. IGNORE ON-SCREEN TEXT: Do NOT transcribe any text or software menus visible on the video screen (e.g., "Annotation mode"). Focus ONLY on transcribing the spoken audio.
                6. PREVENT REPETITION LOOPS: If there is a long silence or background noise, DO NOT hallucinate or continuously repeat filler words like "හරි" (Hari) or "ඕකේ" (Okay). Just SKIP the silent segments completely."""
                
                # Retry mechanism (up to 3 times) to handle Gemini API transient errors
                max_retries = 3
                adjusted_transcript = ""
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[video_file_gemini, prompt]
                        )
                        raw_transcript = response.text
                        adjusted_transcript = adjust_timestamps(raw_transcript, int(start_time))
                        break  # Break out of the retry loop if transcription is successful
                    except Exception as api_e:
                        print(f"⚠️ Gemini API attempt {attempt+1} failed for part {i+1}: {api_e}")
                        time.sleep(15)  # Wait 15 seconds before the next API attempt

                # Append the generated transcript for this chunk to the main transcript
                if adjusted_transcript:
                    full_transcript += adjusted_transcript + "\n\n"
                else:
                    full_transcript += f"\n\n[⚠️ Error: Could not transcribe this section ({start_time//60} mins to {(start_time+CHUNK_DURATION)//60} mins)]\n\n"
                
                # Cleanup: Delete the file from Gemini and local server to save space
                try:
                    client.files.delete(name=video_file_gemini.name)
                except:
                    pass
                if os.path.exists(chunk_file):
                    os.remove(chunk_file)
                
                print(f"✅ Part {i+1} transcribed and cleaned up.")
                
                # Add a 10-second delay between chunks to prevent Gemini API Rate Limits (429 Too Many Requests)
                time.sleep(10)

            except Exception as chunk_e:
                print(f"❌ Critical error in part {i+1}: {chunk_e}")
                full_transcript += f"\n\n[⚠️ Critical Error skipping section ({start_time//60} mins)]\n\n"
                # Prevent the entire system from crashing; gracefully skip to the next video chunk
                continue

        # Status 3: TRANSCRIPT_GENERATED
        # The frontend UI expects "transcript_generated" to trigger the "Embedding Started" visual state
        update_status("transcript_generated", "Transcript generated, embedding and saving...", 80)
        
        # Save the combined full transcript to AWS S3
        transcript_s3_url = upload_text_to_s3(full_transcript, f"transcripts/{video_id}.txt")
        
        # Chunk the full text and index to OpenSearch for RAG (Retrieval-Augmented Generation)
        text_chunks = split_into_chunks(full_transcript)
        for chunk in text_chunks:
            if not chunk.strip(): continue
            enriched_content = f"Video Source: {video_id}\nContent: {chunk}"
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001", contents=enriched_content,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768)
                )
                vector = result.embeddings[0].values
                if vector:
                    opensearch_client.index(index=INDEX_NAME, body={
                        "video_id": video_id, 
                        "text_chunk": chunk,
                        "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
                        "video_s3_url": video_s3_url, 
                        "transcript_s3_url": transcript_s3_url,
                        "duration": formatted_duration, 
                        "embedding": vector
                    })
            except Exception as e:
                # Skip failed text chunks silently to ensure the main process continues
                pass 

        # Status 4: COMPLETED
        # Final status to tell the frontend that the video is fully processed and ready to be viewed
        completed_data = {
            "status": "completed",
            "message": "Processing complete! Video ready.",
            "progress": 100,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "video_s3_url": video_s3_url, "transcript_s3_url": transcript_s3_url,
                "thumbnail_url": thumbnail_url, "duration": formatted_duration
            }
        }
        
        # Try Redis first for final status
        if not save_to_redis(f"video_status:{video_id}", completed_data, ttl_seconds=STATUS_CACHE_TTL):
            # Fallback to memory dict
            upload_statuses[video_id] = completed_data
            
    except Exception as e:
        print(f"Error during processing: {e}")
        update_status("error", f"Processing failed: {str(e)}", 0)


# --- API Endpoints ---

@app.get("/")
async def root():
    return {"status": "healthy"}

@app.get("/api/upload-status/{video_id}")
async def get_upload_status(video_id: str):
    """Returns the current background processing status for a given video."""
    # Try Redis first
    status = get_from_redis(f"video_status:{video_id}")
    if status:
        return status
    
    # Fallback to memory dict
    if video_id not in upload_statuses:
        raise HTTPException(status_code=404, detail="Status not found")
    return upload_statuses[video_id]

@app.get("/api/generate-upload-url")
async def generate_upload_url(filename: str):
    """Generates a pre-signed URL for direct-to-S3 uploads."""
    # Sanitize filename and generate unique video_id
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename.replace(" ", "_"))
    unique_id = str(uuid.uuid4())[:8]
    video_id = f"{unique_id}---{safe_filename}"
    
    try:
        # Generate pre-signed PUT URL for direct upload to S3 (6 hours for large files)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
            ExpiresIn=21600
        )
        
        return {"upload_url": presigned_url, "video_id": video_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-video")
async def process_video(request: ProcessVideoRequest, background_tasks: BackgroundTasks):
    """Triggers the background processing task for a video already uploaded to S3."""
    try:
        initial_status = {
            "status": "starting", "message": "Starting processing...", "progress": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Try Redis first
        if not save_to_redis(f"video_status:{request.video_id}", initial_status, ttl_seconds=STATUS_CACHE_TTL):
            # Fallback to memory dict
            upload_statuses[request.video_id] = initial_status
        
        # Add the heavy processing task to the background queue (no file_path needed)
        background_tasks.add_task(process_video_background, request.video_id)
        return {"status": "processing", "video_id": request.video_id, "message": "Processing started"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """Retrieves relevant context via Vector Search and generates a tailored response using Gemini Flash Lite with conversational memory, Redis Caching, and Streaming."""
    try:
        # 1. CHECK CACHE (REDIS OR IN-MEMORY FALLBACK)
        history_str = "".join([m.content for m in request.chat_history[-2:]])
        raw_key = f"{request.video_id}_{request.question}_{history_str}"
        cache_key = hashlib.md5(raw_key.encode()).hexdigest()

        cached = get_from_redis(f"chat_cache:{cache_key}")
        if cached:
            print(f"⚡ Returning from Redis Cache! Saved API cost for: {request.question}")
            async def cached_stream():
                yield cached.get("answer", "")
            return StreamingResponse(cached_stream(), media_type='text/plain')
        
        # Fallback to memory cache
        if cache_key in chat_response_cache:
            print(f"⚡ Returning from Memory Cache! Saved API cost for: {request.question}")
            async def cached_stream():
                yield chat_response_cache[cache_key]
            return StreamingResponse(cached_stream(), media_type='text/plain')

        # 2. NORMAL PROCESS & QUERY REWRITE
        history_text = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history[-2:]])
        rewrite_prompt = f"""You are a Contextual Search Query Generator for a Sinhala video database.
        Read the chat history and the new question. 
        If the new question is a follow-up, combine it with the history to make a STANDALONE Sinhala search phrase.
        If it is a completely new topic, just translate it to a Sinhala search phrase.
        Output ONLY the Sinhala search phrase. Do not write full sentences.
        History: {history_text}\nNew Question: {request.question}\nStandalone Sinhala Search Phrase:"""
        
        rewritten_q = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=rewrite_prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        search_query_text = rewritten_q.text.strip()

        # Generate Question Embedding
        result = client.models.embed_content(
            model="gemini-embedding-001", contents=search_query_text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768)
        )
        vector = result.embeddings[0].values
        
        # OpenSearch Hybrid Search (Vector k-NN + Keyword Match)
        search_query = {
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"video_id": request.video_id}}
                    ],
                    "should": [
                        # 1. Vector Search (Finds the contextual meaning)
                        {"knn": {"embedding": {"vector": vector, "k": 10}}},
                        # 2. Keyword Search (Finds EXACT Sinhala biology terms, boosted x2)
                        {"match": {"text_chunk": {"query": search_query_text, "boost": 2.0}}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }
        
        try:
            res = opensearch_client.search(index=INDEX_NAME, body=search_query)
            context = "\n---\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
        except:
            context = "Context unavailable."

        # 3. FINAL ANSWER GENERATION WITH MEMORY
        system_instr = """You are a friendly, kind, and highly advanced intelligent AI teaching assistant for Advanced Level (A/L) students.
        
        CRITICAL RULES:
        1. FACTUALITY: Answer based ONLY on the provided Context. Do not guess. If the answer is not in the context, say EXACTLY: "මට මේ වීඩියෝ එකෙන් ඒ ගැන හොයාගන්න බැරි වුණා දුවේ/පුතේ."
        
        2. STRICT LANGUAGE RULES (FOLLOW EXACTLY):
            - If the user's CURRENT question is written in ENGLISH → You MUST respond in ENGLISH only.
            - If the user's CURRENT question is written in SINHALA or SINGLISH → You MUST respond in SINHALA only.
            - IGNORE the language of the video context. Only look at the user's question language.
            - This is the MOST IMPORTANT rule. Check the question language FIRST before generating any response.
           
        3. DYNAMIC RESPONSE LENGTH & QUALITY (CRITICAL):
            - ADAPT TO USER INTENT: If the user asks a simple question like "What are the types?" (වර්ග මොනවද) or "Name them" (නම් කරන්න), provide a SHORT, CONCISE, and friendly list. DO NOT over-explain.
            - DEEP DIVE ONLY WHEN ASKED: ONLY if the user explicitly asks to "explain" (පැහැදිලි කරන්න) or "describe" (විස්තර කරන්න), you MUST provide a deep, comprehensive, and highly detailed explanation using the context.
            - Use bold text, bullet points, and short paragraphs to make the text highly readable.
            - ALWAYS start with a friendly, encouraging introductory sentence.
            
        4. TIMESTAMP FORMATTING (ABSOLUTE MANDATORY - OVERRIDE DEFAULT CITATIONS):
            - You MUST override your default citation style. DO NOT output raw times like "22:30" or "[22:30]" on a new line.
            - You MUST ONLY use the EXACT format provided below. Failure to do so will break the application UI.
            - EVERY major point, paragraph, or bullet point MUST END with its corresponding timestamp on the SAME LINE.
            
            Format for a single timestamp:
            Text explaining the point goes here. ⏱️ [▶ Play Video (HH:MM:SS - HH:MM:SS)]
            
            Format for multiple timestamps (MUST be inside ONE bracket, separated by commas):
            Text explaining the point goes here. ⏱️ [▶ Play Video (HH:MM:SS - HH:MM:SS), (HH:MM:SS - HH:MM:SS)]
            
            EXAMPLES OF CORRECT USAGE:
            * විභාජක පටක කියන්නේ තවමත් විභේදනය නොවූ සෛල වලින් සමන්විත පටක වර්ගයක්. ⏱️ [▶ Play Video (00:22:30 - 00:22:49)]
            * චර්මීය පටක ශාක දේහයේ බාහිරම ආවරණය සකස් කරයි. ⏱️ [▶ Play Video (01:54:27 - 01:54:45), (01:55:30 - 01:55:39)]
            
            STRICT BANS (NEVER DO THESE):
            - NEVER print just the time (e.g., 22:30 or 01:54:27).
            - NEVER put the time on a new empty line.
            - NEVER forget the ⏱️ emoji and the [▶ Play Video ] text.

        5. PREVENT HALLUCINATIONS & LOOPS (CRITICAL FOR VIDEO):
            - IGNORE ON-SCREEN TEXT: Do NOT transcribe or mention any text or software menus visible on the video screen (e.g., "Annotation mode", "Save", "Quit"). Focus ONLY on the spoken audio.
            - PREVENT REPETITION LOOPS: If there is a long silence or background noise, DO NOT continuously repeat filler words like "හරි" (Hari) or "ඕකේ" (Okay). Just SKIP the silent segments completely.

        6. SINHALA TONE & STYLE (CRITICAL - MUST USE STRICTLY SPOKEN SINHALA): 
           - You MUST write in everyday, natural Spoken Sinhala (කතා කරන භාෂාව) exactly as a friendly Sri Lankan teacher speaks in a classroom.
           - NEVER use formal written Sinhala endings (ග්‍රන්ථාරූඪ භාෂාව). 
           - STRICTLY FORBIDDEN WORDS/ENDINGS: Do not use "වේ", "ඇත", "කරයි", "සහ", "හා", "අතර", "වන්නේය". 
           - MANDATORY SPOKEN ENDINGS: Always end sentences with "වෙනවා", "තියෙනවා", "කරනවා", "වෙන්නේ", "කියන්නේ", "එක".
           - Instead of using "හා" or "සහ" to join words, use spoken styles like "යි...යි..." (e.g., instead of "ශෛලම සහ ෆ්ලෝයම", use "ශෛලමයි ෆ්ලෝයමයි").
           - Address the student affectionately using terms like "පුතේ" occasionally to sound warm.
           - Keep the scientific terms accurate (e.g., විභාජක පටක, ශෛලමය) but explain them using strictly conversational grammar.
        """

        formatted_contents = []
        for msg in request.chat_history:
            role = "user" if msg.role == "user" else "model"
            formatted_contents.append({"role": role, "parts": [{"text": msg.content}]})
            
        final_prompt = f"Video Context:\n{context}\n\nUser Question: {request.question}"
        formatted_contents.append({"role": "user", "parts": [{"text": final_prompt}]})
        
        # Use streaming generation
        async def generate_stream():
            full_response = ""
            for chunk in client.models.generate_content_stream(
                model="gemini-2.5-flash-lite", 
                contents=formatted_contents, 
                config=types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
            ):
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text

            # Save to cache after streaming is complete - USING HELPER FUNCTION
            if not save_to_redis(f"chat_cache:{cache_key}", {
                "answer": full_response,
                "timestamp": datetime.utcnow().isoformat()
            }, ttl_seconds=CHAT_CACHE_TTL):
                chat_response_cache[cache_key] = full_response
                    
        return StreamingResponse(generate_stream(), media_type='text/plain')
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/clear/{video_id}")
async def clear_chat_cache(video_id: str):
    """Clears the chat response cache (from Redis or Memory)."""
    try:
        message = ""
        cleared_count = 0

        # Clear memory cache
        global chat_response_cache
        cleared_count = len(chat_response_cache)
        chat_response_cache = {}
        message = f"Memory cache cleared. {cleared_count} entries removed."
        
        # For Redis, delete only chat-related keys (NOT flushdb - that's dangerous!)
        if redis_client:
            try:
                # Only delete chat_cache keys, not everything!
                keys = redis_client.keys("chat_cache:*")
                for key in keys:
                    redis_client.delete(key)
                message += f" Redis chat cache cleared. {len(keys)} keys removed."
            except Exception as e:
                message += f" Could not clear Redis cache: {e}"
            
        return {
            "status": "success", 
            "message": message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    """Health check including Redis status"""
    redis_status = "connected" if redis_client and redis_client.ping() else "disconnected"
    return {
        "status": "healthy",
        "redis": redis_status,
        "redis_db": REDIS_DB,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/videos")
async def list_videos():
    """Lists all videos from the S3 bucket along with their metadata."""
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="videos/")
        videos = []
        if 'Contents' in response:
            for obj in response['Contents']:
                # Get video filename from the key
                video_key = obj['Key']
                video_filename = video_key.replace('videos/', '')
                
                # Generate video URL
                video_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{video_key}"
                
                # Check for corresponding transcript
                transcript_key = f"transcripts/{video_filename}.txt"
                try:
                    s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
                    transcript_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{transcript_key}"
                except:
                    transcript_url = None
                
                # Retrieve thumbnail URL
                thumbnail_s3_key = f"thumbnails/{video_filename}.jpg"
                thumbnail_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
                
                # Fetch duration from OpenSearch metadata
                duration = "0:00"
                try:
                    search_query = {"size": 1, "query": {"term": {"video_id": video_filename}}, "_source": ["duration"]}
                    res = opensearch_client.search(index=INDEX_NAME, body=search_query)
                    if res['hits']['hits']:
                        duration = res['hits']['hits'][0]['_source'].get('duration', '0:00')
                except: pass
                
                # Extract display name by stripping UUID prefix
                display_name = video_filename.split("---")[-1] if "---" in video_filename else video_filename
                title = display_name.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title()
                print(f"display name:{display_name}")
                print(f"title:{title}")
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
        
        # Sort by most recently uploaded
        videos.sort(key=lambda x: x['uploaded_at'], reverse=True)
        return {"status": "success", "videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    """Gets details for a specific video using its ID."""
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Generate video URL
        video_key = f"videos/{video_id}"
        video_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{video_key}"
        
        # Check if video exists in S3
        try:
            response = s3_client.head_object(Bucket=BUCKET_NAME, Key=video_key)
        except:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Check for transcript
        transcript_key = f"transcripts/{video_id}.txt"
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
            transcript_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{transcript_key}"
        except: transcript_url = None
        
        thumbnail_filename = f"{video_id.replace('.mp4', '')}.jpg"
        thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
        
        # Extract display name by stripping UUID prefix
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

# Add this endpoint to delete a video
@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    """Deletes a video and its associated transcript/thumbnails from S3 and OpenSearch."""
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Delete from S3
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"videos/{video_id}")
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"thumbnails/{video_id}.jpg")
        try: s3_client.delete_object(Bucket=BUCKET_NAME, Key=f"transcripts/{video_id}.txt")
        except: pass
        
        # Delete index records from OpenSearch
        try:
            opensearch_client.delete_by_query(index=INDEX_NAME, body={"query": {"term": {"video_id": video_id}}})
        except: pass
        
        return {"status": "success", "message": "Video deleted"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/thumbnail/{video_id:path}")
async def get_thumbnail(video_id: str):
    """Serves locally cached thumbnails with appropriate cache headers."""
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Create thumbnail filename
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
    """List all Redis keys (for debugging)"""
    if not redis_client:
        return {"error": "Redis not connected"}
    
    keys = redis_client.keys("*")
    result = {}
    
    for key in keys[:50]:  # Limit to 50
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
    
    return {
        "total_keys": len(keys),
        "keys": result
    }