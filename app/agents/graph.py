"""
Agent Graph — LangGraph StateGraph builder for multi-agent orchestration.

Builds a directed graph:
  Planner → Researcher → Reviewer → Synthesizer → END
                            ↑ REJECT ↓
                            ← ← ← ←

Replaces the single ReActAgent from v2.1.
"""

import time
from loguru import logger
from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.planner import planner_node
from app.agents.researcher import researcher_node
from app.agents.reviewer import reviewer_node
from app.agents.synthesizer import synthesizer_node


# ──────────────────────────────────────────────
# Instrumented Node Wrappers
# ──────────────────────────────────────────────

def _timed_node(name: str, func):
    """Wrap an agent node with timing instrumentation."""
    def wrapper(state: AgentState) -> dict:
        start = time.perf_counter()
        logger.info("▶ [%s] node started", name)
        try:
            result = func(state)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "✓ [%s] node completed in %.0fms | keys=%s",
                name, elapsed, list(result.keys()),
            )
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error("✗ [%s] node failed after %.0fms: %s", name, elapsed, e)
            raise
    return wrapper


def _route_after_review(state: AgentState) -> str:
    """Conditional edge: loop back to Researcher on REJECT, else to Synthesizer."""
    if state.get("review_status") == "REJECT":
        logger.info("⟲ Graph routing: REJECT → back to researcher (retry %d)", state.get("retry_count", 0))
        return "researcher"
    return "synthesizer"


def create_agent_graph() -> StateGraph:
    """
    Build and compile the multi-agent LangGraph.

    Flow:
        planner → researcher → reviewer
                                  ↓ APPROVE → synthesizer → END
                                  ↓ REJECT  → researcher (loop)

    All nodes are wrapped with timing instrumentation for observability.
    """
    workflow = StateGraph(AgentState)

    # Add instrumented nodes
    workflow.add_node("planner", _timed_node("Planner", planner_node))
    workflow.add_node("researcher", _timed_node("Researcher", researcher_node))
    workflow.add_node("reviewer", _timed_node("Reviewer", reviewer_node))
    workflow.add_node("synthesizer", _timed_node("Synthesizer", synthesizer_node))

    # Set entry point
    workflow.set_entry_point("planner")

    # Define edges
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "reviewer")

    # Conditional edge: Reviewer decides loop or synthesize
    workflow.add_conditional_edges("reviewer", _route_after_review)

    # Synthesizer → END
    workflow.add_edge("synthesizer", END)

    graph = workflow.compile()
    logger.info("Multi-agent graph compiled: planner → researcher → reviewer → synthesizer (instrumented)")
    return graph
