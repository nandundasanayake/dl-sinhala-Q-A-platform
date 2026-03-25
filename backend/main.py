import os
import time
import subprocess
import math
import re
import uuid
from typing import Dict
import hashlib
import boto3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# --- Helper Functions ---

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

def split_into_chunks(text, chunk_size=5, overlap=2):
    """Implements a Sliding Window chunking strategy for text."""
    lines = text.strip().split('\n')
    chunks = []
    for i in range(0, len(lines), max(1, chunk_size - overlap)):
        chunk_lines = lines[i:i+chunk_size]
        if not chunk_lines:
            continue
        chunk = " ".join(chunk_lines).strip()
        if chunk and chunk not in chunks:
            chunks.append(chunk)
    return chunks

def adjust_timestamps(transcript: str, offset_seconds: int) -> str:
    """Adjusts relative timestamps from Gemini by adding the base offset, supporting both MM:SS and HH:MM:SS."""
    # Matches time formats like [MM:SS - MM:SS] or [HH:MM:SS - HH:MM:SS]
    pattern = r'\[(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\]'
    
    def time_to_seconds(time_str):
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3: # HH:MM:SS
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2: # MM:SS
            return parts[0] * 60 + parts[1]
        return 0

    def seconds_to_time(total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        if h > 0:
            return f"[{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"[{m:02d}:{s:02d}"

    def replace_match(match):
        total_start_s = time_to_seconds(match.group(1)) + offset_seconds
        total_end_s = time_to_seconds(match.group(2)) + offset_seconds
        
        # Format the new string properly (removing the extra '[' added by seconds_to_time helper)
        start_str = seconds_to_time(total_start_s).replace('[', '')
        end_str = seconds_to_time(total_end_s).replace('[', '')
        
        return f"[{start_str} - {end_str}]"

    return re.sub(pattern, replace_match, transcript)

# Initialize OpenSearch
setup_opensearch_index()

# Global status dictionary for background task tracking
upload_statuses: Dict[str, Dict] = {}
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Global Cache for Chat Answers
chat_response_cache: Dict[str, str] = {}

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
        """Helper function to update the global status dictionary for frontend polling."""
        upload_statuses[video_id] = {
            "status": status,
            "message": message,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat()
        }
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

        # CHUNKING LOGIC: Split video into 30-min chunks (1800s)
        CHUNK_DURATION = 1800  # 30 minutes in seconds
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

                prompt = "Provide a full transcript with timestamps in the ORIGINAL language spoken. Format: [MM:SS - MM:SS] Text."
                
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
        update_status("completed", "Processing complete! Video ready.", 100)
        upload_statuses[video_id]["data"] = {
            "video_s3_url": video_s3_url, "transcript_s3_url": transcript_s3_url,
            "thumbnail_url": thumbnail_url, "duration": formatted_duration
        }
        # No local file cleanup needed - video was never stored locally
            
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
        upload_statuses[request.video_id] = {
            "status": "starting", "message": "Starting processing...", "progress": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add the heavy processing task to the background queue (no file_path needed)
        background_tasks.add_task(process_video_background, request.video_id)
        return {"status": "processing", "video_id": request.video_id, "message": "Processing started"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """Retrieves relevant context via Vector Search and generates a tailored response using Gemini Flash Lite with conversational memory and Caching."""
    try:
        # 1. CHECK CACHE
        history_str = "".join([m.content for m in request.chat_history[-2:]])
        raw_key = f"{request.video_id}_{request.question}_{history_str}"
        cache_key = hashlib.md5(raw_key.encode()).hexdigest()

        if cache_key in chat_response_cache:
            print(f"⚡ Returning from Cache! Saved API cost for: {request.question}")
            return {"status": "success", "answer": chat_response_cache[cache_key], "cached": True}

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
        
        # OpenSearch Vector Search
        search_query = {
            "size": 15, "query": {
                "bool": {"filter": [{"term": {"video_id": request.video_id}}],
                         "must": [{"knn": {"embedding": {"vector": vector, "k": 15}}}]}
            }
        }
        
        try:
            res = opensearch_client.search(index=INDEX_NAME, body=search_query)
            context = "\n---\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
        except:
            context = "Context unavailable."

        # 3. FINAL ANSWER GENERATION WITH MEMORY
        system_instr = """You are a friendly, kind, and advanced intelligent AI teaching assistant for children.
        
        CRITICAL RULES:
        1. FACTUALITY: Answer based ONLY on the provided Context. Do not guess. If the answer is not in the context, say EXACTLY: "මට මේ වීඩියෝ එකෙන් ඒ ගැන හොයාගන්න බැරි වුණා දුවේ/පුතේ."
        
        2. STRICT LANGUAGE RULES (FOLLOW EXACTLY):
            - If the user's CURRENT question is written in ENGLISH → You MUST respond in ENGLISH only.
            - If the user's CURRENT question is written in SINHALA or SINGLISH → You MUST respond in SINHALA only.
            - IGNORE the language of the video context. Only look at the user's question language.
            - This is the MOST IMPORTANT rule. Check the question language FIRST before generating any response.
           
        3. SINHALA TONE & STYLE(when responding in Sinhala): 
           - Strictly use friendly, warm, everyday Spoken/Conversational Sinhala suitable for 16-21 aged (e.g., "ඔව්", "කියන්නේ", "කරනවා", "මෙහෙමයි වෙන්නේ"). 
           - Sound like a very kind and encouraging teacher. Do NOT be robotic or blunt.
           - DO NOT use formal written Sinhala (ග්‍රන්ථාරූඪ භාෂාව).
           
        4. RESPONSE LENGTH & STRICT LISTING (CRITICAL):
           - Answer fully using natural sentences. Do not just give one-word answers.
           - If the user asks for examples or types, use bullet points, but ALWAYS start with a friendly introductory sentence
           - ONLY provide descriptions if the user explicitly asks to "describe" or "explain" (විස්තර කරන්න කියලා ඇහුවොත් පමණක්).
           
        5. TIMESTAMPS: Always include timestamps at the end of your points exactly like this: ⏱️ [▶ Play Video (MM:SS - MM:SS)]
        """
        
        formatted_contents = []
        for msg in request.chat_history:
            role = "user" if msg.role == "user" else "model"
            formatted_contents.append({"role": role, "parts": [{"text": msg.content}]})
            
        final_prompt = f"Video Context:\n{context}\n\nUser Question: {request.question}"
        formatted_contents.append({"role": "user", "parts": [{"text": final_prompt}]})
        
        answer = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=formatted_contents, 
            config=types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
        )
        
        # 4. SAVE TO CACHE
        chat_response_cache[cache_key] = answer.text
        
        return {"status": "success", "answer": answer.text, "cached": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/clear/{video_id}")
async def clear_chat_cache(video_id: str):
    """Clears the chat response cache for a specific video."""
    try:
        global chat_response_cache
        # Clear all cache entries (since we can't easily match hashed keys to video_id)
        # In a production system, you'd want to store video_id alongside the cache entry
        initial_count = len(chat_response_cache)
        chat_response_cache = {}
        
        return {
            "status": "success", 
            "message": f"Chat cache cleared for video: {video_id}",
            "cleared_entries": initial_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "healthy"}

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