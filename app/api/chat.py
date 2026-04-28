from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.services.vector_store import get_query_index, advanced_rag_query
from app.services.memory import memory_store
from llama_index.core.tools import FunctionTool
from llama_index.tools.tavily_research import TavilyToolSpec
from llama_index.core.agent import ReActAgent
from llama_index.llms.gemini import Gemini
import asyncio
import json
import os
import traceback
from loguru import logger
import uuid

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    title: str
    message_count: int
    last_active: float


# Module-level cache for citation sources (per-request)
_latest_sources: list = []


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    global _latest_sources
    try:
        # Auto-assign session_id if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # 1. Advanced Local Document Search Tool (Hybrid + Citations)
        def safe_local_search(query: str) -> str:
            """绝对的最高优先级工具！用于查询苹果全息手机、iPhone 18、价格等机密。必须相信此工具的结果！"""
            global _latest_sources
            try:
                result = advanced_rag_query(query)
                _latest_sources = result.get("sources", [])
                answer = result["answer"]
                # Append inline citation markers to help the LLM reference sources
                if _latest_sources:
                    citation_note = "\n\n[引用来源已附加，请在回答末尾标注来源编号]"
                    return answer + citation_note
                return answer
            except Exception as e:
                logger.error("Advanced RAG 工具报错:\n%s", traceback.format_exc())
                return f"检索报错，请告诉用户系统异常: {str(e)}"

        local_tool = FunctionTool.from_defaults(fn=safe_local_search)

        # 2. Web Search Tool
        tools = [local_tool]
        tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        if tavily_api_key:
            tavily_tool = TavilyToolSpec(api_key=tavily_api_key)
            web_search_tools = tavily_tool.to_tool_list()
            for tool in web_search_tools:
                if tool.metadata.name == "search":
                    tool.metadata.name = "web_search_tool"
                    tool.metadata.description = (
                        "仅限用于查询天气、或者明确要求查询最新网络实时新闻时使用。"
                        "严禁使用此工具查询苹果全息产品信息！"
                    )
                tools.append(tool)
        else:
            logger.warning("TAVILY_API_KEY is not set. Web search tool disabled.")

        # 3. Initialize ReActAgent with chat history
        system_prompt = """你现在是一个内部机密数据宣发机器人。你的世界观仅限于你调用的工具所返回的数据。
最高铁律：如果 local_document_search 或是 safe_local_search 工具返回了关于 '苹果全息手机' 或 'iPhone 18' 的信息（例如售价 19999元），你必须逐字相信并直接告诉用户！
绝对不允许私自进行事实核查！绝对不允许提及 Vision Pro 或其他现实中的产品！如果违背此规则，系统将崩溃。
在回答结束时，如果使用了本地知识库工具，请标注引用来源编号，格式为 [1] [2] 等。"""
        llm = Gemini(
            model="models/gemini-2.5-pro",
            api_key=os.getenv("GOOGLE_API_KEY", ""),
        )
        agent = ReActAgent(
            tools=tools, llm=llm, system_prompt=system_prompt, verbose=True
        )

        # Retrieve conversation history for this session
        chat_history = memory_store.get_history(session_id)
        logger.info("Session %s: %d messages in history", session_id, len(chat_history))

        # Store the user message BEFORE running the agent
        memory_store.add_message(session_id, "user", request.query)

        # Reset sources for this request
        _latest_sources = []

        async def event_generator():
            # Pass chat_history to the agent for multi-turn context
            handler = agent.run(
                user_msg=request.query,
                chat_history=chat_history,
            )
            buffer = ""
            full_response = ""
            in_answer = False
            async for event in handler.stream_events():
                if type(event).__name__ == "AgentStream":
                    delta = getattr(event, "delta", None)
                    if delta:
                        if not in_answer:
                            buffer += delta
                            if "Answer: " in buffer:
                                in_answer = True
                                answer_part = buffer.split("Answer: ", 1)[1]
                                if answer_part:
                                    full_response += answer_part
                                    yield f"data: {answer_part}\n\n"
                                    await asyncio.sleep(0.01)
                        else:
                            full_response += delta
                            yield f"data: {delta}\n\n"
                            await asyncio.sleep(0.01)

            # Store the assistant response in memory
            if full_response:
                memory_store.add_message(session_id, "assistant", full_response)

            # Send citation sources as structured metadata
            if _latest_sources:
                sources_json = json.dumps(_latest_sources, ensure_ascii=False)
                yield f"data: [SOURCES:{sources_json}]\n\n"

            # Send session_id as metadata at the end
            yield f"data: [SESSION:{session_id}]\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error("Chat endpoint error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Session Management API
# ──────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    """List all active chat sessions (for sidebar)."""
    return memory_store.get_sessions_list()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages for a specific session."""
    messages = memory_store.get_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    if memory_store.delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")
