"""
Researcher Agent — Executes retrieval (RAG + Web search).

Reuses the existing `advanced_rag_query()` from vector_store.py for local
knowledge base search, and Tavily for web search. This replaces the inline
`safe_local_search()` function from v2.1's chat.py.
"""

import traceback
from loguru import logger
from app.agents.state import AgentState
from app.services.vector_store import advanced_rag_query
from app.core.config import GOOGLE_API_KEY, TAVILY_API_KEY

_researcher_llm = None


def _get_researcher_llm():
    global _researcher_llm
    if _researcher_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _researcher_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.3,
        )
    return _researcher_llm


def _do_rag_search(query: str, access_tags: list[str] | None = None) -> dict:
    """Execute hybrid BM25+Vector retrieval with citations and optional RBAC filter."""
    try:
        result = advanced_rag_query(query, user_access_tags=access_tags)
        return {
            "raw_answer": result["answer"],
            "sources": result.get("sources", []),
        }
    except Exception as e:
        logger.error("RAG retrieval failed:\n%s", traceback.format_exc())
        return {
            "raw_answer": f"Retrieval error: {str(e)}",
            "sources": [],
        }


# Cached Tavily client
_tavily_tools = None


def _do_web_search(query: str) -> dict:
    """Execute web search via Tavily (cached client)."""
    global _tavily_tools
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set, cannot perform web search")
        return {"raw_answer": "Web search is not available.", "sources": []}

    try:
        if _tavily_tools is None:
            from llama_index.tools.tavily_research import TavilyToolSpec
            _tavily_tools = TavilyToolSpec(api_key=TAVILY_API_KEY).to_tool_list()

        for tool in _tavily_tools:
            if tool.metadata.name == "search":
                result = tool.call(query)
                return {"raw_answer": str(result), "sources": []}

        return {"raw_answer": "Web search tool not found.", "sources": []}
    except Exception as e:
        logger.error("Web search failed:\n%s", traceback.format_exc())
        return {"raw_answer": f"Web search error: {str(e)}", "sources": []}


def _do_direct_answer(query: str, chat_history: list, access_tags: list[str] | None = None) -> dict:
    """Answer directly without retrieval, using the LLM Router for model selection."""
    from app.core.llm_router import get_router, get_llm_for_config

    router = get_router()
    config = router.route(query=query, intent="direct", access_tags=access_tags)
    llm = get_llm_for_config(config)

    logger.info("Direct answer using %s/%s (%s)", config.provider, config.model, config.reason.value)

    try:
        messages = []
        for msg in chat_history[-10:]:
            role = "human" if str(msg.role) == "MessageRole.USER" else "ai"
            messages.append((role, msg.content))
        messages.append(("human", query))

        response = llm.invoke(messages)
        return {"raw_answer": response.content, "sources": []}
    except Exception as e:
        logger.error("Direct answer failed: %s", e)
        return {"raw_answer": f"Error generating response: {str(e)}", "sources": []}



def researcher_node(state: AgentState) -> dict:
    """Execute retrieval based on Planner's intent classification."""
    intent = state.get("intent", "rag")
    query = state.get("rewritten_query") or state.get("enriched_query", state["query"])
    chat_history = state.get("chat_history", [])
    access_tags = state.get("access_tags")

    logger.info("Researcher executing with intent='%s', query='%s'", intent, query[:80])

    if intent == "rag":
        result = _do_rag_search(query, access_tags=access_tags)
    elif intent == "web":
        result = _do_web_search(query)
    else:  # direct
        result = _do_direct_answer(query, chat_history, access_tags=access_tags)

    return result

