"""
Planner Agent — Intent classification and routing.

Uses Gemini Flash for fast, low-cost intent detection.
Decides whether the query needs: RAG retrieval, web search, or direct answer.
"""

from loguru import logger
from app.agents.state import AgentState
from app.core.llm_router import get_planner_llm


CLASSIFICATION_PROMPT = """You are an intent classifier for an enterprise knowledge system.
Given the user's query, classify it into exactly ONE of these categories:

- "rag": The user is asking about internal company information, documents, policies, projects, or any domain-specific knowledge that would be in a corporate knowledge base.
- "web": The user is asking about real-time information, current events, weather, news, or publicly available data that requires an internet search.
- "direct": The user is asking a simple greeting, math, general knowledge, or conversational question that doesn't need any retrieval.

Respond with ONLY the category word, nothing else.

User query: {query}
Category:"""


def planner_node(state: AgentState) -> dict:
    """Classify user intent and route to appropriate downstream agent."""
    query = state.get("rewritten_query") or state["query"]
    llm = get_planner_llm()

    try:
        response = llm.invoke(CLASSIFICATION_PROMPT.format(query=query))
        intent = response.content.strip().lower().strip('"\'')

        # Validate intent
        if intent not in ("rag", "web", "direct"):
            logger.warning("Planner returned unknown intent '%s', defaulting to 'rag'", intent)
            intent = "rag"

        logger.info("Planner classified query as: %s", intent)
    except Exception as e:
        logger.error("Planner classification failed: %s — defaulting to 'rag'", e)
        intent = "rag"

    return {"intent": intent}
