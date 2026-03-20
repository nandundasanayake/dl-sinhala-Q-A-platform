import os
import io
import time
import shutil
import boto3
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # Add this
from fastapi.responses import FileResponse    # Add this
from google import genai
from google.genai import types
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from pydantic import BaseModel
from typing import List
from moviepy import VideoFileClip
from PIL import Image
import numpy as np
from starlette.middleware.base import BaseHTTPMiddleware 
from botocore.client import Config
from fastapi.responses import JSONResponse
import urllib.parse

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

# Mount static files directory to serve thumbnails
os.makedirs("static/thumbnails", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

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

def get_video_duration(file_path):
    """Get video duration using MoviePy."""
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()  # Important to close and free resources
        
        # Format as MM:SS
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes}:{seconds:02d}"
    except Exception as e:
        print(f"⚠️ Could not get video duration: {e}")
        return "0:00"

# def generate_thumbnail(file_path, output_path, time_offset=5):
#     """Generate thumbnail from video at specified time offset."""
#     try:
#         clip = VideoFileClip(file_path)
        
#         # If video is shorter than time_offset, use middle of video
#         if clip.duration < time_offset:
#             time_offset = clip.duration / 2
        
#         # Get frame at specified time
#         frame = clip.get_frame(time_offset)
#         clip.close()
        
#         # Convert to PIL Image and save
#         img = Image.fromarray(np.uint8(frame))
#         # Resize to thumbnail size (320x180)
#         img = img.resize((320, 180), Image.Resampling.LANCZOS)
#         img.save(output_path, 'JPEG', quality=85)
        
#         return True
#     except Exception as e:
#         print(f"⚠️ Could not generate thumbnail: {e}")
#         return False

# def generate_thumbnail(video_path, video_id, time_offset=5):
#     """Generate thumbnail from video and save locally."""
#     try:
#         # Create thumbnails directory if it doesn't exist
#         thumbnail_dir = "static/thumbnails"
#         os.makedirs(thumbnail_dir, exist_ok=True)
        
#         # Generate thumbnail filename
#         thumbnail_filename = video_id.replace('.mp4', '.jpg').replace('.mov', '.jpg').replace('.avi', '.jpg')

#         thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
#         # If thumbnail already exists, return the URL
#         if os.path.exists(thumbnail_path):
#             print(f"🖼️ Thumbnail already exists: {thumbnail_path}")
#             return f"/static/thumbnails/{thumbnail_filename}"
        
#         # Generate new thumbnail using MoviePy
#         clip = VideoFileClip(video_path)
        
#         # If video is shorter than time_offset, use middle of video
#         if clip.duration < time_offset:
#             time_offset = clip.duration / 2
        
#         # Get frame at specified time
#         frame = clip.get_frame(time_offset)
#         clip.close()
        
#         # Convert to PIL Image and save
#         img = Image.fromarray(np.uint8(frame))
#         # Resize to thumbnail size (320x180)
#         img = img.resize((320, 180), Image.Resampling.LANCZOS)
#         img.save(thumbnail_path, 'JPEG', quality=85)
        
#         print(f"✅ Thumbnail generated: {thumbnail_path}")
#         return f"/static/thumbnails/{thumbnail_filename}"
        
#     except Exception as e:
#         print(f"⚠️ Could not generate thumbnail: {e}")
#         return None




def generate_and_upload_thumbnail(video_path, video_id, time_offset=5):
    """Generate thumbnail from video and upload to S3."""
    try:
        # Generate thumbnail filename
        thumbnail_filename = video_id.replace('.mp4', '.jpg').replace('.mov', '.jpg').replace('.avi', '.jpg')
        thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"
        
        # Check if thumbnail already exists in S3
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=thumbnail_s3_key)
            print(f"🖼️ Thumbnail already exists in S3: {thumbnail_s3_key}")
            thumbnail_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
            return thumbnail_url
        except:
            pass
        
        # Generate new thumbnail using MoviePy
        clip = VideoFileClip(video_path)
        
        if clip.duration < time_offset:
            time_offset = clip.duration / 2
        
        frame = clip.get_frame(time_offset)
        clip.close()
        
        # Convert to PIL Image
        img = Image.fromarray(np.uint8(frame))
        img = img.resize((320, 180), Image.Resampling.LANCZOS)
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        
        # Upload to S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=thumbnail_s3_key,
            Body=buffer.getvalue(),
            ContentType='image/jpeg'
        )
        
        thumbnail_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
        print(f"✅ Thumbnail uploaded to S3: {thumbnail_url}")
        
        return thumbnail_url
        
    except Exception as e:
        print(f"⚠️ Could not generate thumbnail: {e}")
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
    """
    Implements a Sliding Window chunking strategy.
    Overlap ensures semantic continuity between chunks.
    """
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

# Initialize OpenSearch index structure on startup
setup_opensearch_index()

# Local directory for temporary file processing
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Data Models ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    video_id: str
    question: str
    chat_history: List[ChatMessage] = []

# --- API Endpoints ---

@app.post("/api/upload-video")
async def upload_and_process_video(file: UploadFile = File(...)):
    """Handles the full ingestion pipeline: S3 Upload -> Transcription -> Chunking -> Vector Indexing."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    thumbnail_path = os.path.join(UPLOAD_DIR, f"thumb_{file.filename}.jpg")
    
    try:
        # 1. Save locally for processing
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

         # Get video duration using MoviePy
        duration = get_video_duration(file_path)
        print(f"📹 Video duration: {duration}")

        # Generate thumbnail using MoviePy
        # save locally
        thumbnail_url = generate_and_upload_thumbnail(file_path, file.filename)
        print(f"🖼️ Thumbnail available at: {thumbnail_url}")

        # save to s3
        # thumbnail_generated = generate_thumbnail(file_path, thumbnail_path)
        # thumbnail_url = None

        # if thumbnail_generated:
        #     # Upload thumbnail to S3
        #     thumbnail_s3_key = f"thumbnails/{file.filename}.jpg"
        #     thumbnail_url = upload_file_to_s3(thumbnail_path, thumbnail_s3_key)
        #     print(f"🖼️ Thumbnail uploaded: {thumbnail_url}")

        # Step 1: Upload Video to AWS S3 'videos' folder
        video_s3_key = f"videos/{file.filename}"
        video_s3_url = upload_file_to_s3(file_path, video_s3_key)
        if not video_s3_url:
            raise HTTPException(status_code=500, detail="Cloud storage upload failed.")

        # 3. Transcribe using Gemini 2.5 Flash
        video_file = client.files.upload(file=file_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        # Prompt for original language transcription with timestamps
        prompt = "Provide a full transcript with timestamps in the ORIGINAL language spoken. Do not translate. Format: [MM:SS - MM:SS] Text."
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, prompt]
        )
        transcript_text = response.text

        # 4. Upload Transcript to S3 for reference
        transcript_s3_url = upload_text_to_s3(transcript_text, f"transcripts/{file.filename}.txt")

        # 5. Advanced Chunking and Vectorization
        chunks = split_into_chunks(transcript_text, chunk_size=5, overlap=2)
        for chunk in chunks:
            if not chunk.strip(): continue
            
            # Enrich chunk with metadata to improve search relevance
            enriched_content = f"Video Source: {file.filename}\nContent: {chunk}"

            try:
                # Use dimensionality=768 to match the OpenSearch index schema
                result = client.models.embed_content(
                    model="gemini-embedding-001", 
                    contents=enriched_content,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768
                    )
                )

                vector = result.embeddings[0].values
                if not vector: continue

                # Index document into OpenSearch
                doc = {
                    "video_id": file.filename,
                    "text_chunk": chunk,
                    "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
                    "video_s3_url": video_s3_url,
                    "transcript_s3_url": transcript_s3_url,
                    "duration": duration, 
                    "embedding": vector
                }
                opensearch_client.index(index=INDEX_NAME, body=doc)
                time.sleep(0.5)
                print(f"✅ Indexed chunk from {file.filename}")
                
            except Exception as e:
                print(f"⚠️ Indexing error: {e}")
                time.sleep(2)

        os.remove(file_path)
        return {
            "status": "success", 
            "video_id": file.filename, 
            "video_s3_url": video_s3_url,
            "transcript_s3_url": transcript_s3_url,
            "thumbnail_url": thumbnail_url,
            "duration": duration  # This will show on video cards
        }

    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        # if os.path.exists(thumbnail_path): os.remove(thumbnail_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """Retrieves relevant context via Vector Search and generates a tailored response using Gemini Flash Lite."""
    try:
        # Step 1: Intelligent Contextual Query Rewriting
        # We pass the last 2 messages to understand context without overwhelming the Lite model.
        history_text = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history[-2:]])
        
        # We explicitly instruct the model to create a STANDALONE search phrase, not just random keywords.
        rewrite_prompt = f"""You are a Contextual Search Query Generator for a Sinhala video database.
        Read the chat history and the new question. 
        If the new question is a follow-up (e.g., "what are the types?", "what else?"), combine it with the history to make a STANDALONE Sinhala search phrase.
        If it is a completely new topic, just translate it to a Sinhala search phrase.
        Output ONLY the Sinhala search phrase. Do not write full sentences.
        
        History: {history_text}
        New Question: {request.question}
        
        Standalone Sinhala Search Phrase:"""
        
        # Use Flash-Lite for cost-efficiency with a slightly higher temp for better reasoning
        rewritten_q = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=rewrite_prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        search_query_text = rewritten_q.text.strip()
        print(f"🎯 Original: {request.question} | 🧠 Standalone Query: {search_query_text}")

        # Step 2: Generate Question Embedding
        result = client.models.embed_content(
            model="gemini-embedding-001", 
            contents=search_query_text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768
            )
        )

        vector = result.embeddings[0].values
        if not vector:
            raise HTTPException(status_code=500, detail="Embedding generation failed.")
        
        # Step 3: OpenSearch Vector Search (Filtered by current video)
        search_query = {
            "size": 15, 
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"video_id": request.video_id}}
                    ],
                    "must": [
                        {"knn": {"embedding": {"vector": vector, "k": 15}}}
                    ]
                }
            }
        }
        
        context = ""
        try:
            res = opensearch_client.search(index=INDEX_NAME, body=search_query)
            context = "\n---\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
            print(f"🚀 Retrieved {len(res['hits']['hits'])} context chunks.")

        except:
            context = "Context unavailable."

        # Step 4: Final Answer Generation
        system_instr = """You are a friendly and intelligent AI teaching assistant for children.
        
        CRITICAL RULES:
        1. FACTUALITY: Answer based ONLY on the provided Context. Do not guess. If the answer is not in the context, say EXACTLY: "I cannot find this information in the video."
        
        2. STRICT LANGUAGE MATCHING: 
           - Look at the language of the 'Question'.
           - If the Question is in ENGLISH: You MUST reply entirely in ENGLISH.
           - If the Question is in SINHALA or SINGLISH: You MUST reply entirely in natural SINHALA SCRIPT.
           
        3. SINHALA TONE & STYLE: 
           - Strictly use friendly, everyday Spoken/Conversational Sinhala (කතා කරන භාෂාව) suitable for kids (e.g., "කියන්නේ", "කරනවා", "වෙනවා"). 
           - DO NOT use formal written Sinhala.
           
        4. RESPONSE LENGTH & STRICT LISTING (CRITICAL):
           - For simple questions, give a VERY CONCISE, short answer (1 sentence).
           - STRICT LISTING RULE: If the user asks ONLY for types, names, or examples (e.g., "වර්ග මොනවාද?"), output ONLY THE NAMES in bullet points (e.g., * බාඳුරා). DO NOT add any descriptions, features, or extra sentences next to the names.
           - ONLY provide descriptions if the user explicitly asks to "describe" or "explain" (විස්තර කරන්න කියලා ඇහුවොත් පමණක්).
           
        5. TIMESTAMPS: Always include timestamps at the end of your points exactly like this: ⏱️ [▶ Play Video (MM:SS - MM:SS)]
        """
        
        # Temperature 0.2 provides a good balance between factual accuracy and natural phrasing
        config = types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
        
        final_prompt = f"Context:\n{context}\n\nQuestion (Reply entirely in the language of this question): {request.question}"
        
        answer = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=final_prompt, 
            config=config
        )
        
        return {"status": "success", "answer": answer.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "healthy"}


# Add these imports at the top
from datetime import datetime
import urllib.parse

# Add this new endpoint to list videos from S3
@app.get("/api/videos")
async def list_videos():
    """
    List all videos from S3 bucket with their metadata.
    """
    try:
        # List objects in the videos folder
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix="videos/"
        )
        
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
                transcript_url = None
                try:
                    s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
                    transcript_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{transcript_key}"
                except:
                    transcript_url = None
                
                # Check for thumbnail
                # thumbnail_filename = f"{video_filename}.jpg"
                # thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"

                # Thumbnail s3 bucket
                thumbnail_filename = video_filename.replace('.mp4', '.jpg').replace('.mov', '.jpg').replace('.avi', '.jpg')
                thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"

                thumbnail_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{thumbnail_s3_key}"
                
                # Check if thumbnail exists locally
                # thumbnail_path = os.path.join("static/thumbnails", thumbnail_filename)
                # if not os.path.exists(thumbnail_path):
                #     thumbnail_url = None
                
                # Get video duration from OpenSearch (if available)
                duration = "0:00"
                try:
                    # Search for any chunk of this video to get duration
                    search_query = {
                        "size": 1,
                        "query": {
                            "term": {"video_id": video_filename}
                        },
                        "_source": ["duration"]  # Only fetch the duration field
                    }
                    res = opensearch_client.search(index=INDEX_NAME, body=search_query)
                    if res['hits']['hits']:
                        duration = res['hits']['hits'][0]['_source'].get('duration', '0:00')
                except Exception as e:
                    print(f"Could not fetch duration for {video_filename}: {e}")
                
                videos.append({
                    "id": video_filename,
                    "video_id": video_filename,
                    "title": video_filename.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title(),
                    "video_url": video_url,
                    "transcript_url": transcript_url,
                    "thumbnail_url": thumbnail_url,
                    "duration": duration,
                    "uploaded_at": obj['LastModified'].isoformat(),
                    "file_size": obj['Size']
                })
        
        # Sort by last modified (newest first)
        videos.sort(key=lambda x: x['uploaded_at'], reverse=True)
        
        return {
            "status": "success",
            "videos": videos
        }
        
    except Exception as e:
        print(f"Error listing videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this endpoint to get a single video's details
@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    """
    Get details for a specific video.
    """
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Generate video URL
        video_key = f"videos/{video_id}"
        video_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{video_key}"
        
        # Check if video exists in S3
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=video_key)
        except:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Check for transcript
        transcript_key = f"transcripts/{video_id}.txt"
        transcript_url = None
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
            transcript_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{transcript_key}"
        except:
            pass
        
        # Check for thumbnail
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
        thumbnail_path = os.path.join("static/thumbnails", thumbnail_filename)
        if not os.path.exists(thumbnail_path):
            thumbnail_url = None
        
        # Get video metadata from S3
        response = s3_client.head_object(Bucket=BUCKET_NAME, Key=video_key)
        
        return {
            "status": "success",
            "video": {
                "id": video_id,
                "video_id": video_id,
                "title": video_id.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title(),
                "video_url": video_url,
                "transcript_url": transcript_url,
                "thumbnail_url": thumbnail_url,
                "uploaded_at": response['LastModified'].isoformat(),
                "file_size": response['ContentLength']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this endpoint to search videos
@app.get("/api/videos/search")
async def search_videos(query: str):
    """
    Search videos by title.
    """
    try:
        # List all videos from S3
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix="videos/"
        )
        
        videos = []
        
        if 'Contents' in response:
            for obj in response['Contents']:
                video_key = obj['Key']
                video_filename = video_key.replace('videos/', '')
                
                # Check if query matches title (case-insensitive)
                title = video_filename.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title()
                if query.lower() in title.lower():
                    video_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{video_key}"
                    
                    # Check for thumbnail
                    thumbnail_filename = f"{video_filename}.jpg"
                    thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
                    thumbnail_path = os.path.join("static/thumbnails", thumbnail_filename)
                    if not os.path.exists(thumbnail_path):
                        thumbnail_url = None
                    
                    videos.append({
                        "id": video_filename,
                        "video_id": video_filename,
                        "title": title,
                        "video_url": video_url,
                        "thumbnail_url": thumbnail_url,
                        "uploaded_at": obj['LastModified'].isoformat()
                    })
        
        return {
            "status": "success",
            "videos": videos
        }
        
    except Exception as e:
        print(f"Error searching videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this endpoint to delete a video
@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    """
    Delete a video and its associated files from S3.
    """
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Delete video from S3
        video_key = f"videos/{video_id}"
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=video_key)
        
        # Delete transcript if exists
        transcript_key = f"transcripts/{video_id}.txt"
        try:
            s3_client.delete_object(Bucket=BUCKET_NAME, Key=transcript_key)
        except:
            pass
        
        # Delete thumbnail if exists
        thumbnail_path = os.path.join("static/thumbnails", f"{video_id}.jpg")
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        
        # Delete from OpenSearch
        try:
            search_query = {
                "query": {
                    "term": {"video_id": video_id}
                }
            }
            opensearch_client.delete_by_query(index=INDEX_NAME, body=search_query)
        except:
            pass
        
        return {
            "status": "success",
            "message": f"Video {video_id} deleted successfully"
        }
        
    except Exception as e:
        print(f"Error deleting video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/thumbnail/{video_id:path}")
async def get_thumbnail(video_id: str):
    """Serve thumbnails with proper encoding and headers"""
    try:
        # URL decode the video_id
        video_id = urllib.parse.unquote(video_id)
        
        # Create thumbnail filename
        thumbnail_filename = video_id.replace('.mp4', '.jpg')
        thumbnail_path = os.path.join("static", "thumbnails", thumbnail_filename)
        
        print(f"🔍 Serving thumbnail: {thumbnail_path}")
        
        # Check if file exists
        if not os.path.exists(thumbnail_path):
            print(f"❌ Thumbnail not found: {thumbnail_path}")
            # List available thumbnails for debugging
            if os.path.exists(f"static/thumbnails"):
                print(f"📁 Available thumbnails: {os.listdir('static/thumbnails')}")
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        
        # Return the image with the required header
        return FileResponse(
            thumbnail_path,
            media_type="image/jpeg",
            headers={
                "ngrok-skip-browser-warning": "true",
                "Cache-Control": "public, max-age=3600"
            }
        )
    except Exception as e:
        print(f"❌ Error serving thumbnail: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# import os
# import time
# import shutil
# import boto3
# from fastapi import FastAPI, UploadFile, File, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import JSONResponse
# from google import genai
# from google.genai import types
# from dotenv import load_dotenv
# from opensearchpy import OpenSearch, RequestsHttpConnection
# from pydantic import BaseModel
# from typing import List
# from moviepy import VideoFileClip
# from PIL import Image
# import numpy as np
# from botocore.client import Config
# import urllib.parse
# from datetime import datetime

# # Load environment variables from the .env file
# load_dotenv()

# # Initialize the FastAPI application
# app = FastAPI(title="Enterprise Video RAG API", version="3.0")

# # Configure CORS to allow requests from the React frontend (Vite default port 5173)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Mount static files directory to serve thumbnails
# os.makedirs("static/thumbnails", exist_ok=True)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# # --- External Services Configuration ---

# # 1. Google Gemini API Configuration
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# if not GEMINI_API_KEY:
#     raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in environment variables.")
# client = genai.Client(api_key=GEMINI_API_KEY)

# # 2. AWS OpenSearch Configuration
# opensearch_client = OpenSearch(
#     hosts=[{'host': os.getenv("OPENSEARCH_HOST", "localhost"), 'port': int(os.getenv("OPENSEARCH_PORT", 443))}],
#     http_auth=(os.getenv("OPENSEARCH_USER", "admin"), os.getenv("OPENSEARCH_PASS", "admin")),
#     use_ssl=True,
#     verify_certs=True,
#     connection_class=RequestsHttpConnection,
#     timeout=60,
#     max_retries=5,
#     retry_on_timeout=True
# )
# INDEX_NAME = "video-transcripts-index"

# # 3. AWS S3 Configuration for Cloud Storage
# s3_client = boto3.client(
#     's3',
#     aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
#     aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
#     region_name=os.getenv("AWS_REGION", "ap-south-1")
# )

# # Create a separate S3 client for signed URLs with proper signature version
# s3_signed_client = boto3.client(
#     's3',
#     aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
#     aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
#     region_name=os.getenv("AWS_REGION", "ap-south-1"),
#     config=Config(signature_version='s3v4')
# )

# BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# # --- Helper Functions ---

# def setup_opensearch_index():
#     """Ensures the OpenSearch index exists and is configured for k-NN vector search."""
#     try:
#         if not opensearch_client.indices.exists(index=INDEX_NAME):
#             index_body = {
#                 "settings": {"index.knn": True},
#                 "mappings": {
#                     "properties": {
#                         "video_id": {"type": "keyword"},
#                         "timestamp": {"type": "text"},
#                         "text_chunk": {"type": "text"},
#                         "video_s3_url": {"type": "keyword"},
#                         "transcript_s3_url": {"type": "keyword"},
#                         "embedding": {
#                             "type": "knn_vector",
#                             "dimension": 768
#                         }
#                     }
#                 }
#             }
#             opensearch_client.indices.create(index=INDEX_NAME, body=index_body)
#             print(f"✅ Created OpenSearch Index: {INDEX_NAME}")
#     except Exception as e:
#         print(f"⚠️ OpenSearch Connection Warning: {e}")

# def get_video_duration(file_path):
#     """Get video duration using MoviePy."""
#     try:
#         clip = VideoFileClip(file_path)
#         duration = clip.duration
#         clip.close()
        
#         # Format as MM:SS
#         minutes = int(duration // 60)
#         seconds = int(duration % 60)
#         return f"{minutes}:{seconds:02d}"
#     except Exception as e:
#         print(f"⚠️ Could not get video duration: {e}")
#         return "0:00"

# def generate_thumbnail(video_path, video_id, time_offset=5):
#     """Generate thumbnail from video and save locally."""
#     try:
#         # Create thumbnails directory if it doesn't exist
#         thumbnail_dir = "static/thumbnails"
#         os.makedirs(thumbnail_dir, exist_ok=True)
        
#         # Generate thumbnail filename
#         thumbnail_filename = f"{video_id}.jpg"
#         thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
#         # If thumbnail already exists, return the URL
#         if os.path.exists(thumbnail_path):
#             print(f"🖼️ Thumbnail already exists: {thumbnail_path}")
#             return f"/static/thumbnails/{thumbnail_filename}"
        
#         # Generate new thumbnail using MoviePy
#         clip = VideoFileClip(video_path)
        
#         # If video is shorter than time_offset, use middle of video
#         if clip.duration < time_offset:
#             time_offset = clip.duration / 2
        
#         # Get frame at specified time
#         frame = clip.get_frame(time_offset)
#         clip.close()
        
#         # Convert to PIL Image and save
#         img = Image.fromarray(np.uint8(frame))
#         # Resize to thumbnail size (320x180)
#         img = img.resize((320, 180), Image.Resampling.LANCZOS)
#         img.save(thumbnail_path, 'JPEG', quality=85)
        
#         print(f"✅ Thumbnail generated: {thumbnail_path}")
#         return f"/static/thumbnails/{thumbnail_filename}"
        
#     except Exception as e:
#         print(f"⚠️ Could not generate thumbnail: {e}")
#         return None

# def upload_file_to_s3(local_path, s3_file_key):
#     """Uploads binary files (videos) to AWS S3."""
#     try:
#         s3_client.upload_file(local_path, BUCKET_NAME, s3_file_key)
#         # Return just the key, not the public URL
#         return s3_file_key
#     except Exception as e:
#         print(f"❌ S3 Video Upload Failed: {e}")
#         return None

# def upload_text_to_s3(text_content, s3_file_key):
#     """Uploads raw transcript strings to AWS S3."""
#     try:
#         s3_client.put_object(
#             Bucket=BUCKET_NAME,
#             Key=s3_file_key,
#             Body=text_content.encode('utf-8'),
#             ContentType='text/plain'
#         )
#         return s3_file_key
#     except Exception as e:
#         print(f"❌ S3 Transcript Upload Failed: {e}")
#         return None

# def split_into_chunks(text, chunk_size=5, overlap=2):
#     """
#     Implements a Sliding Window chunking strategy.
#     Overlap ensures semantic continuity between chunks.
#     """
#     lines = text.strip().split('\n')
#     chunks = []
#     for i in range(0, len(lines), max(1, chunk_size - overlap)):
#         chunk_lines = lines[i:i+chunk_size]
#         if not chunk_lines:
#             continue
#         chunk = " ".join(chunk_lines).strip()
#         if chunk and chunk not in chunks:
#             chunks.append(chunk)
#     return chunks

# # Initialize OpenSearch index structure on startup
# setup_opensearch_index()

# # Local directory for temporary file processing
# UPLOAD_DIR = "temp_uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)

# # --- Data Models ---
# class ChatMessage(BaseModel):
#     role: str
#     content: str

# class ChatRequest(BaseModel):
#     video_id: str
#     question: str
#     chat_history: List[ChatMessage] = []

# # --- API Endpoints ---

# @app.post("/api/upload-video")
# async def upload_and_process_video(file: UploadFile = File(...)):
#     """Handles the full ingestion pipeline: S3 Upload -> Transcription -> Chunking -> Vector Indexing."""
#     file_path = os.path.join(UPLOAD_DIR, file.filename)
    
#     try:
#         # 1. Save locally for processing
#         with open(file_path, "wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)

#         # Get video duration using MoviePy
#         duration = get_video_duration(file_path)
#         print(f"📹 Video duration: {duration}")

#         # Generate thumbnail using MoviePy and save locally
#         thumbnail_url = generate_thumbnail(file_path, file.filename)
#         print(f"🖼️ Thumbnail available at: {thumbnail_url}")

#         # Upload Video to AWS S3 'videos' folder
#         video_s3_key = f"videos/{file.filename}"
#         video_s3_key_result = upload_file_to_s3(file_path, video_s3_key)
#         if not video_s3_key_result:
#             raise HTTPException(status_code=500, detail="Cloud storage upload failed.")

#         # 3. Transcribe using Gemini
#         video_file = client.files.upload(file=file_path)
#         while video_file.state.name == "PROCESSING":
#             time.sleep(5)
#             video_file = client.files.get(name=video_file.name)

#         # Prompt for original language transcription with timestamps
#         prompt = "Provide a full transcript with timestamps in the ORIGINAL language spoken. Do not translate. Format: [MM:SS - MM:SS] Text."
#         response = client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=[video_file, prompt]
#         )
#         transcript_text = response.text

#         # 4. Upload Transcript to S3 for reference
#         transcript_s3_key = upload_text_to_s3(transcript_text, f"transcripts/{file.filename}.txt")

#         # 5. Advanced Chunking and Vectorization
#         chunks = split_into_chunks(transcript_text, chunk_size=5, overlap=2)
#         for chunk in chunks:
#             if not chunk.strip(): continue
            
#             # Enrich chunk with metadata to improve search relevance
#             enriched_content = f"Video Source: {file.filename}\nContent: {chunk}"

#             try:
#                 # Use dimensionality=768 to match the OpenSearch index schema
#                 result = client.models.embed_content(
#                     model="gemini-embedding-001", 
#                     contents=enriched_content,
#                     config=types.EmbedContentConfig(
#                         task_type="RETRIEVAL_DOCUMENT",
#                         output_dimensionality=768
#                     )
#                 )

#                 vector = result.embeddings[0].values
#                 if not vector: continue

#                 # Index document into OpenSearch
#                 doc = {
#                     "video_id": file.filename,
#                     "text_chunk": chunk,
#                     "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
#                     "video_s3_key": video_s3_key_result,  # Store key instead of full URL
#                     "transcript_s3_key": transcript_s3_key,  # Store key instead of full URL
#                     "duration": duration,
#                     "embedding": vector
#                 }
#                 opensearch_client.index(index=INDEX_NAME, body=doc)
#                 time.sleep(0.5)
#                 print(f"✅ Indexed chunk from {file.filename}")
                
#             except Exception as e:
#                 print(f"⚠️ Indexing error: {e}")
#                 time.sleep(2)

#         os.remove(file_path)
#         return {
#             "status": "success", 
#             "video_id": file.filename, 
#             "thumbnail_url": thumbnail_url,
#             "duration": duration
#         }

#     except Exception as e:
#         if os.path.exists(file_path): 
#             os.remove(file_path)
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/api/chat")
# async def ask_question(request: ChatRequest):
#     """Retrieves relevant context via Vector Search and generates a tailored response using Gemini Flash Lite."""
#     try:
#         # Step 1: Intelligent Contextual Query Rewriting
#         history_text = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history[-2:]])
        
#         rewrite_prompt = f"""You are a Contextual Search Query Generator for a Sinhala video database.
#         Read the chat history and the new question. 
#         If the new question is a follow-up (e.g., "what are the types?", "what else?"), combine it with the history to make a STANDALONE Sinhala search phrase.
#         If it is a completely new topic, just translate it to a Sinhala search phrase.
#         Output ONLY the Sinhala search phrase. Do not write full sentences.
        
#         History: {history_text}
#         New Question: {request.question}
        
#         Standalone Sinhala Search Phrase:"""
        
#         rewritten_q = client.models.generate_content(
#             model="gemini-2.5-flash-lite", 
#             contents=rewrite_prompt,
#             config=types.GenerateContentConfig(temperature=0.2)
#         )
#         search_query_text = rewritten_q.text.strip()
#         print(f"🎯 Original: {request.question} | 🧠 Standalone Query: {search_query_text}")

#         # Step 2: Generate Question Embedding
#         result = client.models.embed_content(
#             model="gemini-embedding-001", 
#             contents=search_query_text,
#             config=types.EmbedContentConfig(
#                 task_type="RETRIEVAL_QUERY",
#                 output_dimensionality=768
#             )
#         )

#         vector = result.embeddings[0].values
#         if not vector:
#             raise HTTPException(status_code=500, detail="Embedding generation failed.")
        
#         # Step 3: OpenSearch Vector Search (Filtered by current video)
#         search_query = {
#             "size": 15, 
#             "query": {
#                 "bool": {
#                     "filter": [
#                         {"term": {"video_id": request.video_id}}
#                     ],
#                     "must": [
#                         {"knn": {"embedding": {"vector": vector, "k": 15}}}
#                     ]
#                 }
#             }
#         }
        
#         context = ""
#         try:
#             res = opensearch_client.search(index=INDEX_NAME, body=search_query)
#             context = "\n---\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
#             print(f"🚀 Retrieved {len(res['hits']['hits'])} context chunks.")
#         except:
#             context = "Context unavailable."

#         # Step 4: Final Answer Generation
#         system_instr = """You are an AI teaching assistant.
#         - Answer the question based ONLY on the provided Context.
#         - CRITICAL INSTRUCTION: When the user asks for types, examples, or a list, you MUST thoroughly scan ALL the provided context chunks and extract EVERY SINGLE example mentioned (e.g., all plant names). Do NOT stop at just one.
#         - List them clearly using bullet points.
#         - Reply in natural, conversational Sinhala script.
#         - Include timestamps at the end of points exactly like this: ⏱️ [▶ Play Video (MM:SS - MM:SS)]
#         - If the exact answer is not in the context, say: "I cannot find this information in the video."
#         """
        
#         config = types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
        
#         final_prompt = f"Context:\n{context}\n\nQuestion: {request.question}"
        
#         answer = client.models.generate_content(
#             model="gemini-2.5-flash-lite", 
#             contents=final_prompt, 
#             config=config
#         )
        
#         return {"status": "success", "answer": answer.text}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/videos")
# async def list_videos():
#     """
#     List all videos from S3 bucket with their metadata.
#     """
#     try:
#         # List objects in the videos folder
#         response = s3_client.list_objects_v2(
#             Bucket=BUCKET_NAME,
#             Prefix="videos/"
#         )
        
#         videos = []
        
#         if 'Contents' in response:
#             for obj in response['Contents']:
#                 # Get video filename from the key
#                 video_key = obj['Key']
#                 video_filename = video_key.replace('videos/', '')
                
#                 # Check for transcript
#                 transcript_key = f"transcripts/{video_filename}.txt"
#                 has_transcript = False
#                 try:
#                     s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
#                     has_transcript = True
#                 except:
#                     pass
                
#                 # Check for thumbnail
#                 thumbnail_filename = f"{video_filename}.jpg"
#                 thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
                
#                 # Check if thumbnail exists locally
#                 thumbnail_path = os.path.join("static/thumbnails", thumbnail_filename)
#                 if not os.path.exists(thumbnail_path):
#                     thumbnail_url = None
                
#                 # Get video duration from OpenSearch (if available)
#                 duration = "0:00"
#                 try:
#                     search_query = {
#                         "query": {
#                             "term": {"video_id": video_filename}
#                         },
#                         "size": 1
#                     }
#                     res = opensearch_client.search(index=INDEX_NAME, body=search_query)
#                     # You might want to store duration in OpenSearch
#                 except:
#                     pass
                
#                 videos.append({
#                     "id": video_filename,
#                     "video_id": video_filename,
#                     "title": video_filename.replace(".mp4", "").replace(".mov", "").replace(".avi", "").replace("_", " ").title(),
#                     "thumbnail_url": thumbnail_url,
#                     "has_transcript": has_transcript,
#                     "duration": duration,
#                     "uploaded_at": obj['LastModified'].isoformat(),
#                     "file_size": obj['Size']
#                 })
        
#         # Sort by last modified (newest first)
#         videos.sort(key=lambda x: x['uploaded_at'], reverse=True)
        
#         return {
#             "status": "success",
#             "videos": videos
#         }
        
#     except Exception as e:
#         print(f"Error listing videos: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/videos/{video_id}/signed-url")
# async def get_signed_video_url(video_id: str):
#     """
#     Generate a pre-signed URL for private S3 videos
#     """
#     try:
#         # URL decode the video_id
#         video_id = urllib.parse.unquote(video_id)
#         print(f"Generating signed URL for: {video_id}")
        
#         # Generate pre-signed URL (valid for 1 hour)
#         video_key = f"videos/{video_id}"
        
#         # Generate pre-signed URL using the dedicated signed client
#         url = s3_signed_client.generate_presigned_url(
#             'get_object',
#             Params={
#                 'Bucket': BUCKET_NAME,
#                 'Key': video_key,
#                 'ResponseContentDisposition': 'inline',
#                 'ResponseContentType': 'video/mp4',
#                 'ResponseCacheControl': 'no-cache',  # Add this
#             },
#             ExpiresIn=3600  # URL expires in 1 hour
#         )
        
#         print(f"Generated signed URL successfully")
#         # Return as JSON with CORS headers
#         response = JSONResponse(content={"url": url})
#         response.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
#         response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
#         response.headers["Access-Control-Allow-Headers"] = "Content-Type"
#         response.headers["Access-Control-Allow-Credentials"] = "true"
#         return response
        
#     except Exception as e:
#         print(f"Error generating signed URL: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/videos/{video_id}/transcript")
# async def get_transcript_url(video_id: str):
#     """
#     Generate a pre-signed URL for transcript
#     """
#     try:
#         video_id = urllib.parse.unquote(video_id)
#         transcript_key = f"transcripts/{video_id}.txt"
        
#         # Check if transcript exists
#         try:
#             s3_client.head_object(Bucket=BUCKET_NAME, Key=transcript_key)
#         except:
#             raise HTTPException(status_code=404, detail="Transcript not found")
        
#         # Generate pre-signed URL
#         url = s3_signed_client.generate_presigned_url(
#             'get_object',
#             Params={
#                 'Bucket': BUCKET_NAME,
#                 'Key': transcript_key,
#                 'ResponseContentType': 'text/plain'
#             },
#             ExpiresIn=3600
#         )
        
#         return JSONResponse(content={"url": url})
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"Error generating transcript URL: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.delete("/api/videos/{video_id}")
# async def delete_video(video_id: str):
#     """
#     Delete a video and its associated files from S3.
#     """
#     try:
#         # URL decode the video_id
#         video_id = urllib.parse.unquote(video_id)
        
#         # Delete video from S3
#         video_key = f"videos/{video_id}"
#         s3_client.delete_object(Bucket=BUCKET_NAME, Key=video_key)
        
#         # Delete transcript if exists
#         transcript_key = f"transcripts/{video_id}.txt"
#         try:
#             s3_client.delete_object(Bucket=BUCKET_NAME, Key=transcript_key)
#         except:
#             pass
        
#         # Delete thumbnail if exists
#         thumbnail_path = os.path.join("static/thumbnails", f"{video_id}.jpg")
#         if os.path.exists(thumbnail_path):
#             os.remove(thumbnail_path)
        
#         # Delete from OpenSearch
#         try:
#             search_query = {
#                 "query": {
#                     "term": {"video_id": video_id}
#                 }
#             }
#             opensearch_client.delete_by_query(index=INDEX_NAME, body=search_query)
#         except:
#             pass
        
#         return {
#             "status": "success",
#             "message": f"Video {video_id} deleted successfully"
#         }
        
#     except Exception as e:
#         print(f"Error deleting video: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/health")
# def health():
#     return {"status": "healthy"}