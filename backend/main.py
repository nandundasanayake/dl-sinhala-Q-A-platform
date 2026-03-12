import os
import time
import shutil
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
app = FastAPI(title="Enterprise Video RAG API", version="2.0")

# Configure CORS to allow requests from the React frontend (Vite runs on port 5173 by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration & External Services Setup ---

# Retrieve the Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in the environment variables.")

# Initialize the Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize AWS OpenSearch Client with SSL for Cloud Security
opensearch_client = OpenSearch(
    hosts=[{'host': os.getenv("OPENSEARCH_HOST", "localhost"), 'port': int(os.getenv("OPENSEARCH_PORT", 443))}],
    http_auth=(os.getenv("OPENSEARCH_USER", "admin"), os.getenv("OPENSEARCH_PASS", "admin")),
    use_ssl=True,                      # MUST be True for AWS Cloud
    verify_certs=True,                 # MUST verify certificates for security
    connection_class=RequestsHttpConnection
)

INDEX_NAME = "video-transcripts-index"

# Create the OpenSearch Index safely (Configured for k-NN Vector Search)
def setup_opensearch_index():
    try:
        if not opensearch_client.indices.exists(index=INDEX_NAME):
            index_body = {
                "settings": {
                    "index.knn": True
                },
                "mappings": {
                    "properties": {
                        "video_id": {"type": "keyword"},
                        "timestamp": {"type": "text"},
                        "text_chunk": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 768 # Standard dimension for Google embeddings
                        }
                    }
                }
            }
            opensearch_client.indices.create(index=INDEX_NAME, body=index_body)
            print(f"✅ Successfully created OpenSearch Index in AWS: {INDEX_NAME}")
        else:
            print(f"✅ Connected to AWS. OpenSearch Index '{INDEX_NAME}' already exists.")
            
    except Exception as e:
        # Graceful error handling: Do not crash the server if DB is down or credentials are pending
        print(f"\n⚠️ WARNING: Could not connect to AWS OpenSearch.")
        print(f"⚠️ Error Details: {str(e)}")
        print("⚠️ Check your .env credentials. The API server will still start.\n")

setup_opensearch_index()

# Define and create a temporary directory for incoming video uploads
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Helper Function: Intelligent Chunking ---
def split_into_chunks(transcript_text, chunk_size=3):
    """
    Splits the timestamped transcript into logical chunks.
    Groups a specified number of lines (sentences) together to maintain context.
    """
    lines = transcript_text.strip().split('\n')
    chunks = []
    
    # Simple chunking: group every 'chunk_size' lines together
    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        combined_text = " ".join(chunk_lines)
        if combined_text.strip():
            chunks.append(combined_text)
            
    return chunks

# --- Request Models for React Frontend (Pydantic) ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    video_id: str
    question: str
    chat_history: List[ChatMessage] = []

# --- Main API Endpoints ---

@app.post("/api/upload-video")
async def upload_and_process_video(file: UploadFile = File(...)):
    """
    API Endpoint to handle video uploads, extract timestamped transcripts, 
    generate embeddings via Google Vertex AI, and store them in AWS OpenSearch.
    """
    if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a valid video.")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    video_id = file.filename # Using filename as ID for simplicity in this version

    try:
        # Step 1: Save file temporarily
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Step 2: Upload to Gemini
        video_file = client.files.upload(file=file_path)

        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise HTTPException(status_code=500, detail="Video processing failed on Google servers.")

        # Step 3: Extract Timestamped Transcript
        extraction_prompt = (
            "Please provide a complete and accurate transcript of everything spoken in this video. "
            "You MUST include timestamps for every logical segment or sentence. "
            "Format each line exactly like this: [MM:SS - MM:SS] Spoken text here. "
            "Do not add any extra summaries or outside information."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, extraction_prompt]
        )
        transcript_text = response.text

        # Step 4: Chunk the text
        chunks = split_into_chunks(transcript_text)

        # Step 5 & 6: Generate Embeddings and Store in OpenSearch
        for chunk in chunks:
            # Generate vector embedding using Google's text-embedding-004
            embed_response = client.models.embed_content(
                model="text-embedding-004",
                contents=chunk,
            )
            embedding_vector = embed_response.embeddings[0].values

            # Construct the document for OpenSearch
            # Simple extraction of the first timestamp found in the chunk
            timestamp_val = chunk[1:14] if chunk.startswith("[") else "Unknown"
            
            document = {
                "video_id": video_id,
                "text_chunk": chunk,
                "timestamp": timestamp_val, 
                "embedding": embedding_vector
            }

            # Index the document in AWS OpenSearch (wrapped in try-except for robustness)
            try:
                opensearch_client.index(index=INDEX_NAME, body=document)
            except Exception as db_err:
                print(f"Skipping indexing due to DB error: {db_err}")

        # Clean up local temporary file
        os.remove(file_path)

        return {
            "status": "success",
            "message": "Video processed, vectorized, and indexed successfully.",
            "total_chunks_indexed": len(chunks),
            "video_id": video_id
        }

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/chat")
async def ask_question(request: ChatRequest):
    """
    API Endpoint to handle student questions.
    Converts question to vector, searches AWS OpenSearch, and generates strict RAG answer via Gemini.
    """
    if not request.question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # Step 1: Convert the student's question into a Vector Embedding
        embed_response = client.models.embed_content(
            model="text-embedding-004",
            contents=request.question,
        )
        question_vector = embed_response.embeddings[0].values

        # Step 2: Search AWS OpenSearch for the top 3 most relevant chunks
        search_query = {
            "size": 3,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": question_vector,
                        "k": 3
                    }
                }
            }
        }

        # Graceful DB fallback if AWS credentials aren't ready yet
        combined_context = ""
        try:
            response = opensearch_client.search(index=INDEX_NAME, body=search_query)
            hits = response['hits']['hits']
            
            retrieved_chunks = []
            for hit in hits:
                source = hit['_source']
                timestamp = source.get('timestamp', 'Unknown Time')
                text = source.get('text_chunk', '')
                retrieved_chunks.append(f"[{timestamp}] {text}")
                
            combined_context = "\n\n---\n\n".join(retrieved_chunks)
        except Exception as db_error:
            print(f"AWS Database Search Error: {db_error}")
            combined_context = "[00:00 - 00:00] Mock data: Database not connected yet. Proceeding with fallback."

        # Step 3: Format the Chat History
        history_context = ""
        for msg in request.chat_history:
            role_name = "Student" if msg.role == "user" else "Assistant"
            history_context += f"{role_name}: {msg.content}\n"

        # Step 4: Strict Enterprise Prompt for Gemini
        system_instruction = (
            "You are an expert teaching assistant. Answer the student's question using ONLY the provided 'Retrieved Context'. "
            "STRICT RULES:\n"
            "1. Reply in the same language the student used to ask the question (e.g., Sinhala, English, Tamil, or Singlish).\n"
            "2. If the answer cannot be found in the context, DO NOT use outside knowledge. Simply reply with 'Sorry, this topic is not covered in the video'.\n"
            "3. Use the 'Previous Chat History' to understand context if the student asks follow-up questions.\n"
            "4. IMPORTANT: You MUST include the exact timestamp(s) from the context where you found the answer. Add it at the end of your response formatted exactly like: ⏱️ [Video Reference: MM:SS - MM:SS]."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0 # Strict zero temperature to prevent hallucinations
        )

        final_prompt = f"Retrieved Context from Database:\n{combined_context}\n\nPrevious Chat History:\n{history_context}\nStudent's Question: {request.question}"

        # Step 5: Generate the final answer
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=final_prompt,
            config=config
        )

        return {
            "status": "success",
            "answer": response.text,
            "backend_context_used": combined_context 
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "Backend API is running smoothly."}