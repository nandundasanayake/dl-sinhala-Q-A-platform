# utils/chunking.py
def split_into_chunks(text, target_words=200, overlap_words=50):
    """
    Implements an advanced Semantic/Token-optimized chunking strategy.
    Groups sentences until a target word count (~200-300 tokens) is reached,
    maintaining a semantic overlap to preserve context between chunks.
    """

    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        word_count = len(line.split())

        if current_word_count + word_count > target_words and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            
            # Semantic Overlap
            overlap_chunk = []
            overlap_count = 0
            for back_line in reversed(current_chunk):
                if overlap_count < overlap_words:
                    overlap_chunk.insert(0, back_line)
                    overlap_count += len(back_line.split())
                else:
                    break
            
            current_chunk = overlap_chunk
            current_word_count = overlap_count
        
        current_chunk.append(line)
        current_word_count += word_count
        i += 1
        
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        if chunk_text not in chunks:
            chunks.append(chunk_text)
            
    return chunks