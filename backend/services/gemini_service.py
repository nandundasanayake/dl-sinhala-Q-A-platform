# services/gemini_service.py
import os
from google import genai
from config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise ValueError("CRITICAL ERROR: GEMINI_API_KEY is missing in environment variables.")

client = genai.Client(api_key=GEMINI_API_KEY)

# Load prompts from files
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

def get_transcription_prompt():
    with open(os.path.join(_PROMPTS_DIR, 'transcription_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()

def get_chat_system_prompt():
    with open(os.path.join(_PROMPTS_DIR, 'chat_system_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()

def get_rewrite_prompt_template():
    with open(os.path.join(_PROMPTS_DIR, 'rewrite_prompt.txt'), 'r', encoding='utf-8') as f:
        return f.read()