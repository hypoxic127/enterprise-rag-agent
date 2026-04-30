"""
Channel Gateway — Unified message protocol for multi-channel access.

Defines:
  - UnifiedMessage: standardized inbound message from any channel
  - UnifiedResponse: standardized outbound response to any channel
  - ChannelAdapter: abstract base class for channel implementations
  - ChannelGateway: registry + dispatcher

Supports: Web UI (SSE), REST API (JSON), and future IM bots.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional
from loguru import logger

from app.agents.graph import create_agent_graph
from app.agents.state import AgentState
from app.core.auth import get_current_user_from_token, UserContext


# ──────────────────────────────────────────────
# Unified Message Protocol
# ──────────────────────────────────────────────

@dataclass
class UnifiedMessage:
    """Standardized inbound message from any channel."""
    channel: str                    # "web" | "api" | "slack" | "wecom" | "feishu"
    user_id: str                    # User identifier
    session_id: str                 # Conversation session ID
    content: str                    # Message text
    attachments: list = field(default_factory=list)    # Images, files
    metadata: dict = field(default_factory=dict)       # Channel-specific extras
    auth_token: Optional[str] = None                   # JWT for RBAC


@dataclass
class UnifiedResponse:
    """Standardized outbound response to any channel."""
    content: str                    # Answer text (Markdown)
    sources: list[dict] = field(default_factory=list)  # Citation sources
    llm_route_info: dict = field(default_factory=dict) # Which LLM was used
    render_hint: str = "markdown"   # "markdown" | "plaintext" | "card"
    session_id: str = ""            # Session ID for continuity
    error: Optional[str] = None     # Error message if failed

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "sources": self.sources,
            "llm_route_info": self.llm_route_info,
            "render_hint": self.render_hint,
            "session_id": self.session_id,
            "error": self.error,
        }


# ──────────────────────────────────────────────
# Channel Adapter — Abstract Base
# ──────────────────────────────────────────────

class ChannelAdapter(ABC):
    """
    Abstract base for channel implementations.

    Each adapter converts between channel-specific formats and the
    unified message protocol.
    """
    channel_name: str = "unknown"

    @abstractmethod
    async def parse_inbound(self, raw_event: dict) -> UnifiedMessage:
        """Convert channel-specific event into a UnifiedMessage."""
        ...

    @abstractmethod
    async def format_outbound(self, response: UnifiedResponse, channel_meta: dict) -> dict:
        """Convert UnifiedResponse into channel-specific format."""
        ...


# ──────────────────────────────────────────────
# Channel Gateway — Registry + Dispatcher
# ──────────────────────────────────────────────

class ChannelGateway:
    """
    Central gateway that routes messages through the agent pipeline.

    Adapters register themselves, and the gateway dispatches inbound
    messages through: parse → authenticate → agent graph → format.
    """

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter):
        """Register a channel adapter."""
        self._adapters[adapter.channel_name] = adapter
        logger.info("Channel adapter registered: %s", adapter.channel_name)

    def get_adapter(self, channel: str) -> ChannelAdapter | None:
        return self._adapters.get(channel)

    @property
    def available_channels(self) -> list[str]:
        return list(self._adapters.keys())

    async def process_message(self, message: UnifiedMessage) -> UnifiedResponse:
        """
        Process a unified message through the full agent pipeline.

        Flow: Auth → Build State → Run Graph → Return Response
        """
        # 1. Authenticate
        user_ctx = self._authenticate(message)

        # 2. Build initial agent state
        initial_state: AgentState = {
            "query": message.content,
            "enriched_query": message.content,
            "session_id": message.session_id or str(uuid.uuid4()),
            "chat_history": [],
            "image_context": "",
            "user_roles": user_ctx.roles if user_ctx else ["viewer"],
            "access_tags": user_ctx.access_tags if user_ctx else ["all", "public"],
            "intent": "",
            "raw_answer": "",
            "sources": [],
            "review_status": "",
            "retry_count": 0,
            "rewritten_query": None,
            "final_answer": "",
            "llm_route_info": {},
        }

        # 3. Run agent graph (singleton)
        try:
            if not hasattr(self, '_graph') or self._graph is None:
                self._graph = create_agent_graph()
            final_state = self._graph.invoke(initial_state)

            return UnifiedResponse(
                content=final_state.get("final_answer", ""),
                sources=final_state.get("sources", []),
                llm_route_info=final_state.get("llm_route_info", {}),
                session_id=message.session_id,
            )
        except Exception as e:
            logger.error("Gateway pipeline error: %s", e)
            return UnifiedResponse(
                content="",
                error=f"Pipeline error: {str(e)}",
                session_id=message.session_id,
            )

    def _authenticate(self, message: UnifiedMessage) -> UserContext | None:
        """Extract user context from the message's auth token."""
        if message.auth_token:
            try:
                return get_current_user_from_token(message.auth_token)
            except Exception as e:
                logger.warning("Gateway auth failed: %s", e)
        return None


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────

_gateway: ChannelGateway | None = None


def get_gateway() -> ChannelGateway:
    global _gateway
    if _gateway is None:
        _gateway = ChannelGateway()
    return _gateway
