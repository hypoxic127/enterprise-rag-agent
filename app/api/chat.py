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
import io
import base64
import traceback
from loguru import logger
import uuid

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


# Module-level cache for citation sources (per-request)
_latest_sources: list = []


def _analyze_image_with_vision(image_base64: str) -> str:
    """Use Gemini Vision to extract content from an uploaded image."""
    import google.generativeai as genai
    import PIL.Image

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))
    vision_model = genai.GenerativeModel("gemini-2.5-pro")

    # Handle data URL format: "data:image/png;base64,..."
    b64_data = image_base64
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    image_bytes = base64.b64decode(b64_data)
    img = PIL.Image.open(io.BytesIO(image_bytes))

    vision_response = vision_model.generate_content([
        "请详细描述这张图片的内容，提取其中所有文字、表格、数据和关键信息。如果图片中有代码，请完整提取：",
        img,
    ])
    return vision_response.text


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    global _latest_sources
    try:
        # Auto-assign session_id if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # --- Multimodal: analyze uploaded image ---
        image_context = ""
        if request.image_base64:
            try:
                image_description = _analyze_image_with_vision(request.image_base64)
                image_context = f"\n\n[用户上传了一张图片，以下是图片内容的AI分析结果]\n{image_description}\n"
                logger.info("Vision analysis completed for uploaded image")
            except Exception as e:
                logger.error("Vision analysis failed: %s", traceback.format_exc())
                image_context = "\n\n[图片分析失败，请基于文字内容回答]\n"

        # 1. Advanced Local Document Search Tool (Hybrid + Citations)
        def safe_local_search(query: str) -> str:
            """
            企业内部知识库的高级检索工具。
            这是获取内部文档、企业规章、项目资料、专有数据和机密信息的唯一且最高优先级的来源。
            务必优先信任并使用此工具返回的结果。
            """
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
                        "互联网实时搜索引擎工具。"
                        "仅当用户明确要求检索外部网络新闻、公共数据，或者当内部知识库确实无法回答时，才可以使用此工具。"
                    )
                tools.append(tool)
        else:
            logger.warning("TAVILY_API_KEY is not set. Web search tool disabled.")

        # 3. Initialize ReActAgent with chat history
        system_prompt = """你现在是 Enterprise RAG Agent，一个高度专业、严谨的企业级知识问答系统。
最高原则：你的首要任务是基于企业内部知识库为用户提供准确、详实的解答。请绝对优先信任并依赖本地检索工具（safe_local_search）返回的数据。
1. 如果本地知识库中包含了相关信息，请严格基于检索到的内容进行回答，绝不能凭借自身预训练数据捏造、脑补或擅自篡改企业内部事实。
2. 只有当用户明确要求查询外部实时信息，或者本地知识库确实没有任何相关资料时，才可使用外部网络搜索工具。
3. 在回答结束时，如果使用了本地知识库工具的数据，请务必在相应事实后标注准确的引用来源编号，格式为 [1] [2] 等。
请用专业、客观、礼貌的语气与用户交流。"""
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

        # Build the enriched query (original + image context if any)
        enriched_query = request.query + image_context

        # Store the user message BEFORE running the agent
        memory_store.add_message(
            session_id, "user", request.query,
            image_url=request.image_base64,
        )

        # Reset sources for this request
        _latest_sources = []

        async def event_generator():
            # Pass chat_history to the agent for multi-turn context
            handler = agent.run(
                user_msg=enriched_query,
                chat_history=chat_history,
            )
            buffer = ""
            full_response = ""
            # State machine: BUFFERING → STREAMING → DONE
            state = "BUFFERING"  # Collecting ReAct reasoning, not yet forwarding

            async for event in handler.stream_events():
                if type(event).__name__ == "AgentStream":
                    delta = getattr(event, "delta", None)
                    if not delta:
                        continue

                    if state == "BUFFERING":
                        buffer += delta

                        # Case 1: Found "Answer:" marker → switch to STREAMING
                        for marker in ("Answer: ", "Answer:"):
                            if marker in buffer:
                                state = "STREAMING"
                                answer_part = buffer.split(marker, 1)[1]
                                if answer_part:
                                    full_response += answer_part
                                    yield f"data: {answer_part}\n\n"
                                    await asyncio.sleep(0.01)
                                break

                        # Case 2: No "Thought:" seen after 300 chars → direct answer
                        if state == "BUFFERING" and len(buffer) > 300 and "Thought:" not in buffer:
                            state = "STREAMING"
                            full_response += buffer
                            yield f"data: {buffer}\n\n"
                            await asyncio.sleep(0.01)

                    elif state == "STREAMING":
                        full_response += delta
                        yield f"data: {delta}\n\n"
                        await asyncio.sleep(0.01)

            # Post-stream: handle buffered content that was never flushed
            if state == "BUFFERING" and buffer:
                # Extract answer from "Thought: ... Answer: ..." block
                for marker in ("Answer: ", "Answer:"):
                    if marker in buffer:
                        answer = buffer.split(marker, 1)[1].strip()
                        full_response = answer
                        yield f"data: {answer}\n\n"
                        break
                else:
                    # No marker found — flush entire buffer as answer
                    full_response = buffer
                    yield f"data: {buffer}\n\n"

            # Store the assistant response in memory
            if full_response:
                memory_store.add_message(session_id, "assistant", full_response, sources=_latest_sources)

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
