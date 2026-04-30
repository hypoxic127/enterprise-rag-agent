"""
Chat API — v3.0 (Multi-Agent + Self-RAG)

Replaces the single ReActAgent with a LangGraph multi-agent pipeline:
  Planner → Researcher → Reviewer (with CRAG retry loop)

SSE streaming format is backward-compatible with v2.1 frontend.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.services.memory import memory_store
from app.agents.graph import create_agent_graph
from app.core.auth import get_current_user, UserContext
from fastapi import Depends
import asyncio
import json
import io
import base64
import traceback
from loguru import logger
import uuid
import time as _time

from app.core.config import GOOGLE_API_KEY

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    image_base64: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    title: str
    message_count: int
    last_active: float


# ──────────────────────────────────────────────
# Multimodal Vision Analysis
# ──────────────────────────────────────────────

def _analyze_image_with_vision(image_base64: str) -> str:
    """Use Gemini Vision to extract content from an uploaded image."""
    import google.generativeai as genai
    import PIL.Image

    genai.configure(api_key=GOOGLE_API_KEY)
    vision_model = genai.GenerativeModel("gemini-2.5-pro")

    b64_data = image_base64
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    image_bytes = base64.b64decode(b64_data)
    img = PIL.Image.open(io.BytesIO(image_bytes))

    vision_response = vision_model.generate_content([
        "Describe this image in detail. Extract all text, tables, data, and key information. If the image contains code, extract it completely:",
        img,
    ])
    return vision_response.text


# ──────────────────────────────────────────────
# Singleton Agent Graph
# ──────────────────────────────────────────────
_agent_graph = None


def _get_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


# ──────────────────────────────────────────────
# Chat Endpoint
# ──────────────────────────────────────────────

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, user: UserContext = Depends(get_current_user)):
    try:
        session_id = request.session_id or str(uuid.uuid4())

        # --- Multimodal: analyze uploaded image ---
        image_context = ""
        if request.image_base64:
            try:
                image_description = _analyze_image_with_vision(request.image_base64)
                image_context = f"\n\n[The user uploaded an image. Below is the AI analysis of its content]\n{image_description}\n"
                logger.info("Vision analysis completed for uploaded image")
            except Exception as e:
                logger.error("Vision analysis failed: %s", traceback.format_exc())
                image_context = "\n\n[Image analysis failed. Please respond based on the text content only]\n"

        # Build enriched query
        enriched_query = request.query + image_context

        # Retrieve conversation history
        chat_history = memory_store.get_history(session_id)
        logger.info("Session %s: %d messages in history", session_id, len(chat_history))

        # Store user message BEFORE running the agent
        memory_store.add_message(
            session_id, "user", request.query,
            image_url=request.image_base64,
        )

        # Build initial state for the graph (with RBAC context)
        initial_state = {
            "query": request.query,
            "enriched_query": enriched_query,
            "session_id": session_id,
            "chat_history": chat_history,
            "image_context": image_context,
            "user_roles": user.roles,
            "access_tags": user.access_tags,
            "sources": [],
            "retry_count": 0,
        }
        logger.info("User %s (roles=%s) querying: %s", user.user_id, user.roles, request.query[:60])

        async def event_generator():
            graph = _get_graph()
            final_answer = ""
            sources = []

            try:
                # Run the graph synchronously (agents use sync LLM calls)
                graph_start = _time.perf_counter()
                result = await asyncio.to_thread(graph.invoke, initial_state)
                graph_elapsed = (_time.perf_counter() - graph_start) * 1000

                final_answer = result.get("final_answer", "")
                sources = result.get("sources", [])
                route_info = result.get("llm_route_info", {})

                logger.info(
                    "Pipeline completed in %.0fms | intent=%s | review=%s | answer_len=%d | route=%s",
                    graph_elapsed,
                    result.get("intent", "?"),
                    result.get("review_status", "?"),
                    len(final_answer),
                    route_info.get("model", "unknown"),
                )

                # Stream the answer in small chunks for typewriter effect
                if final_answer:
                    CHUNK_SIZE = 5
                    for i in range(0, len(final_answer), CHUNK_SIZE):
                        chunk = final_answer[i:i+CHUNK_SIZE]
                        yield f"data: {chunk}\n\n"
                        await asyncio.sleep(0.03)

            except Exception as e:
                logger.error("Agent graph error:\n%s", traceback.format_exc())
                error_msg = "Sorry, an error occurred while processing your request."
                final_answer = error_msg
                yield f"data: {error_msg}\n\n"

            # Store assistant response
            if final_answer:
                memory_store.add_message(
                    session_id, "assistant", final_answer, sources=sources
                )

            # Send citation sources
            if sources:
                sources_json = json.dumps(sources, ensure_ascii=False)
                yield f"data: [SOURCES:{sources_json}]\n\n"

            # Send session_id metadata
            yield f"data: [SESSION:{session_id}]\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error("Chat endpoint error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Session Management API (unchanged from v2.1)
# ──────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(user: UserContext = Depends(get_current_user)):
    """List all active chat sessions (for sidebar). Requires authentication."""
    return memory_store.get_sessions_list()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user: UserContext = Depends(get_current_user)):
    """Get all messages for a specific session. Requires authentication."""
    messages = memory_store.get_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: UserContext = Depends(get_current_user)):
    """Delete a chat session. Requires authentication."""
    if memory_store.delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")
