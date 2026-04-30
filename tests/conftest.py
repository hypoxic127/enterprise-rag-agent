"""
Shared pytest fixtures for Enterprise RAG Agent tests.

Provides mock LLMs, mock vector stores, and test state builders
to enable fast, deterministic testing without external dependencies.
"""

import os
import sys
import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force auth to dev mode for all tests
os.environ["AUTH_ENABLED"] = "false"
os.environ["LLM_ROUTER_ENABLED"] = "false"
os.environ["GOOGLE_API_KEY"] = "test-api-key"


# ──────────────────────────────────────────────
# Mock LLM Response
# ──────────────────────────────────────────────

class MockLLMResponse:
    """Mimics a LangChain LLM response with a .content attribute."""

    def __init__(self, content: str):
        self.content = content


class MockLLM:
    """A deterministic mock LLM that returns pre-configured responses."""

    def __init__(self, response: str = "mock response"):
        self._response = response

    def invoke(self, prompt, **kwargs):
        return MockLLMResponse(self._response)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    """Returns a MockLLM instance with a default response."""
    return MockLLM("This is a mock LLM response for testing.")


@pytest.fixture
def mock_state_rag():
    """Returns a minimal AgentState dict for RAG intent testing."""
    return {
        "query": "What is hybrid search?",
        "enriched_query": "What is hybrid search?",
        "session_id": "test-session-001",
        "chat_history": [],
        "image_context": "",
        "user_roles": ["engineer"],
        "access_tags": ["all", "public", "internal", "engineering"],
        "sources": [],
        "retry_count": 0,
    }


@pytest.fixture
def mock_state_web():
    """Returns a minimal AgentState dict for Web intent testing."""
    return {
        "query": "What is the weather in Tokyo today?",
        "enriched_query": "What is the weather in Tokyo today?",
        "session_id": "test-session-002",
        "chat_history": [],
        "image_context": "",
        "user_roles": ["viewer"],
        "access_tags": ["all", "public"],
        "sources": [],
        "retry_count": 0,
    }


@pytest.fixture
def mock_state_direct():
    """Returns a minimal AgentState dict for direct answer testing."""
    return {
        "query": "Hello, how are you?",
        "enriched_query": "Hello, how are you?",
        "session_id": "test-session-003",
        "chat_history": [],
        "image_context": "",
        "user_roles": ["viewer"],
        "access_tags": ["all", "public"],
        "sources": [],
        "retry_count": 0,
    }


@pytest.fixture
def mock_state_with_review():
    """Returns a state with a raw_answer ready for reviewer evaluation."""
    return {
        "query": "Explain BM25 algorithm",
        "enriched_query": "Explain BM25 algorithm",
        "session_id": "test-session-004",
        "chat_history": [],
        "image_context": "",
        "user_roles": ["engineer"],
        "access_tags": ["all", "public", "internal", "engineering"],
        "intent": "rag",
        "raw_answer": "BM25 is a ranking function used in information retrieval. It uses term frequency saturation and document length normalization to score document relevance.",
        "sources": [{"file": "ir_textbook.pdf", "score": 0.89}],
        "retry_count": 0,
    }
