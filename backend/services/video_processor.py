# services/video_processor.py
import time
import subprocess
import math
import os
import traceback
from datetime import datetime
from typing import Dict
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import logging

logger = logging.getLogger(__name__)

from config import FFMPEG_CMD, UPLOAD_DIR, STATUS_CACHE_TTL, AWS_REGION, BUCKET_NAME
from services.redis_service import save_to_redis, upload_statuses
from services.opensearch_service import opensearch_client, INDEX_NAME
from services.s3_service import s3_client, upload_text_to_s3
from services.gemini_service import client, get_transcription_prompt, get_voice_transcription_prompt
from utils.helpers import get_video_duration_seconds
from utils.chunking import split_into_chunks
from utils.timestamps import adjust_timestamps

def generate_and_upload_thumbnail(video_url, video_id, time_offset=5):
    """Generates a thumbnail from the video URL using FFmpeg and uploads it directly to S3."""
    try:
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"
        
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=thumbnail_s3_key)
            return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
        except:
            pass
        
        temp_jpg = os.path.join(UPLOAD_DIR, f"{video_id}_thumb.jpg")
        
        subprocess.run([
            FFMPEG_CMD, "-y", "-ss", str(time_offset), "-i", video_url,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=320:180", temp_jpg
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        
        with open(temp_jpg, 'rb') as f:
            s3_client.put_object(
                Bucket=BUCKET_NAME, 
                Key=thumbnail_s3_key,
                Body=f.read(), 
                ContentType='image/jpeg'
            )
        
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        
        return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
    except Exception as e:
        print(f"⚠️ Could not generate thumbnail: {e}")
        return None

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _call_gemini_generate(gemini_file, prompt):
    """Calls Gemini generate_content with automatic retries on transient errors (e.g. 504 DEADLINE_EXCEEDED)."""
    return client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[gemini_file, prompt]
    )

def process_video_background(video_id: str, original_title: str = None, transcription_mode: str = "video"):
    """Processes large videos in the background by streaming from S3 and splitting them into chunks to avoid memory and API limits.
    
    transcription_mode: 'video' = full video+audio (with on-screen capture), 'voice' = audio-only transcription
    """
    
    def update_status(status, message, progress):
        status_data = {
            "status": status,
            "message": message,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat()
        }
        if not save_to_redis(f"video_status:{video_id}", status_data, ttl_seconds=STATUS_CACHE_TTL):
            upload_statuses[video_id] = status_data 
        print(f"[{video_id}] {status}: {message} ({progress}%)")
    
    try:
        if not original_title:
            if "---" in video_id:
                original_title = video_id.split("---")[-1].replace(".mp4", "").replace("_", " ")

        update_status("uploading", "Processing video from cloud storage...", 10)
        
        # 1. Generate Presigned URL
        video_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"videos/{video_id}"},
            ExpiresIn=43200
        )
        video_s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/videos/{video_id}"
        
        # 2. Extract Duration
        duration_sec = get_video_duration_seconds(video_url)
        print(f"[OK] Extracted duration: {duration_sec} seconds")
        
        hours = int(duration_sec // 3600)
        minutes = int((duration_sec % 3600) // 60)
        seconds = int(duration_sec % 60)
        formatted_duration = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
        
        # 3. Thumbnail
        thumbnail_url = generate_and_upload_thumbnail(video_url, video_id)

        update_status("uploaded", "Video metadata extracted, starting transcription...", 30)

        # 4. Transcription with Gemini 2.5 Flash
        CHUNK_DURATION = 900
        total_parts = math.ceil(duration_sec / CHUNK_DURATION) if duration_sec > 0 else 1
        full_transcript = ""
        all_chunk_summaries = []
        
        # Select prompt based on transcription mode
        is_voice_only = transcription_mode == "voice"
        if is_voice_only:
            prompt = get_voice_transcription_prompt()
            print(f"[MODE] VOICE-ONLY (audio extraction)")
        else:
            prompt = get_transcription_prompt()
            print(f"[MODE] VIDEO + AUDIO (with on-screen capture)")

        for i in range(total_parts):
            start_time = i * CHUNK_DURATION
            chunk_file = None
            gemini_file_ref = None
            update_status("processing", f"Transcribing part {i+1} of {total_parts}...", 30 + int((i/total_parts)*40))
            
            try:
                if is_voice_only:
                    # VOICE-ONLY MODE: Extract audio as .mp3
                    chunk_file = os.path.join(UPLOAD_DIR, f"{video_id}_part{i}.mp3")
                    subprocess.run([
                        FFMPEG_CMD, "-y", "-i", video_url,
                        "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                        "-vn",              # Remove video stream
                        "-acodec", "libmp3lame",
                        "-ab", "128k",       # Audio bitrate
                        chunk_file
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"   [AUDIO] Audio chunk extracted: {chunk_file}")
                else:
                    # VIDEO MODE: Keep full video chunk as .mp4
                    chunk_file = os.path.join(UPLOAD_DIR, f"{video_id}_part{i}.mp4")
                    subprocess.run([
                        FFMPEG_CMD, "-y", "-i", video_url,
                        "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                        "-c", "copy", chunk_file
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"   [VIDEO] Video chunk extracted: {chunk_file}")

                # Gemini Upload (works for both .mp3 and .mp4)
                gemini_file_ref = client.files.upload(file=chunk_file)
                while gemini_file_ref.state.name == "PROCESSING":
                    time.sleep(5)
                    gemini_file_ref = client.files.get(name=gemini_file_ref.name)

                # Model Generation (Gemini 2.5 Flash) — retries up to 3x with exponential backoff
                response = _call_gemini_generate(gemini_file_ref, prompt)
                
                adjusted_transcript = adjust_timestamps(response.text, int(start_time))
                full_transcript += adjusted_transcript + "\n\n"
                
                # MAP PHASE: Generate chunk summary
                try:
                    summary_prompt = f"""Summarize the following transcript segment into 3-4 bullet points focusing on core educational concepts. Include the start time. Transcript: {adjusted_transcript}"""
                    summary_response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=summary_prompt
                    )
                    all_chunk_summaries.append(summary_response.text)
                except Exception as summary_e:
                    print(f"[WARN] Summary generation failed for chunk {i}: {summary_e}")
                
                print(f"[OK] Part {i+1} success.")
                time.sleep(2) # Avoid rate limits

            except Exception as chunk_e:
                # Gemini call failed after all retries (or another critical error) — halt pipeline
                print(f"[FATAL] Unrecoverable error in chunk {i}: {chunk_e}")
                traceback.print_exc()
                update_status("failed", f"Transcription failed on part {i+1}/{total_parts}: {chunk_e}", 0)
                return
            finally:
                # Always clean up Gemini remote file and local chunk, even on failure
                if gemini_file_ref:
                    try:
                        client.files.delete(name=gemini_file_ref.name)
                    except Exception:
                        pass
                if chunk_file and os.path.exists(chunk_file):
                    os.remove(chunk_file)

        # REDUCE PHASE: Generate final roadmap
        formatted_roadmap = ""
        if all_chunk_summaries:
            try:
                update_status("processing", "Generating video roadmap...", 75)
                merged_summaries = "\n\n".join(all_chunk_summaries)
                
                # Read roadmap prompt from text file
                prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'Roadmap_prompt.txt')
                with open(prompt_path, 'r', encoding='utf-8') as file:
                    prompt_template = file.read()
                    
                print("\n" + "=" * 60)
                print("[DEBUG] MERGED SUMMARIES (ADMIN DEBUG VIEW)")
                print("=" * 60)
                print(merged_summaries)
                print("=" * 60 + "\n")

                roadmap_prompt = prompt_template.format(merged_summaries=merged_summaries)
                
                roadmap_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=roadmap_prompt
                )
                
                import json
                roadmap_text = roadmap_response.text.strip()
                if roadmap_text.startswith("```json"):
                    roadmap_text = roadmap_text[7:-3].strip()
                elif roadmap_text.startswith("```"):
                    roadmap_text = roadmap_text[3:-3].strip()
                
                roadmap_json = json.loads(roadmap_text)
                formatted_roadmap = json.dumps(roadmap_json, ensure_ascii=False)
                print(f"[OK] Roadmap generated for {video_id}")
            except Exception as roadmap_e:
                print(f"[WARN] Roadmap generation failed: {roadmap_e}")
                traceback.print_exc()
        
        # Append roadmap to transcript
        if formatted_roadmap:
            full_transcript += f"\n\n=== VIDEO ROADMAP ===\n\n{formatted_roadmap}"

        # 5. Save Transcript & Index to OpenSearch
        update_status("transcript_generated", "Indexing to OpenSearch...", 80)
        transcript_s3_url = upload_text_to_s3(full_transcript, f"transcripts/{video_id}.txt")
        
        text_chunks = split_into_chunks(full_transcript)
        for chunk in text_chunks:
            if not chunk.strip(): continue
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001", 
                    contents=f"Video: {original_title}\nContent: {chunk}",
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768)
                )
                opensearch_client.index(index=INDEX_NAME, body={
                    "video_id": video_id, 
                    "text_chunk": chunk,
                    "timestamp": chunk[1:14] if chunk.startswith("[") else "00:00",
                    "video_s3_url": video_s3_url, 
                    "transcript_s3_url": transcript_s3_url,
                    "duration": formatted_duration, 
                    "embedding": result.embeddings[0].values,
                    "original_title": original_title,
                    "thumbnail_url": thumbnail_url
                })
            except Exception as e:
                print(f"[WARN] Indexing error: {e}")

        # 6. Complete
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
        if not save_to_redis(f"video_status:{video_id}", completed_data, ttl_seconds=STATUS_CACHE_TTL):
            upload_statuses[video_id] = completed_data
        print(f"[DONE] [{video_id}] Final Status: COMPLETED")

    except Exception as e:
        print(f"\n[FATAL] FATAL ERROR IN BACKGROUND TASK: {str(e)}")
        traceback.print_exc()
        update_status("error", f"Processing failed: {str(e)}", 0)