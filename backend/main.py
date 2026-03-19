import os
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

# Load environment variables from the .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(title="Enterprise Video RAG API", version="3.0")

# Configure CORS to allow requests from the React frontend (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
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

def generate_thumbnail(video_path, video_id, time_offset=5):
    """Generate thumbnail from video and save locally."""
    try:
        # Create thumbnails directory if it doesn't exist
        thumbnail_dir = "static/thumbnails"
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        # Generate thumbnail filename
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
        # If thumbnail already exists, return the URL
        if os.path.exists(thumbnail_path):
            print(f"🖼️ Thumbnail already exists: {thumbnail_path}")
            return f"/static/thumbnails/{thumbnail_filename}"
        
        # Generate new thumbnail using MoviePy
        clip = VideoFileClip(video_path)
        
        # If video is shorter than time_offset, use middle of video
        if clip.duration < time_offset:
            time_offset = clip.duration / 2
        
        # Get frame at specified time
        frame = clip.get_frame(time_offset)
        clip.close()
        
        # Convert to PIL Image and save
        img = Image.fromarray(np.uint8(frame))
        # Resize to thumbnail size (320x180)
        img = img.resize((320, 180), Image.Resampling.LANCZOS)
        img.save(thumbnail_path, 'JPEG', quality=85)
        
        print(f"✅ Thumbnail generated: {thumbnail_path}")
        return f"/static/thumbnails/{thumbnail_filename}"
        
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
        thumbnail_url = generate_thumbnail(file_path, file.filename)
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
        system_instr = """You are an AI teaching assistant.
        - Answer the question based ONLY on the provided Context.
        - CRITICAL INSTRUCTION: When the user asks for types, examples, or a list, you MUST thoroughly scan ALL the provided context chunks and extract EVERY SINGLE example mentioned (e.g., all plant names). Do NOT stop at just one.
        - List them clearly using bullet points.
        - Reply in natural, conversational Sinhala script.
        - Include timestamps at the end of points exactly like this: ⏱️ [▶ Play Video (MM:SS - MM:SS)]
        - If the exact answer is not in the context, say: "I cannot find this information in the video."
        """
        
        # Temperature 0.2 provides a good balance between factual accuracy and natural phrasing
        config = types.GenerateContentConfig(system_instruction=system_instr, temperature=0.2)
        
        final_prompt = f"Context:\n{context}\n\nQuestion: {request.question}"
        
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