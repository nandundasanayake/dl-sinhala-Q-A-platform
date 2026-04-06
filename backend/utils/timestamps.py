# utils/timestamps.py
import re

def adjust_timestamps(transcript: str, offset_seconds: int) -> str:
    """Adjusts relative timestamps from Gemini, handling spaces and preventing double formatting."""
    
    # Clean up any weird double timestamps Gemini might have hallucinated 
    cleaned_transcript = re.sub(r'\]\s*\d{1,2}:\d{2}(?::\d{2})?\s*-\s*\d{1,2}:\d{2}(?::\d{2})?\s*', '] ', transcript)

    # Updated Regex to handle spaces inside brackets like [ 00:15 - 01:20 ]
    pattern = r'\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]'
    
    def time_to_seconds(time_str):
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return 0

    def seconds_to_time(total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"{m:02d}:{s:02d}"

    def replace_match(match):
        start_raw = match.group(1)
        end_raw = match.group(2)
        
        # Detect if original had hours format
        original_has_hours = ':' in start_raw and start_raw.count(':') == 2
        
        total_start_s = time_to_seconds(start_raw) + offset_seconds
        total_end_s = time_to_seconds(end_raw) + offset_seconds
        
        # If original had hours OR total exceeds 1 hour, use HH:MM:SS format
        if original_has_hours or total_start_s >= 3600 or total_end_s >= 3600:
            return f"[{seconds_to_time(total_start_s)} - {seconds_to_time(total_end_s)}]"
        else:
            # Keep MM:SS format for consistency with short segments
            return f"[{seconds_to_time(total_start_s)} - {seconds_to_time(total_end_s)}]"

    return re.sub(pattern, replace_match, cleaned_transcript)