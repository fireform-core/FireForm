import json
import logging
import os
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

logger = logging.getLogger("fireform_rag")
logger.setLevel(logging.INFO)

# Setup the specific local Ollama embeddings configured for privacy
# Data never leaves local Docker net
ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
embedding_function = OllamaEmbeddingFunction(
    url=f"{ollama_host}/api/embeddings",
    model_name="nomic-embed-text"
)

# Chroma client (Ephemeral/In-Memory for demonstration, but PersistentClient in Prod)
# We use PersistentClient pointing to /app/data configured in docker-compose
CHROMA_DATA_DIR = os.environ.get("CHROMA_DATA_DIR", "/app/data/chroma")
os.makedirs(CHROMA_DATA_DIR, exist_ok=True)

try:
    chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_DIR)
    
    # Initialize Collection
    collection = chroma_client.get_or_create_collection(
        name="few_shot_examples",
        embedding_function=embedding_function
    )
except Exception as e:
    logger.error("Failed to initialize ChromaDB: %s", str(e))
    # Fallback to ephemeral or None if not available during bootstrap
    chroma_client = chromadb.Client()
    collection = chroma_client.create_collection("few_shot_examples", embedding_function=embedding_function)

def populate_examples(json_path: str = "data/examples.json"):
    """
    Load examples from JSON and embed them.
    Assumes array of {"narrative": "...", "report": {...}}
    """
    if not os.path.exists(json_path):
        logger.warning("No examples file found at %s. Few-shot RAG will be empty.", json_path)
        return

    with open(json_path, "r", encoding="utf-8") as f:
        examples = json.load(f)

    if not isinstance(examples, list) or len(examples) == 0:
        return

    ids = []
    documents = []
    metadatas = []

    for idx, ex in enumerate(examples):
        ids.append(f"example_{idx}")
        documents.append(ex.get("narrative", ""))
        metadatas.append({"report": json.dumps(ex.get("report", {}))})

    # Add to Chroma collection
    # Skip if they already exist
    existing = collection.get(ids=ids)
    if not existing or len(existing.get('ids', [])) < len(ids):
        collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info("Upserted %d training examples to Chroma vector store.", len(ids))

def get_few_shot_prompt(query: str, top_k: int = 3) -> str:
    """
    Retrieve top-k similar examples and format them into a context prompt.
    """
    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k
        )
    except Exception as e:
        logger.error("Chroma query failed: %s", str(e))
        return ""

    if not results or not results.get("documents") or len(results["documents"][0]) == 0:
        return ""

    context_str = "Here are a few similar incident examples for reference:\n\n"
    
    for i in range(len(results["documents"][0])):
        doc = results["documents"][0][i]
        meta = results["metadatas"][0][i]
        report_json = meta.get("report", "{}")
        
        context_str += f"---\nNarrative: {doc}\nExtraction Output expected:\n{report_json}\n\n"
        
    return context_str
