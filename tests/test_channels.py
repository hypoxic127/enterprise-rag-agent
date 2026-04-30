"""
Channel Gateway Tests — Adapter and gateway validation.

Tests:
  - API adapter inbound parsing
  - API adapter outbound formatting
  - Web adapter inbound parsing
  - Gateway adapter registration
  - Gateway message processing (mocked)

Note: Uses lazy imports inside test methods to avoid triggering
the full production import chain (qdrant, llama_index, etc.)
which may not be installed in the test environment.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

os.environ["AUTH_ENABLED"] = "false"
os.environ["GOOGLE_API_KEY"] = "test-api-key"


# ──────────────────────────────────────────────
# UnifiedMessage / UnifiedResponse Tests
# ──────────────────────────────────────────────

class TestUnifiedProtocol:
    """Test the unified message/response dataclasses."""

    def _get_classes(self):
        """Lazy import to avoid full dependency chain."""
        # Mock out the graph import that pulls in heavy deps
        mock_graph_module = MagicMock()
        mock_graph_module.create_agent_graph = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.gateway import UnifiedMessage, UnifiedResponse
            return UnifiedMessage, UnifiedResponse

    def test_unified_message_defaults(self):
        """UnifiedMessage should have sensible defaults."""
        UnifiedMessage, _ = self._get_classes()
        msg = UnifiedMessage(
            channel="test",
            user_id="u1",
            session_id="s1",
            content="Hello",
        )
        assert msg.attachments == []
        assert msg.metadata == {}
        assert msg.auth_token is None

    def test_unified_response_defaults(self):
        """UnifiedResponse should have sensible defaults."""
        _, UnifiedResponse = self._get_classes()
        resp = UnifiedResponse(content="Test answer")
        assert resp.sources == []
        assert resp.render_hint == "markdown"
        assert resp.error is None

    def test_unified_response_to_dict(self):
        """to_dict should serialize all fields."""
        _, UnifiedResponse = self._get_classes()
        resp = UnifiedResponse(
            content="Answer text",
            sources=[{"file": "doc.pdf", "score": 0.9}],
            session_id="s1",
        )
        d = resp.to_dict()
        assert d["content"] == "Answer text"
        assert len(d["sources"]) == 1
        assert d["session_id"] == "s1"
        assert d["error"] is None

    def test_unified_response_error(self):
        """Error response should include error field."""
        _, UnifiedResponse = self._get_classes()
        resp = UnifiedResponse(content="", error="Pipeline failed")
        d = resp.to_dict()
        assert d["error"] == "Pipeline failed"
        assert d["content"] == ""


# ──────────────────────────────────────────────
# API Adapter Tests
# ──────────────────────────────────────────────

class TestAPIAdapter:
    """Test the APIAdapter channel implementation."""

    def _get_adapter(self):
        mock_graph_module = MagicMock()
        mock_graph_module.create_agent_graph = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.api_adapter import APIAdapter
            return APIAdapter()

    @pytest.mark.asyncio
    async def test_parse_inbound(self):
        """API adapter should correctly parse inbound events."""
        adapter = self._get_adapter()
        raw = {
            "message": "What is RAG?",
            "session_id": "api-session-1",
            "user_id": "api-client-42",
            "auth_token": "bearer-token-xyz",
            "metadata": {"source": "ci-pipeline"},
        }
        msg = await adapter.parse_inbound(raw)
        assert msg.channel == "api"
        assert msg.content == "What is RAG?"
        assert msg.user_id == "api-client-42"
        assert msg.session_id == "api-session-1"
        assert msg.auth_token == "bearer-token-xyz"

    @pytest.mark.asyncio
    async def test_parse_inbound_defaults(self):
        """Missing fields should use defaults."""
        adapter = self._get_adapter()
        raw = {"message": "Hello"}
        msg = await adapter.parse_inbound(raw)
        assert msg.user_id == "api-client"
        assert msg.session_id == ""
        assert msg.auth_token is None

    @pytest.mark.asyncio
    async def test_format_outbound_success(self):
        """Successful response should format correctly."""
        mock_graph_module = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.api_adapter import APIAdapter
            from app.channels.gateway import UnifiedResponse
            adapter = APIAdapter()
            response = UnifiedResponse(
                content="RAG stands for Retrieval-Augmented Generation.",
                sources=[{"file": "rag_paper.pdf"}],
                session_id="s1",
            )
            result = await adapter.format_outbound(response, {})
            assert result["status"] == "success"
            assert result["data"]["answer"] == "RAG stands for Retrieval-Augmented Generation."
            assert len(result["data"]["sources"]) == 1

    @pytest.mark.asyncio
    async def test_format_outbound_error(self):
        """Error response should include error field."""
        mock_graph_module = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.api_adapter import APIAdapter
            from app.channels.gateway import UnifiedResponse
            adapter = APIAdapter()
            response = UnifiedResponse(content="", error="Pipeline crashed")
            result = await adapter.format_outbound(response, {})
            assert result["status"] == "error"
            assert result["error"] == "Pipeline crashed"


# ──────────────────────────────────────────────
# Web Adapter Tests
# ──────────────────────────────────────────────

class TestWebAdapter:
    """Test the WebAdapter channel implementation."""

    @pytest.mark.asyncio
    async def test_parse_inbound(self):
        """Web adapter should correctly parse inbound events."""
        mock_graph_module = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.web_adapter import WebAdapter
            adapter = WebAdapter()
            raw = {
                "message": "Search for vector databases",
                "session_id": "web-s1",
                "user_id": "browser-user",
            }
            msg = await adapter.parse_inbound(raw)
            assert msg.channel == "web"
            assert msg.content == "Search for vector databases"


# ──────────────────────────────────────────────
# Channel Gateway Tests
# ──────────────────────────────────────────────

class TestChannelGateway:
    """Test the ChannelGateway registry and dispatch."""

    def _get_gateway_classes(self):
        mock_graph_module = MagicMock()
        mock_graph_module.create_agent_graph = MagicMock()
        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.gateway import ChannelGateway, UnifiedMessage, UnifiedResponse
            from app.channels.api_adapter import APIAdapter
            from app.channels.web_adapter import WebAdapter
            return ChannelGateway, UnifiedMessage, UnifiedResponse, APIAdapter, WebAdapter

    def test_register_adapter(self):
        """Adapters should register by channel_name."""
        ChannelGateway, _, _, APIAdapter, _ = self._get_gateway_classes()
        gw = ChannelGateway()
        api_adapter = APIAdapter()
        gw.register(api_adapter)
        assert "api" in gw.available_channels
        assert gw.get_adapter("api") is api_adapter

    def test_register_multiple_adapters(self):
        """Multiple adapters should coexist."""
        ChannelGateway, _, _, APIAdapter, WebAdapter = self._get_gateway_classes()
        gw = ChannelGateway()
        gw.register(APIAdapter())
        gw.register(WebAdapter())
        assert len(gw.available_channels) == 2
        assert "api" in gw.available_channels
        assert "web" in gw.available_channels

    def test_get_unknown_adapter(self):
        """Unknown channel should return None."""
        ChannelGateway, _, _, _, _ = self._get_gateway_classes()
        gw = ChannelGateway()
        assert gw.get_adapter("slack") is None

    @pytest.mark.asyncio
    async def test_process_message_returns_response(self):
        """process_message should return a UnifiedResponse."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "final_answer": "Test response from mocked graph.",
            "sources": [],
            "llm_route_info": {},
        }

        mock_graph_module = MagicMock()
        mock_graph_module.create_agent_graph = MagicMock(return_value=mock_graph)

        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.gateway import ChannelGateway, UnifiedMessage, UnifiedResponse
            with patch("app.channels.gateway.create_agent_graph", return_value=mock_graph):
                gw = ChannelGateway()
                msg = UnifiedMessage(
                    channel="api",
                    user_id="test-user",
                    session_id="test-s1",
                    content="Test query",
                )
                response = await gw.process_message(msg)
                assert isinstance(response, UnifiedResponse)
                assert response.content == "Test response from mocked graph."
                assert response.error is None

    @pytest.mark.asyncio
    async def test_process_message_handles_error(self):
        """Pipeline errors should be captured in response.error."""
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = Exception("Graph explosion")

        mock_graph_module = MagicMock()
        mock_graph_module.create_agent_graph = MagicMock(return_value=mock_graph)

        with patch.dict(sys.modules, {"app.agents.graph": mock_graph_module}):
            from app.channels.gateway import ChannelGateway, UnifiedMessage, UnifiedResponse
            with patch("app.channels.gateway.create_agent_graph", return_value=mock_graph):
                gw = ChannelGateway()
                msg = UnifiedMessage(
                    channel="api",
                    user_id="test-user",
                    session_id="test-s1",
                    content="Test query",
                )
                response = await gw.process_message(msg)
                assert response.error is not None
                assert "Pipeline error" in response.error
