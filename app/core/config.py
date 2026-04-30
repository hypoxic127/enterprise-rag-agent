"""
Centralized Configuration — Single source of truth for all settings.

All secrets, feature flags, and infrastructure config live here.
Other modules import from this file instead of calling os.getenv() directly.
"""

import os
from loguru import logger

# ──────────────────────────────────────────────
# Secrets & Auth
# ──────────────────────────────────────────────
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ──────────────────────────────────────────────
# LLM Router
# ──────────────────────────────────────────────
LLM_ROUTER_ENABLED = os.getenv("LLM_ROUTER_ENABLED", "false").lower() == "true"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")

# Tags indicating sensitive data that must stay local
SENSITIVE_TAGS = {"confidential", "secret", "executive"}

# ──────────────────────────────────────────────
# Infrastructure
# ──────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
REDIS_URL = os.getenv("REDIS_URL", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# ──────────────────────────────────────────────
# Startup Validation
# ──────────────────────────────────────────────
def validate_production_config():
    """
    Validate critical config on startup. Call from FastAPI lifespan.
    Raises RuntimeError if production mode has insecure defaults.
    """
    errors = []

    if AUTH_ENABLED:
        if JWT_SECRET == "dev-secret-change-me" or len(JWT_SECRET) < 32:
            errors.append(
                "JWT_SECRET must be a 32+ character secret in production. "
                "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY is not set — LLM calls will fail")

    if errors:
        for e in errors:
            logger.critical("CONFIG ERROR: %s", e)
        raise RuntimeError(f"Fatal config errors: {'; '.join(errors)}")

    logger.info(
        "Config validated — AUTH=%s, LLM_ROUTER=%s, QDRANT=%s:%d",
        AUTH_ENABLED, LLM_ROUTER_ENABLED, QDRANT_HOST, QDRANT_PORT,
    )
