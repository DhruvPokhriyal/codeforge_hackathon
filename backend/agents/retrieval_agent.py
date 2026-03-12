# backend/agents/retrieval_agent.py
# STEP 4 — RAG Retrieval (LlamaIndex + all-MiniLM-L6-v2 embeddings)
#
# Embeds the transcript and retrieves top-k relevant chunks from the offline
# PDF knowledge base. Flags vague queries when top_score < CONFIDENCE_THRESHOLD.
#
# Public interface:
#   build_index(pdf_dir: str) -> None
#     · Call once on application startup (registered in main.py startup event)
#
#   retrieve(query: str, top_k: int) -> dict
#     · Returns: {
#         "chunks":    list[{text, score, source, page}],
#         "is_vague":  bool,   # True when top_score < CONFIDENCE_THRESHOLD
#         "top_score": float
#       }

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from config import EMBED_MODEL, RAG_TOP_K, CONFIDENCE_THRESHOLD, PROTOCOLS_DIR

# Configure embedding model — LLM is managed separately via llama.cpp
Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
Settings.llm = None

_index = None


def build_index(pdf_dir: str = str(PROTOCOLS_DIR)) -> None:
    """Build (or rebuild) the vector index from all PDFs in pdf_dir."""
    global _index
    docs = SimpleDirectoryReader(pdf_dir).load_data()
    _index = VectorStoreIndex.from_documents(docs)


def retrieve(query: str, top_k: int = RAG_TOP_K) -> dict:
    """
    Embed query → semantic search → return top-k chunks with confidence flag.
    If no index is built (no PDFs loaded), returns empty chunks with is_vague=True
    so the pipeline degrades gracefully through the vagueness resolver.
    """
    if _index is None:
        return {"chunks": [], "is_vague": True, "top_score": 0.0}

    retriever = _index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)

    chunks = [
        {
            "text": n.node.get_content(),
            "score": n.score,
            "source": n.node.metadata.get("file_name", "unknown"),
            "page": n.node.metadata.get("page_label", "?"),
        }
        for n in nodes
    ]

    top_score = chunks[0]["score"] if chunks else 0.0
    is_vague = top_score < CONFIDENCE_THRESHOLD

    return {"chunks": chunks, "is_vague": is_vague, "top_score": top_score}
