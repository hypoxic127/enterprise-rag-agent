"""
Agent State — Shared state object flowing through the LangGraph pipeline.

All agents read from and write to this TypedDict. It replaces the
module-level global variables (e.g., _latest_sources) from v2.1.
"""

from typing import TypedDict, Optional
from llama_index.core.llms import ChatMessage


class AgentState(TypedDict, total=False):
    # ── Input ──
    query: str                          # Original user query
    enriched_query: str                 # Query + image context (if any)
    session_id: str                     # Chat session ID
    chat_history: list[ChatMessage]     # Multi-turn history
    image_context: str                  # Vision analysis text

    # ── RBAC (v3.0) ──
    user_roles: list[str]               # User roles from JWT (e.g., ["engineer"])
    access_tags: list[str]              # Expanded access tags for Qdrant filter

    # ── Planner output ──
    intent: str                         # "rag" | "web" | "direct"

    # ── Researcher output ──
    raw_answer: str                     # Answer from retrieval or web
    sources: list[dict]                 # Citation sources

    # ── Reviewer output ──
    review_status: str                  # "APPROVE" | "REJECT"
    retry_count: int                    # Number of CRAG retries (max 3)
    rewritten_query: Optional[str]      # Rewritten query after rejection

    # ── Final output ──
    final_answer: str                   # Polished answer for the user
    llm_route_info: dict                # LLM Router decision (provider, model, reason)

