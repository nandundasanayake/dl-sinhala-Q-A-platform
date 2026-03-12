import os
import time
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(title="Enterprise Video RAG API", version="1.0")

# Configure CORS to allow requests from the React frontend (Vite runs on port 5173 by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Retrieve the Gemini API Key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in the environment variables.")

# Initialize the Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Define and create a temporary directory for incoming video uploads
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload-video")
async def upload_and_process_video(file: UploadFile = File(...)):
    """
    API Endpoint to handle video uploads, send the file to Google Gemini, 
    and automatically extract a fully timestamped transcript.
    """
    # Validate the uploaded file format
    if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a valid video file.")

    # Create a safe local path for the uploaded video
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    try:
        # Step 1: Save the uploaded file temporarily to the local server
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Step 2: Upload the saved video to Google Gemini for processing
        video_file = client.files.upload(file=file_path)

        # Step 3: Wait asynchronously until Gemini finishes processing the video
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise HTTPException(status_code=500, detail="Video processing failed on Google servers.")

        # Step 4: Construct the strict prompt to extract timestamps alongside the transcript
        extraction_prompt = (
            "Please provide a complete and accurate transcript of everything spoken in this video. "
            "You MUST include timestamps for every logical segment or sentence. "
            "Format each line exactly like this: [MM:SS - MM:SS] Spoken text here. "
            "Do not add any extra summaries or outside information."
        )

        # Step 5: Request the transcript generation using the Flash model
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, extraction_prompt]
        )

        # Step 6: Clean up the local temporary file to optimize server storage
        os.remove(file_path)

        # Return the successful response back to the React frontend
        return {
            "status": "success",
            "message": "Video processed and transcript generated successfully.",
            "transcript": response.text,
            "video_id": video_file.name # ID required if we need to reference this video in future Gemini calls
        }

    except Exception as e:
        # Ensure the temporary file is deleted even if the process crashes
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Health check endpoint to verify the API is running
@app.get("/health")
def health_check():
    return {"status": "Backend API is running smoothly."}