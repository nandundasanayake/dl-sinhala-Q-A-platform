from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Listing all available models...")
try:
    models = client.models.list()
    embed_models = [m.name for m in models if 'embed' in m.name.lower()]
    print(f"\nEmbedding models: {embed_models}")
    
    all_models = [m.name for m in models]
    print(f"\nAll models ({len(all_models)}):")
    for model in all_models[:20]:  # Show first 20
        print(f"  - {model}")
except Exception as e:
    print(f"Error: {e}")
