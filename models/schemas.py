# models/schemas.py
from pydantic import BaseModel
from typing import List, Optional

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    video_id: str
    question: str
    chat_history: List[ChatMessage] = []

class ProcessVideoRequest(BaseModel):
    video_id: str
    original_title: Optional[str] = None
    folder_path: Optional[str] = ""