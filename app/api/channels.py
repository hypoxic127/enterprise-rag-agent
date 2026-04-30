"""
Channels API Router — Unified endpoint for multi-channel message processing.

Exposes:
  POST /api/channels/{channel}/message — Process a message through a specific channel
  GET  /api/channels                   — List available channels
  GET  /api/channels/router/info       — LLM Router configuration info
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger

from app.channels.gateway import get_gateway, UnifiedMessage
from app.channels.web_adapter import WebAdapter
from app.channels.api_adapter import APIAdapter
from app.core.llm_router import LLM_ROUTER_ENABLED, get_router

router = APIRouter()


# ──────────────────────────────────────────────
# Initialize gateway with built-in adapters
# ──────────────────────────────────────────────

def _init_gateway():
    """Register all built-in channel adapters."""
    gw = get_gateway()
    if not gw.available_channels:
        gw.register(WebAdapter())
        gw.register(APIAdapter())
    return gw


# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────

class ChannelMessageRequest(BaseModel):
    message: str = Field(..., description="User message text")
    session_id: Optional[str] = Field(default="", description="Session ID for continuity")
    user_id: Optional[str] = Field(default="", description="User identifier")
    auth_token: Optional[str] = Field(default=None, description="JWT token for RBAC")
    metadata: Optional[dict] = Field(default_factory=dict, description="Extra metadata")


class ChannelInfo(BaseModel):
    channels: list[str]
    router_enabled: bool


class RouterInfo(BaseModel):
    enabled: bool
    default_provider: str
    default_model: str
    sensitive_tags: list[str]


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/channels", response_model=ChannelInfo)
async def list_channels():
    """List all available channels."""
    gw = _init_gateway()
    return ChannelInfo(
        channels=gw.available_channels,
        router_enabled=LLM_ROUTER_ENABLED,
    )


@router.post("/channels/{channel}/message")
async def process_channel_message(channel: str, request: ChannelMessageRequest):
    """
    Process a message through a specific channel adapter.

    This is the unified entry point for all non-SSE channels.
    """
    gw = _init_gateway()
    adapter = gw.get_adapter(channel)

    if not adapter:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel}' not found. Available: {gw.available_channels}",
        )

    # Parse inbound message
    raw_event = {
        "message": request.message,
        "session_id": request.session_id,
        "user_id": request.user_id,
        "auth_token": request.auth_token,
        "metadata": request.metadata,
    }

    try:
        unified_msg = await adapter.parse_inbound(raw_event)
        logger.info("Channel [%s] message from user=%s: %s",
                     channel, unified_msg.user_id, unified_msg.content[:80])

        # Process through agent pipeline
        response = await gw.process_message(unified_msg)

        # Format for channel
        formatted = await adapter.format_outbound(response, raw_event.get("metadata", {}))
        return formatted

    except Exception as e:
        logger.error("Channel [%s] processing error: %s", channel, e)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@router.get("/channels/router/info", response_model=RouterInfo)
async def get_router_info():
    """Get LLM Router configuration info."""
    from app.core.llm_router import SENSITIVE_TAGS
    return RouterInfo(
        enabled=LLM_ROUTER_ENABLED,
        default_provider="gemini",
        default_model="gemini-2.5-pro",
        sensitive_tags=list(SENSITIVE_TAGS),
    )
