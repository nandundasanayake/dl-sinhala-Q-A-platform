# services/video_processor.py
import time
import subprocess
import math
import os
import traceback
from datetime import datetime
from typing import Dict
from google.genai import types

from config import FFMPEG_CMD, UPLOAD_DIR, STATUS_CACHE_TTL, AWS_REGION, S3_REGION, BUCKET_NAME, OUTPUT_BUCKET_NAME
from services.redis_service import save_to_redis, upload_statuses
from services.opensearch_service import opensearch_client, INDEX_NAME
from services.s3_service import s3_client, upload_text_to_s3
from services.gemini_service import client, get_transcription_prompt, get_roadmap_prompt_template
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
            return f"https://{OUTPUT_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{thumbnail_s3_key}"
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
        return f"https://{OUTPUT_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{thumbnail_s3_key}"
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
        video_s3_url = f"https://{BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{s3_key}"
        
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
        chunk_summaries = []  # Collect summaries for roadmap generation
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

                # Verify chunk file was created and has content
                if not os.path.exists(chunk_file):
                    raise Exception(f"FFmpeg failed to create chunk file: {chunk_file}")
                
                chunk_size = os.path.getsize(chunk_file)
                if chunk_size == 0:
                    raise Exception(f"Chunk file is empty: {chunk_file}")
                
                print(f"📦 Chunk {i+1} created: {chunk_size / (1024*1024):.2f} MB")

                # Gemini Upload with retry logic
                max_retries = 3
                retry_count = 0
                video_file_gemini = None
                last_error = None
                
                while retry_count <= max_retries:
                    try:
                        # Open file fresh for each attempt to avoid stale file handles
                        print(f"📤 Uploading chunk {i+1} to Gemini (attempt {retry_count + 1}/{max_retries + 1})...")
                        
                        # For retries after "Upload has already been terminated", recreate the chunk
                        if retry_count > 0 and last_error and "terminated" in str(last_error).lower():
                            print(f"🔄 Recreating chunk file due to terminated upload session...")
                            if os.path.exists(chunk_file):
                                os.remove(chunk_file)
                            
                            # Recreate the chunk
                            subprocess.run([
                                FFMPEG_CMD, "-y", "-i", video_url,
                                "-ss", str(start_time), "-t", str(CHUNK_DURATION),
                                "-c", "copy", chunk_file
                            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            
                            # Add extra delay to let Gemini API reset
                            time.sleep(10)
                        
                        video_file_gemini = client.files.upload(file=chunk_file)
                        print(f"✅ Upload successful, file ID: {video_file_gemini.name}")
                        break  # Success, exit retry loop
                        
                    except Exception as upload_error:
                        last_error = upload_error
                        retry_count += 1
                        error_msg = str(upload_error)
                        print(f"❌ Upload attempt {retry_count} failed: {error_msg}")
                        
                        if retry_count > max_retries:
                            # Check if this is a quota/rate limit issue
                            if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                                raise Exception(f"Gemini API quota/rate limit exceeded. Please try again later. Error: {upload_error}")
                            raise Exception(f"Gemini upload failed after {max_retries} retries: {upload_error}")
                        
                        # Exponential backoff: 10s, 20s, 30s
                        wait_time = retry_count * 10
                        print(f"⏳ Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                
                if not video_file_gemini:
                    raise Exception("Failed to upload video chunk to Gemini")
                
                # Wait for processing
                print(f"⏳ Waiting for Gemini to process chunk {i+1}...")
                processing_timeout = 300  # 5 minutes
                processing_start = time.time()
                
                while video_file_gemini.state.name == "PROCESSING":
                    if time.time() - processing_start > processing_timeout:
                        raise Exception(f"Gemini processing timeout after {processing_timeout}s")
                    time.sleep(5)
                    video_file_gemini = client.files.get(name=video_file_gemini.name)
                
                if video_file_gemini.state.name != "ACTIVE":
                    raise Exception(f"Gemini file processing failed with state: {video_file_gemini.state.name}")

                # Model Generation (Gemini 2.5 Flash)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[video_file_gemini, prompt]
                )
                
                adjusted_transcript = adjust_timestamps(response.text, int(start_time))
                full_transcript += adjusted_transcript + "\n\n"
                
                # Generate chunk summary for roadmap (Map step)
                print(f"📝 Generating summary for chunk {i+1}...")
                try:
                    summary_prompt = """Summarize the following transcript segment into 3-4 bullet points focusing on core educational concepts. Include the start time.
Transcript:""" + adjusted_transcript
                    
                    summary_response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=summary_prompt
                    )
                    
                    chunk_summary = summary_response.text.strip()
                    chunk_summaries.append(f"=== Chunk {i+1} (Time: {start_time//60}:{start_time%60:02d}) ===\n{chunk_summary}")
                    print(f"✅ Summary generated for chunk {i+1}")
                    
                except Exception as summary_error:
                    print(f"⚠️ Failed to generate summary for chunk {i+1}: {summary_error}")
                    # Fallback: use first 500 chars of transcript as summary
                    fallback_summary = adjusted_transcript[:500] + "..." if len(adjusted_transcript) > 500 else adjusted_transcript
                    chunk_summaries.append(f"=== Chunk {i+1} (Time: {start_time//60}:{start_time%60:02d}) ===\n{fallback_summary}")
                
                # Cleanup Gemini file & Local chunk
                client.files.delete(name=video_file_gemini.name)
                if os.path.exists(chunk_file): os.remove(chunk_file)
                
                print(f"✅ Part {i+1} success.")
                time.sleep(2) # Avoid rate limits

            except Exception as chunk_e:
                print(f"❌ Error in chunk {i}: {chunk_e}")
                traceback.print_exc()
                # Clean up chunk file if it exists
                if os.path.exists(chunk_file):
                    try:
                        os.remove(chunk_file)
                    except Exception:
                        pass
                continue

        # 5. Validate transcript (but continue even if empty)
        transcript_available = bool(full_transcript and len(full_transcript.strip()) >= 50)
        
        if not transcript_available:
            print(f"⚠️ Transcription failed or produced minimal output")
            print(f"   Transcript length: {len(full_transcript.strip()) if full_transcript else 0} characters")
            print(f"   Continuing processing without transcript...")
            full_transcript = ""  # Empty transcript, but continue processing

        # 6. Generate Roadmap from Chunk Summaries (Reduce step - only if transcript exists)
        roadmap_available = False
        if transcript_available and chunk_summaries:
            print("\n🗺️ Generating roadmap from chunk summaries...")
            print(f"   Total chunks summarized: {len(chunk_summaries)}")
            update_status("processing", "Generating lesson roadmap...", 75)
            
            try:
                # Load roadmap generation prompt using the service function
                roadmap_prompt_template = get_roadmap_prompt_template()
                
                # Merge all chunk summaries (Reduce step)
                merged_summaries = "\n\n".join(chunk_summaries)
                print(f"   Merged summaries length: {len(merged_summaries)} characters")
                
                # Replace placeholder with merged summaries
                roadmap_prompt = roadmap_prompt_template.replace("{merged_summaries}", merged_summaries)
                
                # Generate roadmap using Gemini (same model as transcription)
                roadmap_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=roadmap_prompt
                )
                
                roadmap_json_text = roadmap_response.text.strip()
                
                # Clean up markdown code blocks if present
                if roadmap_json_text.startswith("```json"):
                    roadmap_json_text = roadmap_json_text.replace("```json", "").replace("```", "").strip()
                elif roadmap_json_text.startswith("```"):
                    roadmap_json_text = roadmap_json_text.replace("```", "").strip()
                
                # Validate JSON
                import json
                roadmap_data = json.loads(roadmap_json_text)
                
                # Append roadmap to transcript
                full_transcript += "\n\n=== VIDEO ROADMAP ===\n"
                full_transcript += json.dumps(roadmap_data, ensure_ascii=False, indent=2)
                
                roadmap_available = True
                print(f"✅ Roadmap generated successfully with {len(roadmap_data)} chapters")
                
            except Exception as roadmap_error:
                print(f"⚠️ Roadmap generation failed: {roadmap_error}")
                print("   Continuing without roadmap...")
                import traceback
                traceback.print_exc()
                # Don't fail the entire process if roadmap generation fails
        else:
            if not transcript_available:
                print("⚠️ Skipping roadmap generation (no transcript available)")
            elif not chunk_summaries:
                print("⚠️ Skipping roadmap generation (no chunk summaries available)")

        # 7. Save Transcript & Index to OpenSearch (only if transcript exists)
        update_status("transcript_generated", "Finalizing processing...", 80)
        
        transcript_s3_url = None
        if transcript_available:
            # Clean video_id for transcript filename (remove extensions and slashes)
            clean_video_id = video_id.replace('.mp4', '').replace('.mov', '').replace('.avi', '').strip('/')
            transcript_s3_url = upload_text_to_s3(full_transcript, f"transcripts/{clean_video_id}.txt")
            
            # Index to OpenSearch
            text_chunks = split_into_chunks(full_transcript)
            indexed_chunks = 0
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
                    indexed_chunks += 1
                except Exception as e:
                    print(f"⚠️ Indexing error: {e}")
            
            print(f"✅ Indexed {indexed_chunks} chunks to OpenSearch")
        else:
            print("⚠️ No transcript to save or index")

        # 8. Complete (ALWAYS reach here, even if transcript/roadmap failed)
        completion_message = "Processing complete!"
        if not transcript_available:
            completion_message = "Processing complete (transcript unavailable)"
        elif not roadmap_available:
            completion_message = "Processing complete (roadmap unavailable)"
        
        completed_data = {
            "status": "completed",
            "message": completion_message,
            "progress": 100,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "video_s3_url": video_s3_url,
                "duration": formatted_duration,
                "thumbnail_url": thumbnail_url,
                "transcript_s3_url": transcript_s3_url,
                "transcript_status": "available" if transcript_available else "unavailable",
                "has_transcript": transcript_available,
                "has_roadmap": roadmap_available
            }
        }
        save_to_redis(f"video_status:{video_id}", completed_data, ttl_seconds=STATUS_CACHE_TTL)
        print(f"🏁 [{video_id}] Final Status: COMPLETED")
        print(f"   Transcript: {'✅ Available' if transcript_available else '❌ Unavailable'}")
        print(f"   Roadmap: {'✅ Available' if roadmap_available else '❌ Unavailable'}")

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN BACKGROUND TASK: {str(e)}")
        traceback.print_exc()
        update_status("error", f"Processing failed: {str(e)}", 0)