import os
import time
import shutil
import boto3
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from pydantic import BaseModel
from typing import List

# Load environment variables from the .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(title="Enterprise Video RAG API", version="3.0")

# Configure CORS to allow requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- External Services Configuration ---

# 1. Google Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing.")
client = genai.Client(api_key=GEMINI_API_KEY)

# 2. AWS OpenSearch Configuration (t3.small.search)
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

# 3. AWS S3 Configuration
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1")
)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# --- Helper Functions ---

def setup_opensearch_index():
    """Ensures the OpenSearch index exists and is configured for k-NN search."""
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

def upload_file_to_s3(local_path, s3_file_key):
    """Uploads the video file to a specific folder in S3."""
    try:
        s3_client.upload_file(local_path, BUCKET_NAME, s3_file_key)
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{s3_file_key}"
    except Exception as e:
        print(f"❌ Video S3 Upload Failed: {e}")
        return None

def upload_text_to_s3(text_content, s3_file_key):
    """Uploads the raw transcript text directly to a specific folder in S3."""
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_file_key,
            Body=text_content.encode('utf-8'),
            ContentType='text/plain'
        )
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{s3_file_key}"
    except Exception as e:
        print(f"❌ Transcript S3 Upload Failed: {e}")
        return None

def split_into_chunks(text, size=3):
    """Splits transcript into chunks of sentences to preserve context."""
    lines = text.strip().split('\n')
    return [" ".join(lines[i:i+size]) for i in range(0, len(lines), size) if lines[i:i+size]]

# Initialize index on startup
setup_opensearch_index()

# Local temporary storage for processing
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
    """Handles video upload, S3 storage (video & transcript), Gemini processing, and OpenSearch indexing."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    try:
        # Save file locally for processing
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Step 1: Upload Video to AWS S3 'videos' folder
        video_s3_key = f"videos/{file.filename}"
        video_s3_url = upload_file_to_s3(file_path, video_s3_key)
        if not video_s3_url:
            raise HTTPException(status_code=500, detail="Video cloud storage upload failed.")

        # Step 2: Processing with Gemini 2.5 Flash to get Transcript
        video_file = client.files.upload(file=file_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        prompt = "Provide a full transcript with timestamps in the exact ORIGINAL language spoken in the video. Do not translate. Format: [MM:SS - MM:SS] Text."
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, prompt]
        )
        transcript_text = response.text

        # Step 3: Upload Transcript to AWS S3 'transcripts' folder
        transcript_s3_key = f"transcripts/{file.filename}.txt"
        transcript_s3_url = upload_text_to_s3(transcript_text, transcript_s3_key)

        # Step 4: Chunking and Embedding using correct model and dimensions
        chunks = split_into_chunks(transcript_text)
        for chunk in chunks:
            if not chunk.strip(): continue
            
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001", 
                    contents=chunk,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768
                    )
                )
                
                vector = result.embeddings[0].values
                if not vector:
                    continue

                # Step 5: Save embedded chunks to AWS OpenSearch
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
                print(f"✅ Chunk indexed successfully!")
                
            except Exception as e:
                print(f"⚠️ Chunk processing error: {e}")
                time.sleep(2)

        os.remove(file_path)
        return {
            "status": "success", 
            "video_id": file.filename, 
            "video_s3_url": video_s3_url,
            "transcript_s3_url": transcript_s3_url
        }

    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """Retrieves relevant video context and generates an AI answer using Flash Lite."""
    try:
        # Step 6 & 7: Generate embedding for student question
        result = client.models.embed_content(
            model="gemini-embedding-001", 
            contents=request.question,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768
            )
        )
        
        vector = result.embeddings[0].values
        if not vector:
            raise HTTPException(status_code=500, detail="AI Vector Error: Question embedding failed.")

        # Step 8: Search similar embedded top 3 chunks using AWS OpenSearch
        search_query = {
            "size": 3,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": vector, 
                        "k": 3
                    }
                }
            }
        }
        
        context = ""
        try:
            res = opensearch_client.search(index=INDEX_NAME, body=search_query)
            context = "\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
        except:
            context = "Context unavailable (DB Offline)."

        # Step 9: Generate answer using Gemini with Sinhala language support
        system_instr = """You are a helpful assistant that answers questions based on video transcripts.
        - Answer ONLY based on the provided context
        - If the question is in Sinhala, answer in Sinhala
        - If the question is in English, answer in English
        - Always include timestamps as: ⏱️ [Video Reference: MM:SS - MM:SS]
        - If the answer is not in the context, say "I cannot find this information in the video"
        """
        config = types.GenerateContentConfig(system_instruction=system_instr, temperature=0.0)
        
        history = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history])
        final_prompt = f"Context: {context}\nHistory: {history}\nQuestion: {request.question}"
        
        # Step 10: Answer with time stamps using Flash Lite
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