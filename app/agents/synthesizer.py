"""
Synthesizer Agent — Polishes raw answers into final responses with citations.

Replaces the direct raw_answer → final_answer passthrough.
Uses the Hybrid LLM Router to select the optimal model for synthesis.
"""


from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI
from app.agents.state import AgentState
from app.core.llm_router import get_router, get_llm_for_config

SYNTHESIS_PROMPT = """You are a professional enterprise AI assistant.
Your job is to take a raw answer and polish it into a clear, well-structured response.

Rules:
1. Keep the factual content intact — do NOT add information not present in the raw answer.
2. Use Markdown formatting: use **bold** for emphasis, use bullet points (- or *) for lists.
3. Do NOT start with headings (### or ##). Start your response directly with content.
4. Do NOT use horizontal rules (*** or ---) anywhere in the response.
5. Do NOT include any prefix like "Polished response:" or "Here is the polished response".
6. If sources are provided, naturally reference them inline.
7. Be concise but thorough. Remove redundancy.
8. Use a professional, helpful tone.
9. If the raw answer contains an error message, acknowledge it gracefully.

User's original query: {query}

Raw answer to polish:
{raw_answer}

Respond directly with the polished content:"""


def _clean_synthesis_output(text: str) -> str:
    """Remove residual markdown artifacts that LLMs sometimes produce."""
    import re
    # Remove leading headings (### Title\n\n)
    text = re.sub(r'^\s*(#{1,4})\s+.*?\n+', '', text)
    # Remove horizontal rules
    text = re.sub(r'\n\s*[\*\-]{3,}\s*\n', '\n\n', text)
    # Remove "Polished response:" prefix if LLM added it
    text = re.sub(r'^\s*(Polished response|Here is):?\s*\n*', '', text, flags=re.IGNORECASE)
    # Collapse excessive blank lines (3+ newlines -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def synthesizer_node(state: AgentState) -> dict:
    """
    Polish the raw answer into a final response.

    For short/simple answers, passes through directly.
    For substantive answers, uses LLM to polish with formatting and citations.
    """
    raw_answer = state.get("raw_answer", "")
    query = state.get("rewritten_query") or state.get("enriched_query", state["query"])
    access_tags = state.get("access_tags")

    # Short answers don't need synthesis
    if len(raw_answer) < 100 or raw_answer.startswith("Error") or raw_answer.startswith("Retrieval error"):
        logger.info("Synthesizer: short/error answer, passing through directly")
        return {
            "final_answer": raw_answer,
            "llm_route_info": {"provider": "passthrough", "model": "none", "reason": "short_answer"},
        }

    # Route to the optimal LLM
    router = get_router()
    intent = state.get("intent", "rag")
    config = router.route(query=query, intent=intent, access_tags=access_tags)

    try:
        llm = get_llm_for_config(config)
        response = llm.invoke(SYNTHESIS_PROMPT.format(
            query=query,
            raw_answer=raw_answer[:2000],
        ))
        polished = _clean_synthesis_output(response.content)
        logger.info("Synthesizer: polished answer using %s/%s (%s)",
                     config.provider, config.model, config.reason.value)

        return {
            "final_answer": polished,
            "llm_route_info": config.to_dict(),
        }
    except Exception as e:
        logger.warning("Synthesizer failed (%s), using raw answer", e)
        return {
            "final_answer": raw_answer,
            "llm_route_info": {"provider": "fallback", "model": "none", "reason": str(e)},
        }
