# services/gemini_service.py
import os
from google import genai
from config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in environment variables.")

from google.genai import types

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'timeout': 10000} # 10s timeout to prevent API hangs
)

_embedding_cache = {}

def get_query_embedding(text: str):
    """Generates query embedding using text-embedding-004 with in-memory caching for speed."""
    if text in _embedding_cache:
        print(f"   [FAST] Returning embedding from RAM cache")
        return _embedding_cache[text]
    
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768)
    )
    vector = result.embeddings[0].values
    _embedding_cache[text] = vector
    return vector

# Load prompts from files
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

def get_transcription_prompt():
    with open(os.path.join(_PROMPTS_DIR, 'transcription_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()

def get_voice_transcription_prompt():
    with open(os.path.join(_PROMPTS_DIR, 'voice_transcription_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()

def get_chat_system_prompt():
    with open(os.path.join(_PROMPTS_DIR, 'chat_system_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()

def get_rewrite_prompt_template():
    with open(os.path.join(_PROMPTS_DIR, 'rewrite_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()