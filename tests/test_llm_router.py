"""
LLM Router Tests — Routing logic validation.

Tests:
  - Router disabled → default Gemini Pro
  - Confidential data → local Ollama
  - Simple queries → Gemini Flash
  - Complex queries → Gemini Pro
  - Ollama fallback when unavailable
"""

import os
import pytest
from unittest.mock import patch

# Ensure router starts disabled
os.environ["LLM_ROUTER_ENABLED"] = "false"

from app.core.llm_router import LLMRouter, LLMConfig, RouteReason


class TestRouterDisabled:
    """Tests when LLM_ROUTER_ENABLED=false (default)."""

    def test_router_disabled_returns_gemini_pro(self):
        """When router is disabled, should always return Gemini Pro."""
        router = LLMRouter()
        # Monkey-patch the module-level flag for this test
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", False):
            config = router.route(query="Explain quantum computing", intent="rag")
            assert config.provider == "gemini"
            assert config.model == "gemini-2.5-pro"
            assert config.reason == RouteReason.ROUTER_DISABLED

    def test_router_disabled_ignores_access_tags(self):
        """Disabled router should ignore sensitive tags."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", False):
            config = router.route(
                query="Secret project details",
                access_tags=["confidential", "secret"],
            )
            assert config.provider == "gemini"
            assert config.reason == RouteReason.ROUTER_DISABLED


class TestRouterEnabled:
    """Tests when LLM_ROUTER_ENABLED=true."""

    def test_confidential_routes_to_ollama(self):
        """Queries with confidential tags should route to local Ollama."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True), \
             patch.object(router, "_is_ollama_available", return_value=True):
            config = router.route(
                query="Executive salary report Q3",
                access_tags=["all", "public", "confidential"],
            )
            assert config.provider == "ollama"
            assert config.reason == RouteReason.CONFIDENTIAL_DATA

    def test_secret_tags_route_to_ollama(self):
        """'secret' tag should also trigger local routing."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True), \
             patch.object(router, "_is_ollama_available", return_value=True):
            config = router.route(
                query="Board meeting minutes",
                access_tags=["secret"],
            )
            assert config.provider == "ollama"

    def test_ollama_unavailable_fallback(self):
        """When Ollama is down, confidential queries should fallback to Flash."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True), \
             patch.object(router, "_is_ollama_available", return_value=False):
            config = router.route(
                query="Confidential project alpha",
                access_tags=["confidential"],
            )
            assert config.provider == "gemini"
            assert config.model == "gemini-2.5-flash"
            assert config.reason == RouteReason.OLLAMA_FALLBACK

    def test_simple_query_routes_to_flash(self):
        """Short/simple queries should use Gemini Flash for cost optimization."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True):
            config = router.route(query="hello", access_tags=["public"])
            assert config.provider == "gemini"
            assert config.model == "gemini-2.5-flash"
            assert config.reason == RouteReason.SIMPLE_QUERY

    def test_short_query_is_simple(self):
        """Queries shorter than 20 chars should be classified as simple."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True):
            config = router.route(query="hi there", access_tags=["public"])
            assert config.reason == RouteReason.SIMPLE_QUERY

    def test_complex_query_routes_to_pro(self):
        """Complex queries should use Gemini Pro for best quality."""
        router = LLMRouter()
        with patch("app.core.llm_router.LLM_ROUTER_ENABLED", True):
            config = router.route(
                query="Compare and contrast the retrieval strategies of BM25 sparse matching versus dense vector embeddings in enterprise RAG systems",
                access_tags=["public"],
            )
            assert config.provider == "gemini"
            assert config.model == "gemini-2.5-pro"
            assert config.reason == RouteReason.COMPLEX_REASONING


class TestLLMConfig:
    """Test the LLMConfig dataclass."""

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        config = LLMConfig(
            provider="gemini",
            model="gemini-2.5-pro",
            reason=RouteReason.COMPLEX_REASONING,
            endpoint="cloud",
        )
        d = config.to_dict()
        assert d["provider"] == "gemini"
        assert d["model"] == "gemini-2.5-pro"
        assert d["reason"] == "complex_reasoning"

    def test_default_temperature(self):
        """Default temperature should be 0.7."""
        config = LLMConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            reason=RouteReason.SIMPLE_QUERY,
        )
        assert config.temperature == 0.7

    def test_custom_temperature(self):
        """Custom temperature should override default."""
        config = LLMConfig(
            provider="ollama",
            model="deepseek-r1:14b",
            reason=RouteReason.CONFIDENTIAL_DATA,
            temperature=0.3,
        )
        assert config.temperature == 0.3


class TestSimpleQueryDetection:
    """Test the _is_simple_query heuristic."""

    def test_greeting_is_simple(self):
        router = LLMRouter()
        assert router._is_simple_query("hello") is True
        assert router._is_simple_query("hi there") is True
        assert router._is_simple_query("thanks") is True

    def test_short_query_is_simple(self):
        router = LLMRouter()
        assert router._is_simple_query("what is AI?") is True  # < 20 chars

    def test_long_complex_query_is_not_simple(self):
        router = LLMRouter()
        assert router._is_simple_query(
            "Explain the differences between sparse and dense retrieval methods in enterprise search"
        ) is False
