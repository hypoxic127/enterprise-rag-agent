"""
Auth Module — JWT-based authentication and RBAC role extraction.

Supports two modes:
  - Production: Validates JWT tokens (RS256/HS256) from Authorization header
  - Development: Bypasses auth, assigns default "engineer" role

Set AUTH_ENABLED=true and JWT_SECRET in .env for production.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

from app.core.config import AUTH_ENABLED, JWT_SECRET, JWT_ALGORITHM

# Lazy import to avoid hard dependency when auth is disabled
_jwt = None


def _get_jwt():
    global _jwt
    if _jwt is None:
        import jwt as _jwt_module
        _jwt = _jwt_module
    return _jwt

# Default roles for development mode (when auth is disabled)
DEV_USER = {
    "user_id": "dev-user",
    "email": "dev@enterprise.local",
    "roles": ["engineer", "viewer"],
    "department": "engineering",
}

# Role hierarchy for RBAC
ROLE_HIERARCHY = {
    "viewer":    ["all", "public"],
    "engineer":  ["all", "public", "internal", "engineering"],
    "manager":   ["all", "public", "internal", "engineering", "management", "confidential"],
    "executive": ["all", "public", "internal", "engineering", "management", "confidential", "executive", "secret"],
}

security = HTTPBearer(auto_error=False)


# ──────────────────────────────────────────────
# User Context
# ──────────────────────────────────────────────

class UserContext:
    """Authenticated user context with resolved access roles."""

    def __init__(self, user_id: str, email: str, roles: list[str], department: str):
        self.user_id = user_id
        self.email = email
        self.roles = roles
        self.department = department
        # Expand roles to include all accessible document tags
        self.access_tags = self._resolve_access_tags()

    def _resolve_access_tags(self) -> list[str]:
        """Expand user roles into the full set of document access tags."""
        tags = set()
        for role in self.roles:
            tags.update(ROLE_HIERARCHY.get(role, ["all", "public"]))
        return list(tags)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "roles": self.roles,
            "department": self.department,
            "access_tags": self.access_tags,
        }


# ──────────────────────────────────────────────
# Auth Dependency
# ──────────────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserContext:
    """
    FastAPI dependency to extract the current user from JWT.

    - If AUTH_ENABLED=false: returns a dev user with "engineer" role.
    - If AUTH_ENABLED=true: decodes and validates the Bearer token.
    """
    if not AUTH_ENABLED:
        return UserContext(**DEV_USER)

    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    jwt = _get_jwt()
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        user = UserContext(
            user_id=payload.get("sub", "unknown"),
            email=payload.get("email", ""),
            roles=payload.get("roles", ["viewer"]),
            department=payload.get("department", "general"),
        )
        logger.info("Authenticated user: %s (roles=%s)", user.user_id, user.roles)
        return user

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def get_current_user_from_token(token: str) -> UserContext:
    """
    Standalone JWT decode for use outside FastAPI request context.

    Used by the Channel Gateway to authenticate messages from non-web channels.
    Returns a dev user if auth is disabled, same as the FastAPI dependency.
    """
    if not AUTH_ENABLED:
        return UserContext(**DEV_USER)

    jwt = _get_jwt()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return UserContext(
            user_id=payload.get("sub", "unknown"),
            email=payload.get("email", ""),
            roles=payload.get("roles", ["viewer"]),
            department=payload.get("department", "general"),
        )
    except Exception as e:
        logger.warning("Token decode failed: %s", e)
        return UserContext(**DEV_USER)

