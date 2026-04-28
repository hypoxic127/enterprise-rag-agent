"""
Vector Store Service — v2.0 (Cached Index + Connection Pool)

Architecture:
  - WRITE PATH: `ingest_documents()` → reads files, chunks, embeds, upserts to Qdrant
  - READ PATH:  `get_query_index()`  → connects to existing Qdrant collection (cached singleton)

The read path NEVER touches the filesystem or re-processes documents.
"""

import logging
from functools import lru_cache

import qdrant_client
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.settings import Settings
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from dotenv import load_dotenv
import os

from app.services.document_processor import load_and_split_documents

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Global Settings (initialized once at import)
# ──────────────────────────────────────────────
_api_key = os.getenv("GOOGLE_API_KEY", "")
Settings.embed_model = GeminiEmbedding(model_name="models/gemini-embedding-001", api_key=_api_key)
Settings.llm = Gemini(model="models/gemini-2.5-pro", api_key=_api_key)

# ──────────────────────────────────────────────
# Singleton Qdrant Client (Connection Pool)
# ──────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_qdrant_client() -> qdrant_client.QdrantClient:
    """Create a single, reusable Qdrant client connection."""
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    logger.info("Creating Qdrant client → %s:%d", host, port)
    return qdrant_client.QdrantClient(host=host, port=port)


# ──────────────────────────────────────────────
# READ PATH — Cached query index (no file I/O)
# ──────────────────────────────────────────────
_cached_index: VectorStoreIndex | None = None

def get_query_index(collection_name: str = "enterprise_rag_gemini") -> VectorStoreIndex:
    """
    Return a cached VectorStoreIndex that connects to an EXISTING Qdrant collection.
    Does NOT read files or re-process documents. Safe to call on every request.
    """
    global _cached_index
    if _cached_index is not None:
        return _cached_index

    logger.info("Building query index from existing collection '%s'...", collection_name)
    client = _get_qdrant_client()
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    _cached_index = VectorStoreIndex.from_vector_store(vector_store)
    logger.info("Query index cached successfully.")
    return _cached_index


# ──────────────────────────────────────────────
# WRITE PATH — Ingestion (only called by scripts)
# ──────────────────────────────────────────────
def ingest_documents(
    data_dir: str = "data",
    collection_name: str = "enterprise_rag_gemini",
) -> VectorStoreIndex:
    """
    Read documents from disk, chunk, embed, and upsert into Qdrant.
    This is an EXPENSIVE operation — only call from ingestion scripts,
    never from the request hot path.
    """
    global _cached_index

    logger.info("Ingesting documents from '%s' into collection '%s'...", data_dir, collection_name)
    client = _get_qdrant_client()
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    nodes = load_and_split_documents(data_dir)
    logger.info("Loaded %d nodes, upserting to Qdrant...", len(nodes))

    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
    )

    # Invalidate the read cache so the next query picks up new data
    _cached_index = None
    logger.info("Ingestion complete. Read cache invalidated.")
    return index


# ──────────────────────────────────────────────
# Backwards-compat alias (deprecated, will remove in v2.1)
# ──────────────────────────────────────────────
def get_vector_index(collection_name: str = "enterprise_rag_gemini", data_dir: str = "data"):
    """DEPRECATED: Use get_query_index() for reads or ingest_documents() for writes."""
    logger.warning("get_vector_index() is deprecated. Use get_query_index() or ingest_documents().")
    return ingest_documents(data_dir=data_dir, collection_name=collection_name)
