"""
Reviewer Agent — Self-RAG quality grading and corrective retrieval.

Implements Corrective RAG (CRAG) pattern:
1. DocumentGrader: LLM-as-Judge to score retrieval relevance
2. QueryRewriter: Transforms failed queries for retry
3. Decision: APPROVE (pass to output) or REJECT (loop back to Researcher)
"""

import json
from loguru import logger
from app.agents.state import AgentState
from app.core.llm_router import get_reviewer_llm

MAX_RETRIES = 3


# ──────────────────────────────────────────────
# Document Grader — LLM-as-Judge
# ──────────────────────────────────────────────

GRADING_PROMPT = """You are a strict relevance grader for an enterprise knowledge system.
Given a user query and a retrieved answer, determine if the answer contains
information that is genuinely relevant and useful for answering the query.

Consider:
- Does the answer address the user's actual question?
- Is the information specific enough to be useful?
- Would this answer satisfy the user?

Respond with ONLY valid JSON (no markdown, no code fences):
{{"relevant": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}

User query: {query}
Retrieved answer (first 800 chars): {answer}

JSON:"""


def _grade_relevance(query: str, answer: str) -> dict:
    """Grade the relevance of a retrieved answer to the query."""
    llm = get_reviewer_llm()
    try:
        response = llm.invoke(GRADING_PROMPT.format(
            query=query,
            answer=answer[:800],
        ))
        text = response.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        logger.info(
            "Grading result: relevant=%s, confidence=%.2f, reason=%s",
            result.get("relevant"), result.get("confidence", 0), result.get("reason", "")
        )
        return result
    except Exception as e:
        logger.warning("Grading failed (%s), defaulting to APPROVE", e)
        return {"relevant": True, "confidence": 0.5, "reason": "grading_error_fallback"}


# ──────────────────────────────────────────────
# Query Rewriter — Transform failed queries
# ──────────────────────────────────────────────

REWRITE_PROMPT = """You are an expert at reformulating search queries for an enterprise knowledge base.
The original query failed to retrieve relevant documents.

Rewrite the query to:
1. Use alternative terminology or synonyms
2. Be more specific about what information is needed
3. Break compound questions into the most important sub-question

Original query: {query}
Reason for failure: {reason}

Respond with ONLY the rewritten query, nothing else.

Rewritten query:"""


def _rewrite_query(query: str, reason: str) -> str:
    """Rewrite a query that failed relevance grading."""
    llm = get_reviewer_llm()
    try:
        response = llm.invoke(REWRITE_PROMPT.format(query=query, reason=reason))
        rewritten = response.content.strip()
        logger.info("Query rewritten: '%s' → '%s'", query[:50], rewritten[:50])
        return rewritten
    except Exception as e:
        logger.warning("Query rewrite failed (%s), returning original", e)
        return query


# ──────────────────────────────────────────────
# Reviewer Node — Main entry point
# ──────────────────────────────────────────────

def reviewer_node(state: AgentState) -> dict:
    """
    Grade retrieval quality and decide APPROVE or REJECT.

    For 'direct' intent, always approve (no retrieval to grade).
    For 'web' intent, always approve (web results are best-effort).
    For 'rag' intent, run the DocumentGrader.
    """
    intent = state.get("intent", "rag")
    retry_count = state.get("retry_count", 0)

    # Skip grading for non-RAG intents
    if intent != "rag":
        logger.info("Reviewer: skipping grading for intent='%s', auto-APPROVE", intent)
        return {
            "review_status": "APPROVE",
            "final_answer": state.get("raw_answer", ""),
            "retry_count": retry_count,
        }

    # Max retries reached — force approve with what we have
    if retry_count >= MAX_RETRIES:
        logger.warning("Reviewer: max retries (%d) reached, force APPROVE", MAX_RETRIES)
        return {
            "review_status": "APPROVE",
            "final_answer": state.get("raw_answer", ""),
            "retry_count": retry_count,
        }

    # Grade the retrieval quality
    query = state.get("rewritten_query") or state["query"]
    answer = state.get("raw_answer", "")

    grade = _grade_relevance(query, answer)

    if grade.get("relevant", True) and grade.get("confidence", 0) >= 0.6:
        # APPROVE — answer is good
        logger.info("Reviewer: APPROVE (confidence=%.2f)", grade.get("confidence", 0))
        return {
            "review_status": "APPROVE",
            "final_answer": answer,
            "retry_count": retry_count,
        }
    else:
        # REJECT — rewrite query and retry
        reason = grade.get("reason", "low relevance")
        rewritten = _rewrite_query(query, reason)
        logger.info(
            "Reviewer: REJECT (confidence=%.2f, retry=%d/%d)",
            grade.get("confidence", 0), retry_count + 1, MAX_RETRIES,
        )
        return {
            "review_status": "REJECT",
            "rewritten_query": rewritten,
            "retry_count": retry_count + 1,
        }
