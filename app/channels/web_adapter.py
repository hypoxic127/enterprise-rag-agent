"""
Web Channel Adapter — Adapts the existing Web UI SSE flow into the ChannelAdapter interface.

This adapter preserves backward compatibility with the current Next.js frontend.
"""

from loguru import logger
from app.channels.gateway import ChannelAdapter, UnifiedMessage, UnifiedResponse


class WebAdapter(ChannelAdapter):
    """
    Adapter for the Next.js Web UI.

    The existing /api/chat SSE endpoint remains the primary web interface.
    This adapter enables the web channel to also be used through the
    unified gateway endpoint.
    """

    channel_name = "web"

    async def parse_inbound(self, raw_event: dict) -> UnifiedMessage:
        """Convert a web UI request into a UnifiedMessage."""
        return UnifiedMessage(
            channel="web",
            user_id=raw_event.get("user_id", "web-user"),
            session_id=raw_event.get("session_id", ""),
            content=raw_event.get("message", ""),
            attachments=raw_event.get("attachments", []),
            metadata={"source": "web_ui"},
            auth_token=raw_event.get("auth_token"),
        )

    async def format_outbound(self, response: UnifiedResponse, channel_meta: dict) -> dict:
        """Format response for Web UI consumption (Markdown + sources)."""
        return {
            "type": "web",
            "content": response.content,
            "sources": response.sources,
            "session_id": response.session_id,
            "render_hint": "markdown",
            "llm_route_info": response.llm_route_info,
        }
