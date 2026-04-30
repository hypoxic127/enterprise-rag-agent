"""
Auth Module Tests — JWT/RBAC validation.

Tests:
  - Dev mode bypass
  - Role hierarchy expansion
  - JWT token encoding/decoding
  - Expired/invalid token handling
"""

import os
import pytest

# Ensure dev mode for baseline tests
os.environ["AUTH_ENABLED"] = "false"

from app.core.auth import (
    UserContext,
    ROLE_HIERARCHY,
    get_current_user_from_token,
)


class TestUserContext:
    """Test the UserContext class and role expansion logic."""

    def test_viewer_role_expands_correctly(self):
        """Viewer should only access 'all' and 'public' tags."""
        user = UserContext(
            user_id="u1", email="a@b.com", roles=["viewer"], department="general"
        )
        assert set(user.access_tags) == {"all", "public"}

    def test_engineer_role_expands_correctly(self):
        """Engineer should access all, public, internal, engineering."""
        user = UserContext(
            user_id="u2", email="b@b.com", roles=["engineer"], department="engineering"
        )
        expected = {"all", "public", "internal", "engineering"}
        assert set(user.access_tags) == expected

    def test_manager_role_includes_confidential(self):
        """Manager should include 'confidential' in access tags."""
        user = UserContext(
            user_id="u3", email="c@b.com", roles=["manager"], department="management"
        )
        assert "confidential" in user.access_tags
        assert "internal" in user.access_tags

    def test_executive_role_includes_secret(self):
        """Executive should access everything including 'secret'."""
        user = UserContext(
            user_id="u4", email="d@b.com", roles=["executive"], department="c-suite"
        )
        assert "secret" in user.access_tags
        assert "executive" in user.access_tags
        assert "confidential" in user.access_tags

    def test_multi_role_union(self):
        """Multiple roles should produce a union of all access tags."""
        user = UserContext(
            user_id="u5", email="e@b.com", roles=["viewer", "engineer"], department="eng"
        )
        # Should have the union of viewer + engineer tags
        assert "engineering" in user.access_tags
        assert "public" in user.access_tags

    def test_unknown_role_defaults_to_public(self):
        """Unknown role should default to 'all' + 'public'."""
        user = UserContext(
            user_id="u6", email="f@b.com", roles=["unknown_role"], department="general"
        )
        assert set(user.access_tags) == {"all", "public"}

    def test_to_dict_serialization(self):
        """to_dict() should return all user fields."""
        user = UserContext(
            user_id="u7", email="g@b.com", roles=["engineer"], department="eng"
        )
        d = user.to_dict()
        assert d["user_id"] == "u7"
        assert d["email"] == "g@b.com"
        assert d["roles"] == ["engineer"]
        assert "access_tags" in d


class TestDevModeAuth:
    """Test authentication in dev mode (AUTH_ENABLED=false)."""

    def test_dev_mode_returns_default_user(self):
        """When auth is disabled, should return dev user."""
        user = get_current_user_from_token("any-token-value")
        assert user.user_id == "dev-user"
        assert "engineer" in user.roles

    def test_dev_mode_empty_token(self):
        """Empty token in dev mode should still return dev user."""
        user = get_current_user_from_token("")
        assert user.user_id == "dev-user"


class TestJWTAuth:
    """Test JWT token decoding when auth is enabled."""

    def test_valid_jwt_decodes_correctly(self):
        """A properly signed JWT should decode to the correct user."""
        import jwt

        secret = "test-secret-key"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["JWT_SECRET"] = secret

        # Re-import to pick up new env vars
        import importlib
        import app.core.auth as auth_module
        importlib.reload(auth_module)

        payload = {
            "sub": "test-user-123",
            "email": "test@enterprise.com",
            "roles": ["manager"],
            "department": "engineering",
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        user = auth_module.get_current_user_from_token(token)
        assert user.user_id == "test-user-123"
        assert "manager" in user.roles
        assert "confidential" in user.access_tags

        # Reset to dev mode
        os.environ["AUTH_ENABLED"] = "false"
        importlib.reload(auth_module)

    def test_expired_jwt_returns_dev_user(self):
        """Expired JWT in tolerant mode should return dev user fallback."""
        import jwt
        import time

        secret = "test-secret-key"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["JWT_SECRET"] = secret

        import importlib
        import app.core.auth as auth_module
        importlib.reload(auth_module)

        payload = {
            "sub": "expired-user",
            "exp": int(time.time()) - 3600,  # expired 1 hour ago
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        # get_current_user_from_token gracefully falls back
        user = auth_module.get_current_user_from_token(token)
        # Should return dev user due to decode failure fallback
        assert user.user_id == "dev-user"

        # Reset
        os.environ["AUTH_ENABLED"] = "false"
        importlib.reload(auth_module)


class TestRoleHierarchy:
    """Test the ROLE_HIERARCHY configuration."""

    def test_all_roles_have_public_and_all(self):
        """Every role should include 'all' and 'public' tags."""
        for role, tags in ROLE_HIERARCHY.items():
            assert "all" in tags, f"Role '{role}' missing 'all' tag"
            assert "public" in tags, f"Role '{role}' missing 'public' tag"

    def test_hierarchy_is_monotonically_expanding(self):
        """Higher roles should have at least as many tags as lower roles."""
        ordered_roles = ["viewer", "engineer", "manager", "executive"]
        for i in range(len(ordered_roles) - 1):
            lower = set(ROLE_HIERARCHY[ordered_roles[i]])
            higher = set(ROLE_HIERARCHY[ordered_roles[i + 1]])
            assert lower.issubset(higher), (
                f"'{ordered_roles[i]}' tags should be a subset of '{ordered_roles[i+1]}'"
            )
