# services/video_processor.py
import time
import subprocess
import math
import os
import traceback
from datetime import datetime
from typing import Dict
from google.genai import types

from config import FFMPEG_CMD, UPLOAD_DIR, STATUS_CACHE_TTL, AWS_REGION, BUCKET_NAME, OUTPUT_BUCKET_NAME
from services.redis_service import save_to_redis, upload_statuses
from services.opensearch_service import opensearch_client, INDEX_NAME
from services.s3_service import s3_client, upload_text_to_s3
from services.gemini_service import client, get_transcription_prompt
from utils.helpers import get_video_duration_seconds
from utils.chunking import split_into_chunks
from utils.timestamps import adjust_timestamps

def build_s3_key(folder_path: str, filename: str) -> str:
    """Safely constructs S3 key by stripping leading/trailing slashes from folder_path."""
    if not folder_path or folder_path.strip() == "":
        return filename
    # Strip leading and trailing slashes from folder_path
    clean_folder = folder_path.strip().strip('/')
    return f"{clean_folder}/{filename}" if clean_folder else filename

def build_video_s3_key(folder_path: str, filename: str) -> str:
    """Constructs S3 key for videos with raw/ prefix."""
    base_key = build_s3_key(folder_path, filename)
    return f"raw/{base_key}"

def generate_and_upload_thumbnail(video_url, video_id, time_offset=5):
    """Generates a thumbnail from the video URL using FFmpeg and uploads it directly to S3."""
    try:
        # Clean video_id: remove any file extensions and path separators
        clean_video_id = video_id.replace('.mp4', '').replace('.mov', '').replace('.avi', '').strip('/')
        thumbnail_filename = f"{clean_video_id}.jpg"
        thumbnail_s3_key = f"thumbnails/{thumbnail_filename}"
        
        print(f"🖼️ Generating thumbnail...")
        print(f"   Video ID: {video_id}")
        print(f"   Clean ID: {clean_video_id}")
        print(f"   S3 Key: {thumbnail_s3_key}")
        
        try:
            s3_client.head_object(Bucket=OUTPUT_BUCKET_NAME, Key=thumbnail_s3_key)
            print(f"   ✅ Thumbnail already exists")
            return f"https://{OUTPUT_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
        except:
            pass
        
        temp_jpg = os.path.join(UPLOAD_DIR, f"{clean_video_id}_thumb.jpg")
        
        subprocess.run([
            FFMPEG_CMD, "-y", "-ss", str(time_offset), "-i", video_url,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=320:180", temp_jpg
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        
        with open(temp_jpg, 'rb') as f:
            s3_client.put_object(
                Bucket=OUTPUT_BUCKET_NAME, 
                Key=thumbnail_s3_key,
                Body=f.read(), 
                ContentType='image/jpeg'
            )
        
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        
        print(f"   ✅ Thumbnail uploaded: {thumbnail_s3_key}")
        return f"https://{OUTPUT_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{thumbnail_s3_key}"
    except Exception as e:
        print(f"⚠️ Could not generate thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None

def process_video_background(video_id: str, original_title: str = None, folder_path: str = ""):
    """Processes large videos in the background by streaming from S3 and splitting them into chunks to avoid memory and API limits."""
    
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
    
    def discover_s3_key(folder_path: str, video_id: str) -> str:
        """Fuzzy S3 key discovery using list_objects_v2 - lists all files and matches by video_id."""
        # Clean the folder path
        clean_folder = folder_path.strip().strip('/') if folder_path else ""
        
        # Construct the prefix to search in
        if clean_folder:
            prefix = f"raw/{clean_folder}/"
        else:
            prefix = "raw/"
        
        print(f"\n" + "="*70)
        print(f"🔍 FUZZY S3 KEY DISCOVERY")
        print(f"="*70)
        print(f"📁 Folder Path: '{folder_path}'")
        print(f"📁 Clean Folder: '{clean_folder}'")
        print(f"🎯 Video ID: '{video_id}'")
        print(f"🔎 S3 Prefix: '{prefix}'")
        print(f"🪣 Bucket: '{BUCKET_NAME}'")
        print(f"="*70)
        
        try:
            # List all objects with the prefix
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                print(f"⚠️  No files found in S3 with prefix: {prefix}")
                raise FileNotFoundError(f"No files found in S3 bucket '{BUCKET_NAME}' with prefix '{prefix}'")
            
            # Log all files found
            all_keys = [obj['Key'] for obj in response['Contents']]
            print(f"\n📋 Found {len(all_keys)} file(s) in S3:")
            for idx, key in enumerate(all_keys, 1):
                print(f"   {idx}. {key}")
            
            # Clean video_id for matching (remove extensions)
            clean_video_id = video_id.replace('.mp4', '').replace('.mov', '').replace('.avi', '').strip()
            
            print(f"\n🔍 Searching for video_id: '{video_id}' (clean: '{clean_video_id}')")
            print(f"="*70)
            
            # Try exact matches first
            for key in all_keys:
                filename = key.split('/')[-1]  # Get just the filename
                print(f"   Checking: {filename}")
                
                # Exact match with video_id
                if filename == video_id:
                    print(f"   ✅ EXACT MATCH: {key}")
                    return key
                
                # Exact match with clean video_id
                if filename == clean_video_id:
                    print(f"   ✅ EXACT MATCH (clean): {key}")
                    return key
                
                # Exact match with extensions
                if filename == f"{video_id}.mp4" or filename == f"{clean_video_id}.mp4":
                    print(f"   ✅ EXACT MATCH (.mp4): {key}")
                    return key
            
            print(f"\n   No exact matches found. Trying fuzzy matching...")
            
            # Fuzzy matching - check if video_id is contained in filename
            for key in all_keys:
                filename = key.split('/')[-1]
                filename_lower = filename.lower()
                video_id_lower = video_id.lower()
                clean_video_id_lower = clean_video_id.lower()
                
                # Check if video_id is contained in filename (case-insensitive)
                if video_id_lower in filename_lower or clean_video_id_lower in filename_lower:
                    print(f"   ✅ FUZZY MATCH: {key}")
                    print(f"      ('{video_id}' found in '{filename}')")
                    return key
            
            # No matches found
            print(f"\n❌ NO MATCHES FOUND")
            print(f"="*70)
            raise FileNotFoundError(
                f"Video not found in S3.\n"
                f"  Bucket: {BUCKET_NAME}\n"
                f"  Prefix: {prefix}\n"
                f"  Video ID: {video_id}\n"
                f"  Files found: {len(all_keys)}\n"
                f"  Files: {', '.join([k.split('/')[-1] for k in all_keys[:5]])}{'...' if len(all_keys) > 5 else ''}"
            )
            
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                raise
            print(f"\n❌ ERROR during S3 listing: {e}")
            import traceback
            traceback.print_exc()
            raise FileNotFoundError(f"Failed to list S3 objects: {str(e)}")
    
    try:
        if not original_title:
            if "---" in video_id:
                original_title = video_id.split("---")[-1].replace(".mp4", "").replace("_", " ")

        update_status("uploading", "Processing video from cloud storage...", 10)
        
        # 1. Smart S3 Key Discovery
        s3_key = discover_s3_key(folder_path, video_id)
        print(f"🔍 Final S3 Key: {s3_key}")
        print(f"🔍 Bucket: {BUCKET_NAME}")
        
        video_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=43200
        )
        print(f"🔍 Presigned URL: {video_url[:100]}...")
        video_s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        
        # 2. Extract Duration
        duration_sec = get_video_duration_seconds(video_url)
        print(f"✅ Extracted duration: {duration_sec} seconds")
        
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
        prompt = get_transcription_prompt()

        for i in range(total_parts):
            try:
                start_time = i * CHUNK_DURATION
                chunk_file = os.path.join(UPLOAD_DIR, f"{video_id}_part{i}.mp4")
                update_status("processing", f"Transcribing part {i+1} of {total_parts}...", 30 + int((i/total_parts)*40))
                
                # FFmpeg Chunking
                subprocess.run([
                    FFMPEG_CMD, "-y", "-i", video_url,
                    "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                    "-c", "copy", chunk_file
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Gemini Upload
                video_file_gemini = client.files.upload(file=chunk_file)
                while video_file_gemini.state.name == "PROCESSING":
                    time.sleep(5)
                    video_file_gemini = client.files.get(name=video_file_gemini.name)

                # Model Generation (Gemini 2.5 Flash)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[video_file_gemini, prompt]
                )
                
                adjusted_transcript = adjust_timestamps(response.text, int(start_time))
                full_transcript += adjusted_transcript + "\n\n"
                
                # Cleanup Gemini file & Local chunk
                client.files.delete(name=video_file_gemini.name)
                if os.path.exists(chunk_file): os.remove(chunk_file)
                
                print(f"✅ Part {i+1} success.")
                time.sleep(2) # Avoid rate limits

            except Exception as chunk_e:
                print(f"❌ Error in chunk {i}: {chunk_e}")
                traceback.print_exc()
                continue

        # 5. Save Transcript & Index to OpenSearch
        update_status("transcript_generated", "Indexing to OpenSearch...", 80)
        
        # Clean video_id for transcript filename (remove extensions and slashes)
        clean_video_id = video_id.replace('.mp4', '').replace('.mov', '').replace('.avi', '').strip('/')
        transcript_s3_url = upload_text_to_s3(full_transcript, f"transcripts/{clean_video_id}.txt")
        
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
                print(f"⚠️ Indexing error: {e}")

        # 6. Complete
        completed_data = {
            "status": "completed",
            "message": "Processing complete!",
            "progress": 100,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "video_s3_url": video_s3_url, "duration": formatted_duration, "thumbnail_url": thumbnail_url
            }
        }
        save_to_redis(f"video_status:{video_id}", completed_data, ttl_seconds=STATUS_CACHE_TTL)
        print(f"🏁 [{video_id}] Final Status: COMPLETED")

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN BACKGROUND TASK: {str(e)}")
        traceback.print_exc()
        update_status("error", f"Processing failed: {str(e)}", 0)