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
from botocore.exceptions import NoCredentialsError

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

# 1. Google Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing.")
client = genai.Client(api_key=GEMINI_API_KEY)

# 2. AWS OpenSearch Configuration
opensearch_client = OpenSearch(
    hosts=[{'host': os.getenv("OPENSEARCH_HOST", "localhost"), 'port': int(os.getenv("OPENSEARCH_PORT", 443))}],
    http_auth=(os.getenv("OPENSEARCH_USER", "admin"), os.getenv("OPENSEARCH_PASS", "admin")),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
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
                        "s3_url": {"type": "keyword"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 768  # Dimension for text-embedding-004
                        }
                    }
                }
            }
            opensearch_client.indices.create(index=INDEX_NAME, body=index_body)
            print(f"✅ Created OpenSearch Index: {INDEX_NAME}")
    except Exception as e:
        print(f"⚠️ OpenSearch Connection Warning: {e}")

def upload_to_s3(local_path, file_name):
    """Uploads the processed video to AWS S3 for permanent storage."""
    try:
        s3_client.upload_file(local_path, BUCKET_NAME, file_name)
        return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{file_name}"
    except Exception as e:
        print(f"❌ S3 Upload Failed: {e}")
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
    """Handles video upload, S3 storage, Gemini processing, and OpenSearch indexing."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    try:
        # Save file locally for processing
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 1. Permanent storage in AWS S3
        s3_url = upload_to_s3(file_path, file.filename)
        if not s3_url:
            raise HTTPException(status_code=500, detail="Cloud storage upload failed.")

        # 2. Processing with Gemini Flash
        video_file = client.files.upload(file=file_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        # 3. Generate Transcript
        prompt = "Provide a full transcript with timestamps. Format: [MM:SS - MM:SS] Text."
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, prompt]
        )

        # 4. Vectorize and Index
        chunks = split_into_chunks(response.text)
        for chunk in chunks:
            embed = client.models.embed_content(model="text-embedding-004", contents=chunk)
            
            doc = {
                "video_id": file.filename,
                "text_chunk": chunk,
                "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
                "s3_url": s3_url,
                "embedding": embed.embeddings[0].values
            }
            try:
                opensearch_client.index(index=INDEX_NAME, body=doc)
            except:
                pass

        os.remove(file_path)
        return {"status": "success", "video_id": file.filename, "s3_url": s3_url}

    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """Retrieves relevant video context and generates an AI answer using Flash Lite."""
    try:
        # 1. Embed Question
        embed = client.models.embed_content(model="text-embedding-004", contents=request.question)
        
        # 2. Search OpenSearch (RAG)
        search_query = {
            "size": 3,
            "query": {"knn": {"embedding": {"vector": embed.embeddings[0].values, "k": 3}}}
        }
        
        context = ""
        try:
            res = opensearch_client.search(index=INDEX_NAME, body=search_query)
            context = "\n".join([hit['_source']['text_chunk'] for hit in res['hits']['hits']])
        except:
            context = "Context unavailable (DB Offline)."

        # 3. Generate Answer with Gemini Flash Lite
        system_instr = "Answer based ONLY on context. Include timestamps as: ⏱️ [Video Reference: MM:SS - MM:SS]"
        config = types.GenerateContentConfig(system_instruction=system_instr, temperature=0.0)
        
        history = "\n".join([f"{m.role}: {m.content}" for m in request.chat_history])
        final_prompt = f"Context: {context}\nHistory: {history}\nQuestion: {request.question}"
        
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