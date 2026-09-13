import re
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

THRESHOLD = 0.33

# Compiled once at import rather than on every query.
TAG_PATTERN = re.compile(r"[A-Z]{1,3}-?\d+[A-Z]?")

# Opening the PersistentClient and resolving the collection cost ~2.5 s and was
# repeated on every single query. Both are stateless handles onto the local
# ./db store, so they are built once per process and reused. Still embedded,
# still no network beyond localhost:11434 for embeddings.
_COLLECTION = None


def get_collection():
    """Return the shared 'sops' collection, opening it on first use."""
    global _COLLECTION
    if _COLLECTION is None:
        client = chromadb.PersistentClient("./db")
        ef = OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name="nomic-embed-text"
        )
        _COLLECTION = client.get_collection(
            name="sops",
            embedding_function=ef
        )
    return _COLLECTION


def is_in_scope(q, keywords):
    """Helper to determine if query falls within allowed scope keywords."""
    q_lower = q.lower()
    return any(kw.lower() in q_lower for kw in keywords)

def search(q, role, top=6):
    # Filter by role categories — RBAC decision stays deterministic Python,
    # evaluated before any retrieval work is done.
    if "E-1042" in role:
        allowed_cats = ["pumps", "valves", "safety"]
    elif "T-201" in role:
        allowed_cats = ["pumps"]
    else:
        allowed_cats = []

    if not allowed_cats:
        return []

    collection = get_collection()

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
    q_tags = TAG_PATTERN.findall(q)
    
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
