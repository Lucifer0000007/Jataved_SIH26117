import os
import re
import glob
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

def get_metadata(chunk, filename, category):
    # Extract the header line for the section metadata
    match = re.search(r"^(\d+\.\s+.*?)(?:\n|$)", chunk)
    section = match.group(1).strip() if match else "UNKNOWN"
    return {"file": filename, "cat": category, "section": section}

def load():
    os.makedirs("sops", exist_ok=True)
    
    client = chromadb.PersistentClient("./db")
    ef = OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text"
    )
    
    collection = client.get_or_create_collection(
        name="sops",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

    sop_files = glob.glob(os.path.join("sops", "*_SOP-*.txt"))
    
    total_chunks = 0
    for filepath in sop_files:
        filename = os.path.basename(filepath)
        category = filename.split('_')[0]
        
        with open(filepath, 'r', encoding='utf-8') as f:
            # Prepend newline to ensure first section matches regex
            txt = "\n" + f.read().strip()
            
        # Split on numbered sections and maintain the header line inside chunk
        raw_chunks = [c.strip() for c in re.split(r"\n(?=\d+\.)", txt) if c.strip()]
        
        chunks = []
        current_chunk = ""
        
        # Keep chunks 300-600 chars: merge tiny fragments
        for c in raw_chunks:
            if current_chunk:
                if len(current_chunk) < 300:
                    current_chunk += "\n\n" + c
                else:
                    chunks.append(current_chunk)
                    current_chunk = c
            else:
                current_chunk = c
                
        if current_chunk:
            if len(current_chunk) < 300 and chunks:
                chunks[-1] += "\n\n" + current_chunk
            else:
                chunks.append(current_chunk)
        
        ids = []
        documents = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            if len(chunk) < 40:
                continue
            chunk_id = f"{filename}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(get_metadata(chunk, filename, category))
            
        if ids:
            # Idempotent upsert
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            total_chunks += len(ids)

    print(f"Upserted {total_chunks} chunks successfully.")

if __name__ == "__main__":
    load()