# services/video_processor.py
import time
import subprocess
import math
import os
import traceback
from datetime import datetime
from typing import Dict
from google.genai import types

from config import FFMPEG_CMD, UPLOAD_DIR, STATUS_CACHE_TTL, AWS_REGION, BUCKET_NAME
from services.redis_service import save_to_redis, upload_statuses
from services.opensearch_service import opensearch_client, INDEX_NAME
from services.s3_service import s3_client, upload_text_to_s3
from services.gemini_service import client, get_transcription_prompt
from utils.helpers import get_video_duration_seconds
from utils.chunking import split_into_chunks
from utils.timestamps import adjust_timestamps

def generate_and_upload_thumbnail(video_url, video_id, time_offset=5):
    """Generates a thumbnail from the video URL using FFmpeg and uploads it directly to S3."""
    try:
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"
        
        # Return existing URL if already in S3
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=thumbnail_s3_key)
            return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
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
        
        return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
    except Exception as e:
        print(f"⚠️ Could not generate thumbnail: {e}")
        temp_jpg = os.path.join(UPLOAD_DIR, f"{video_id}_thumb.jpg")
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        return None

def process_video_background(video_id: str, original_title: str = None):
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
        # Extract original_title from video_id if not provided
        if not original_title:
            # Try to extract from video_id (format: unique_id---original_name)
            if "---" in video_id:
                original_title = video_id.split("---")[-1].replace(".mp4", "").replace("_", " ")

        # Status 1: UPLOADING
        update_status("uploading", "Processing video from cloud storage...", 10)
        
        # Generate a pre-signed GET URL for reading the video from S3 (valid for 12 hours)
        video_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
            ExpiresIn=43200
        )
        
        # Construct the public S3 URL for storing in the database
        video_s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video_id}"
        
        # Extract metadata using ffprobe with the presigned URL
        duration_sec = get_video_duration_seconds(video_url)
        print(f"Video duration (seconds): {duration_sec}")
        # Calculate Hours, Minutes, and Seconds properly
        hours = int(duration_sec // 3600)
        minutes = int((duration_sec % 3600) // 60)
        seconds = int(duration_sec % 60)
        
        if hours > 0:
            formatted_duration = f"{hours}:{minutes:02d}:{seconds:02d}"
            print(f"Video duration (H:MM:SS): {formatted_duration}")
        else:
            formatted_duration = f"{minutes}:{seconds:02d}"
            print(f"Video duration (M:SS): {formatted_duration}")
        
        # Generate thumbnail using FFmpeg with the presigned URL
        thumbnail_url = generate_and_upload_thumbnail(video_url, video_id)

        # Status 2: UPLOADED 
        update_status("uploaded", "Video uploaded, starting transcription...", 30)

        # CHUNKING LOGIC: Split video into 15-min chunks (900s)
        CHUNK_DURATION = 900
        total_parts = math.ceil(duration_sec / CHUNK_DURATION) if duration_sec > 0 else 1
        full_transcript = ""

        prompt = get_transcription_prompt()

        for i in range(total_parts):
            try:
                start_time = i * CHUNK_DURATION
                chunk_file = os.path.join(UPLOAD_DIR, f"{video_id}_part{i}.mp4")
                
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

                # Retry mechanism (up to 3 times)
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
                        break
                    except Exception as api_e:
                        print(f"⚠️ Gemini API attempt {attempt+1} failed for part {i+1}: {api_e}")
                        time.sleep(15)

                if adjusted_transcript:
                    full_transcript += adjusted_transcript + "\n\n"
                else:
                    full_transcript += f"\n\n[⚠️ Error: Could not transcribe this section ({start_time//60} mins to {(start_time+CHUNK_DURATION)//60} mins)]\n\n"
                
                # Cleanup
                try:
                    client.files.delete(name=video_file_gemini.name)
                except:
                    pass
                if os.path.exists(chunk_file):
                    os.remove(chunk_file)
                
                print(f"✅ Part {i+1} transcribed and cleaned up.")
                time.sleep(10)

            except Exception as chunk_e:
                print(f"❌ Critical error in part {i+1}: {chunk_e}")
                full_transcript += f"\n\n[⚠️ Critical Error skipping section ({start_time//60} mins)]\n\n"
                continue

        # Status 3: TRANSCRIPT_GENERATED
        update_status("transcript_generated", "Transcript generated, embedding and saving...", 80)
        
        # Save the combined full transcript to AWS S3
        transcript_s3_url = upload_text_to_s3(full_transcript, f"transcripts/{video_id}.txt")
        
        # Chunk the full text and index to OpenSearch for RAG
        text_chunks = split_into_chunks(full_transcript)
        for chunk in text_chunks:
            if not chunk.strip(): 
                continue
            enriched_content = f"Video Source: {video_id}\nContent: {chunk}"
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001", contents=enriched_content,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768)
                )
                vector = result.embeddings[0].values
                if vector and opensearch_client:
                    opensearch_client.index(index=INDEX_NAME, body={
                        "video_id": video_id, 
                        "text_chunk": chunk,
                        "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
                        "video_s3_url": video_s3_url, 
                        "transcript_s3_url": transcript_s3_url,
                        "duration": formatted_duration, 
                        "embedding": vector,
                        "original_title": original_title  # Store original title
                    })
            except Exception as e:
                pass 

        # Status 4: COMPLETED
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
        
        if not save_to_redis(f"video_status:{video_id}", completed_data, ttl_seconds=STATUS_CACHE_TTL):
            upload_statuses[video_id] = completed_data
            
    except Exception as e:
        print(f"\n❌ FATAL ERROR IN BACKGROUND TASK: {str(e)}")
        traceback.print_exc()
        update_status("error", f"Processing failed: {str(e)}", 0)