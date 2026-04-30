"""
API Channel Adapter — Direct REST API access for programmatic consumers.

Returns JSON instead of SSE streaming. Ideal for:
  - CI/CD pipelines
  - Internal microservices
  - CLI tools
  - External integrations
"""

from loguru import logger
from app.channels.gateway import ChannelAdapter, UnifiedMessage, UnifiedResponse


class APIAdapter(ChannelAdapter):
    """
    Adapter for direct REST API access.

    Messages come in as JSON, responses go out as JSON.
    No streaming — synchronous request/response.
    """

    channel_name = "api"

    async def parse_inbound(self, raw_event: dict) -> UnifiedMessage:
        """Convert an API request into a UnifiedMessage."""
        return UnifiedMessage(
            channel="api",
            user_id=raw_event.get("user_id", "api-client"),
            session_id=raw_event.get("session_id", ""),
            content=raw_event.get("message", raw_event.get("query", "")),
            attachments=raw_event.get("attachments", []),
            metadata=raw_event.get("metadata", {}),
            auth_token=raw_event.get("auth_token"),
        )

    async def format_outbound(self, response: UnifiedResponse, channel_meta: dict) -> dict:
        """Format response as plain JSON for API consumers."""
        result = {
            "status": "error" if response.error else "success",
            "data": {
                "answer": response.content,
                "sources": response.sources,
                "session_id": response.session_id,
                "llm_route_info": response.llm_route_info,
            },
        }
        if response.error:
            result["error"] = response.error
        return result
