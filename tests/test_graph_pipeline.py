"""
Graph Pipeline E2E Tests — Full multi-agent orchestration validation.

Tests the complete LangGraph pipeline with mocked LLMs.
Uses sys.modules mocking to avoid importing heavy dependencies
(qdrant, llama_index) that may not be in the test environment.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

os.environ["AUTH_ENABLED"] = "false"
os.environ["GOOGLE_API_KEY"] = "test-api-key"

from tests.conftest import MockLLMResponse


def _mock_heavy_deps():
    """Create mock modules for heavy production dependencies."""
    mocks = {}
    for mod_name in [
        "app.services.vector_store",
        "llama_index.vector_stores.qdrant",
        "llama_index.retrievers.bm25",
    ]:
        if mod_name not in sys.modules:
            mocks[mod_name] = MagicMock()
    return mocks


class TestGraphCompilation:
    """Test that the graph compiles and has the correct structure."""

    def test_graph_compiles_without_error(self):
        """create_agent_graph() should return a compiled graph."""
        mock_vs = MagicMock()
        mock_vs.advanced_rag_query = MagicMock(return_value={"answer": "test", "sources": []})

        with patch.dict(sys.modules, _mock_heavy_deps()):
            # Reload to pick up mocked modules
            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import create_agent_graph
            graph = create_agent_graph()
            assert graph is not None

    def test_graph_has_all_nodes(self):
        """Graph should contain planner, researcher, reviewer, synthesizer nodes."""
        with patch.dict(sys.modules, _mock_heavy_deps()):
            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import create_agent_graph
            graph = create_agent_graph()
            node_names = list(graph.nodes.keys())
            assert "planner" in node_names
            assert "researcher" in node_names
            assert "reviewer" in node_names
            assert "synthesizer" in node_names


class TestGraphRoutingLogic:
    """Test the conditional routing after reviewer."""

    def test_approve_routes_to_synthesizer(self):
        """APPROVE status should route to synthesizer."""
        with patch.dict(sys.modules, _mock_heavy_deps()):
            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import _route_after_review
            state = {"review_status": "APPROVE", "retry_count": 0}
            assert _route_after_review(state) == "synthesizer"

    def test_reject_routes_to_researcher(self):
        """REJECT status should loop back to researcher."""
        with patch.dict(sys.modules, _mock_heavy_deps()):
            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import _route_after_review
            state = {"review_status": "REJECT", "retry_count": 1}
            assert _route_after_review(state) == "researcher"


class TestFullPipeline:
    """End-to-end tests with all LLM calls mocked."""

    def _build_initial_state(self, query: str) -> dict:
        return {
            "query": query,
            "enriched_query": query,
            "session_id": "e2e-test-session",
            "chat_history": [],
            "image_context": "",
            "user_roles": ["engineer"],
            "access_tags": ["all", "public", "internal", "engineering"],
            "sources": [],
            "retry_count": 0,
        }

    def test_full_pipeline_direct_intent(self):
        """Direct intent: planner→researcher→reviewer(skip)→synthesizer."""
        mock_planner_llm = MagicMock()
        mock_planner_llm.invoke.return_value = MockLLMResponse("direct")

        mock_researcher_llm = MagicMock()
        mock_researcher_llm.invoke.return_value = MockLLMResponse(
            "Hello! I'm doing well. How can I help you?"
        )

        # Mock heavy deps
        mock_vs = MagicMock()
        mock_vs.advanced_rag_query = MagicMock()

        with patch.dict(sys.modules, _mock_heavy_deps()), \
             patch("app.agents.planner._get_planner_llm", return_value=mock_planner_llm), \
             patch("app.core.llm_router.get_router") as mock_get_router, \
             patch("app.core.llm_router.get_llm_for_config", return_value=mock_researcher_llm):

            # Setup router mock
            mock_router = MagicMock()
            mock_config = MagicMock()
            mock_config.provider = "gemini"
            mock_config.model = "gemini-2.5-flash"
            mock_config.reason = MagicMock(value="simple_query_optimization")
            mock_config.to_dict.return_value = {"provider": "gemini", "model": "gemini-2.5-flash", "reason": "simple"}
            mock_router.route.return_value = mock_config
            mock_get_router.return_value = mock_router

            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import create_agent_graph
            graph = create_agent_graph()
            state = self._build_initial_state("Hello, how are you?")
            result = graph.invoke(state)

            assert result.get("intent") == "direct"
            assert result.get("review_status") == "APPROVE"
            # Direct short answer passes through synthesizer
            assert "final_answer" in result

    def test_full_pipeline_rag_intent_approved(self):
        """RAG intent with high-quality retrieval → APPROVE path."""
        mock_planner_llm = MagicMock()
        mock_planner_llm.invoke.return_value = MockLLMResponse("rag")

        mock_reviewer_llm = MagicMock()
        mock_reviewer_llm.invoke.return_value = MockLLMResponse(
            '{"relevant": true, "confidence": 0.95, "reason": "Directly relevant"}'
        )

        mock_vs = MagicMock()
        mock_vs.advanced_rag_query = MagicMock(return_value={
            "answer": "Hybrid search uses both BM25 and vector embeddings for retrieval.",
            "sources": [{"file": "search_docs.pdf", "score": 0.92}],
        })

        with patch.dict(sys.modules, {**_mock_heavy_deps(), "app.services.vector_store": mock_vs}), \
             patch("app.agents.planner._get_planner_llm", return_value=mock_planner_llm), \
             patch("app.agents.reviewer._get_reviewer_llm", return_value=mock_reviewer_llm), \
             patch("app.core.llm_router.get_router") as mock_get_router, \
             patch("app.core.llm_router.get_llm_for_config") as mock_get_llm:

            mock_router = MagicMock()
            mock_config = MagicMock()
            mock_config.provider = "gemini"
            mock_config.model = "gemini-2.5-pro"
            mock_config.reason = MagicMock(value="complex_reasoning")
            mock_config.to_dict.return_value = {"provider": "gemini", "model": "gemini-2.5-pro", "reason": "complex"}
            mock_router.route.return_value = mock_config
            mock_get_router.return_value = mock_router

            mock_synth_llm = MagicMock()
            mock_synth_llm.invoke.return_value = MockLLMResponse(
                "Hybrid search combines BM25 sparse retrieval with dense vector search for more accurate results."
            )
            mock_get_llm.return_value = mock_synth_llm

            import importlib
            if "app.agents.researcher" in sys.modules:
                importlib.reload(sys.modules["app.agents.researcher"])
            if "app.agents.graph" in sys.modules:
                importlib.reload(sys.modules["app.agents.graph"])

            from app.agents.graph import create_agent_graph
            graph = create_agent_graph()
            state = self._build_initial_state("What is hybrid search?")
            result = graph.invoke(state)

            assert result.get("intent") == "rag"
            assert result.get("review_status") == "APPROVE"
            assert "final_answer" in result
            assert len(result["final_answer"]) > 0


class TestAgentState:
    """Test the AgentState TypedDict structure."""

    def test_state_has_required_fields(self):
        """AgentState should define all required pipeline fields."""
        from app.agents.state import AgentState
        fields = AgentState.__annotations__
        required = [
            "query", "enriched_query", "session_id", "chat_history",
            "intent", "raw_answer", "sources", "review_status",
            "retry_count", "final_answer",
        ]
        for f in required:
            assert f in fields, f"AgentState missing field: {f}"

    def test_state_has_rbac_fields(self):
        """AgentState should include v3.0 RBAC fields."""
        from app.agents.state import AgentState
        fields = AgentState.__annotations__
        assert "user_roles" in fields
        assert "access_tags" in fields
