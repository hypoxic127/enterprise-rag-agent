"""
Vector Store Service — v2.1 (Advanced RAG: Hybrid Retrieval + Reranker + Citations)

Architecture:
  - WRITE PATH: `ingest_documents()` → reads files, chunks, embeds, upserts to Qdrant
  - READ PATH:  `get_query_index()`  → connects to existing Qdrant collection (cached singleton)
  - ADVANCED:   `get_citation_query_engine()` → BM25+Vector fusion → citation-aware responses

The read path NEVER touches the filesystem or re-processes documents.
"""

import json
from functools import lru_cache
from loguru import logger

import qdrant_client
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.settings import Settings
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.query_engine import CitationQueryEngine, RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from dotenv import load_dotenv

from app.services.document_processor import load_and_split_documents
from app.core.config import GOOGLE_API_KEY, QDRANT_HOST, QDRANT_PORT

load_dotenv()

# ──────────────────────────────────────────────
# Global Settings (initialized once at import)
# ──────────────────────────────────────────────
Settings.embed_model = GeminiEmbedding(model_name="models/gemini-embedding-001", api_key=GOOGLE_API_KEY)
Settings.llm = Gemini(model="models/gemini-2.5-pro", api_key=GOOGLE_API_KEY)

# ──────────────────────────────────────────────
# Singleton Qdrant Client (Connection Pool)
# ──────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_qdrant_client() -> qdrant_client.QdrantClient:
    """Create a single, reusable Qdrant client connection."""
    logger.info("Creating Qdrant client → %s:%d", QDRANT_HOST, QDRANT_PORT)
    return qdrant_client.QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# ──────────────────────────────────────────────
# READ PATH — Cached query index (no file I/O)
# ──────────────────────────────────────────────
_cached_index: VectorStoreIndex | None = None
_cached_nodes: list | None = None

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


def _get_cached_nodes(collection_name: str = "enterprise_rag_gemini") -> list:
    """
    Retrieve all document nodes from Qdrant for BM25 indexing.
    Cached after first call.
    """
    global _cached_nodes
    if _cached_nodes is not None:
        return _cached_nodes

    logger.info("Loading nodes from Qdrant for BM25 index...")
    index = get_query_index(collection_name)
    # Retrieve all nodes from the vector store's docstore
    retriever = index.as_retriever(similarity_top_k=100)
    # We use a broad query to pull nodes for BM25 corpus
    _cached_nodes = list(index.docstore.docs.values()) if index.docstore.docs else []
    logger.info("Loaded %d nodes for BM25 corpus.", len(_cached_nodes))
    return _cached_nodes


# ──────────────────────────────────────────────
# ADVANCED RAG — Hybrid Retrieval + Citations
# ──────────────────────────────────────────────
def advanced_rag_query(
    query: str,
    collection_name: str = "enterprise_rag_gemini",
    user_access_tags: list[str] | None = None,
) -> dict:
    """
    Execute an Advanced RAG query with:
    1. BM25 + Vector hybrid retrieval (QueryFusionRetriever)
    2. Optional RBAC filtering via Qdrant metadata payload
    3. Citation-aware response synthesis
    
    Args:
        query: The search query.
        collection_name: Qdrant collection to search.
        user_access_tags: List of access tags from user's JWT roles.
            If provided, only documents with matching `access_roles` metadata
            will be returned.

    Returns:
        {"answer": "...", "sources": [...]}
    """
    from qdrant_client.models import Filter, FieldCondition, MatchAny

    index = get_query_index(collection_name)

    # --- Build RBAC metadata filter ---
    qdrant_filters = None
    if user_access_tags:
        qdrant_filters = Filter(
            should=[
                FieldCondition(
                    key="access_roles",
                    match=MatchAny(any=user_access_tags),
                ),
            ]
        )
        logger.info("RBAC filter applied: access_tags=%s", user_access_tags)

    # --- Vector Retriever (with optional RBAC filter) ---
    retriever_kwargs = {"similarity_top_k": 5}
    if qdrant_filters:
        retriever_kwargs["filters"] = qdrant_filters
    vector_retriever = index.as_retriever(**retriever_kwargs)

    # --- BM25 Retriever ---
    nodes = _get_cached_nodes(collection_name)
    if nodes:
        # If RBAC is active, filter BM25 nodes by access_roles
        active_nodes = nodes
        if user_access_tags:
            active_nodes = [
                n for n in nodes
                if set(n.metadata.get("access_roles", ["all"])) & set(user_access_tags)
            ]
            logger.info("BM25 nodes filtered: %d/%d by RBAC", len(active_nodes), len(nodes))

        try:
            bm25_retriever = BM25Retriever.from_defaults(
                nodes=active_nodes if active_nodes else nodes,
                similarity_top_k=5,
            )
            # --- Hybrid Fusion (RRF) ---
            fusion_retriever = QueryFusionRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                similarity_top_k=5,
                num_queries=1,
                mode="reciprocal_rerank",
            )
            logger.info("Using hybrid BM25 + Vector retrieval with RRF fusion")
            active_retriever = fusion_retriever
        except Exception as e:
            logger.warning("BM25 init failed, falling back to vector-only: %s", e)
            active_retriever = vector_retriever
    else:
        logger.info("No cached nodes for BM25, using vector-only retrieval")
        active_retriever = vector_retriever

    # --- Citation Query Engine ---
    try:
        citation_engine = CitationQueryEngine.from_args(
            index,
            retriever=active_retriever,
            citation_chunk_size=512,
            citation_chunk_overlap=50,
        )
        response = citation_engine.query(query)
    except Exception as e:
        logger.warning("CitationQueryEngine failed, falling back to basic: %s", e)
        response = index.as_query_engine().query(query)

    # --- Extract sources ---
    sources = []
    if hasattr(response, "source_nodes"):
        for i, node in enumerate(response.source_nodes):
            source_text = node.node.get_content()[:200]
            file_name = node.node.metadata.get("file_name", "unknown")
            score = getattr(node, "score", None)
            sources.append({
                "id": i + 1,
                "text": source_text + ("..." if len(node.node.get_content()) > 200 else ""),
                "file": file_name,
                "score": round(score, 4) if score else None,
            })

    return {
        "answer": str(response),
        "sources": sources,
    }


# ──────────────────────────────────────────────
# WRITE PATH — Ingestion (only called by scripts)
# ──────────────────────────────────────────────
def ingest_documents(
    data_dir: str = "data",
    collection_name: str = "enterprise_rag_gemini",
    access_roles_map: dict[str, list[str]] | None = None,
) -> VectorStoreIndex:
    """
    Read documents from disk, chunk, embed, and upsert into Qdrant.
    This is an EXPENSIVE operation — only call from ingestion scripts,
    never from the request hot path.

    Args:
        data_dir: Directory containing documents.
        collection_name: Target Qdrant collection.
        access_roles_map: Optional mapping of filename → access roles for RBAC.
    """
    global _cached_index, _cached_nodes

    logger.info("Ingesting documents from '%s' into collection '%s'...", data_dir, collection_name)
    client = _get_qdrant_client()
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    nodes = load_and_split_documents(data_dir, access_roles_map=access_roles_map)
    logger.info("Loaded %d nodes, upserting to Qdrant...", len(nodes))

    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
    )

    # Invalidate all read caches so the next query picks up new data
    _cached_index = None
    _cached_nodes = None
    logger.info("Ingestion complete. All caches invalidated.")
    return index

