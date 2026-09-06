import re
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

THRESHOLD = 0.33

def is_in_scope(q, keywords):
    """Helper to determine if query falls within allowed scope keywords."""
    q_lower = q.lower()
    return any(kw.lower() in q_lower for kw in keywords)

def search(q, role, top=6):
    client = chromadb.PersistentClient("./db")
    ef = OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text"
    )
    
    collection = client.get_collection(
        name="sops",
        embedding_function=ef
    )
    
    # Filter by role categories
    if "E-1042" in role:
        allowed_cats = ["pumps", "valves", "safety"]
    elif "T-201" in role:
        allowed_cats = ["pumps"]
    else:
        allowed_cats = []
        
    if not allowed_cats:
        return []
        
    results = collection.query(
        query_texts=[q],
        n_results=top,
        where={"cat": {"$in": allowed_cats}}
    )
    
    if not results["documents"] or not results["documents"][0]:
        return []
        
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]
    
    combined = list(zip(docs, metas, dists))
    
    # Extract tags from query using equipment regex
    tag_pattern = re.compile(r"[A-Z]{1,3}-?\d+[A-Z]?")
    q_tags = tag_pattern.findall(q)
    
    if q_tags:
        boosted = []
        normal = []
        for item in combined:
            doc = item[0]
            # Exact tag matching logic to boost chunks
            if any(tag in doc for tag in q_tags):
                boosted.append(item)
            else:
                normal.append(item)
        combined = boosted + normal
        
    return combined