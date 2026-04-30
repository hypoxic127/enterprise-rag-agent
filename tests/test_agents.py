"""
Agent Node Tests — Unit tests for each graph node.

Tests planner, researcher, reviewer, and synthesizer nodes
with mocked LLM backends for deterministic behavior.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ["AUTH_ENABLED"] = "false"
os.environ["GOOGLE_API_KEY"] = "test-api-key"


# ──────────────────────────────────────────────
# Planner Tests
# ──────────────────────────────────────────────

class TestPlannerNode:
    """Test the planner_node intent classification."""

    def test_planner_classifies_rag(self, mock_state_rag):
        """RAG-related query should classify as 'rag'."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse("rag")

        with patch("app.agents.planner._get_planner_llm", return_value=mock_llm):
            from app.agents.planner import planner_node
            result = planner_node(mock_state_rag)
            assert result["intent"] == "rag"

    def test_planner_classifies_web(self, mock_state_web):
        """Web-search query should classify as 'web'."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse("web")

        with patch("app.agents.planner._get_planner_llm", return_value=mock_llm):
            from app.agents.planner import planner_node
            result = planner_node(mock_state_web)
            assert result["intent"] == "web"

    def test_planner_classifies_direct(self, mock_state_direct):
        """Simple greeting should classify as 'direct'."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse("direct")

        with patch("app.agents.planner._get_planner_llm", return_value=mock_llm):
            from app.agents.planner import planner_node
            result = planner_node(mock_state_direct)
            assert result["intent"] == "direct"

    def test_planner_unknown_defaults_to_rag(self, mock_state_rag):
        """Unknown LLM response should default to 'rag'."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse("unknown_intent")

        with patch("app.agents.planner._get_planner_llm", return_value=mock_llm):
            from app.agents.planner import planner_node
            result = planner_node(mock_state_rag)
            assert result["intent"] == "rag"

    def test_planner_error_defaults_to_rag(self, mock_state_rag):
        """LLM error should gracefully default to 'rag'."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")

        with patch("app.agents.planner._get_planner_llm", return_value=mock_llm):
            from app.agents.planner import planner_node
            result = planner_node(mock_state_rag)
            assert result["intent"] == "rag"


# ──────────────────────────────────────────────
# Reviewer Tests
# ──────────────────────────────────────────────

class TestReviewerNode:
    """Test the reviewer_node grading and CRAG logic."""

    def test_reviewer_skips_grading_for_web(self):
        """Web intent should auto-approve without grading."""
        from app.agents.reviewer import reviewer_node
        state = {
            "intent": "web",
            "raw_answer": "Current weather is sunny.",
            "retry_count": 0,
        }
        result = reviewer_node(state)
        assert result["review_status"] == "APPROVE"

    def test_reviewer_skips_grading_for_direct(self):
        """Direct intent should auto-approve without grading."""
        from app.agents.reviewer import reviewer_node
        state = {
            "intent": "direct",
            "raw_answer": "Hello! I'm doing great.",
            "retry_count": 0,
        }
        result = reviewer_node(state)
        assert result["review_status"] == "APPROVE"

    def test_reviewer_approves_relevant_answer(self, mock_state_with_review):
        """High-confidence relevant answer should be APPROVED."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse(
            '{"relevant": true, "confidence": 0.92, "reason": "Directly answers the query"}'
        )

        with patch("app.agents.reviewer._get_reviewer_llm", return_value=mock_llm):
            from app.agents.reviewer import reviewer_node
            result = reviewer_node(mock_state_with_review)
            assert result["review_status"] == "APPROVE"

    def test_reviewer_rejects_irrelevant_answer(self):
        """Low-confidence irrelevant answer should be REJECTED."""
        from tests.conftest import MockLLMResponse
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            MockLLMResponse('{"relevant": false, "confidence": 0.2, "reason": "Off topic"}'),
            MockLLMResponse("What is the BM25 ranking algorithm and how does it work?"),
        ]

        with patch("app.agents.reviewer._get_reviewer_llm", return_value=mock_llm):
            from app.agents.reviewer import reviewer_node
            state = {
                "query": "Explain BM25",
                "intent": "rag",
                "raw_answer": "The weather is nice today.",
                "retry_count": 0,
            }
            result = reviewer_node(state)
            assert result["review_status"] == "REJECT"
            assert result["retry_count"] == 1
            assert result.get("rewritten_query") is not None

    def test_reviewer_force_approve_after_max_retries(self):
        """After MAX_RETRIES, should force APPROVE regardless of quality."""
        from app.agents.reviewer import reviewer_node, MAX_RETRIES
        state = {
            "intent": "rag",
            "raw_answer": "Some mediocre answer.",
            "retry_count": MAX_RETRIES,
            "query": "test query",
        }
        result = reviewer_node(state)
        assert result["review_status"] == "APPROVE"


# ──────────────────────────────────────────────
# Synthesizer Tests
# ──────────────────────────────────────────────

class TestSynthesizerNode:
    """Test the synthesizer_node output polishing."""

    def test_synthesizer_passes_through_short_answers(self):
        """Short answers (< 100 chars) should pass through without LLM call."""
        from app.agents.synthesizer import synthesizer_node
        state = {
            "review_status": "APPROVE",
            "raw_answer": "Hello! I'm doing great.",  # < 100 chars
            "final_answer": "",
            "query": "Hello",
            "enriched_query": "Hello",
            "sources": [],
        }
        result = synthesizer_node(state)
        assert result["final_answer"] == "Hello! I'm doing great."
        assert result["llm_route_info"]["reason"] == "short_answer"

    def test_synthesizer_passes_through_errors(self):
        """Error messages should pass through without LLM call."""
        from app.agents.synthesizer import synthesizer_node
        state = {
            "review_status": "APPROVE",
            "raw_answer": "Error: API connection failed",
            "query": "test",
            "enriched_query": "test",
            "sources": [],
        }
        result = synthesizer_node(state)
        assert "Error" in result["final_answer"]

    def test_synthesizer_cleans_markdown_headings(self):
        """Output cleaner should remove leading markdown headings."""
        from app.agents.synthesizer import _clean_synthesis_output

        dirty = "### Overview\n\nHere is the answer."
        clean = _clean_synthesis_output(dirty)
        assert "###" not in clean
        assert "answer" in clean

    def test_synthesizer_cleans_horizontal_rules(self):
        """Output cleaner should remove horizontal rules."""
        from app.agents.synthesizer import _clean_synthesis_output

        dirty = "First paragraph.\n\n---\n\nSecond paragraph."
        clean = _clean_synthesis_output(dirty)
        assert "---" not in clean
        assert "First paragraph" in clean
        assert "Second paragraph" in clean

    def test_synthesizer_preserves_content(self):
        """Cleaning should preserve meaningful content."""
        from app.agents.synthesizer import _clean_synthesis_output

        text = "BM25 is a ranking function. It uses term frequency."
        clean = _clean_synthesis_output(text)
        assert "BM25" in clean
        assert "ranking function" in clean

    def test_synthesizer_strips_answer_prefix(self):
        """Cleaning should remove 'Here is the answer:' type prefixes."""
        from app.agents.synthesizer import _clean_synthesis_output

        prefixed = "Here is the synthesized answer:\n\nBM25 is great."
        clean = _clean_synthesis_output(prefixed)
        assert not clean.startswith("Here is")

    def test_synthesizer_collapses_blank_lines(self):
        """Cleaning should collapse excessive blank lines."""
        from app.agents.synthesizer import _clean_synthesis_output

        text = "Paragraph one.\n\n\n\n\nParagraph two."
        clean = _clean_synthesis_output(text)
        assert "\n\n\n" not in clean
