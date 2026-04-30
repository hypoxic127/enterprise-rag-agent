"""
Hybrid LLM Router — Intelligent query routing between cloud and local models.

Routes queries to the optimal LLM based on:
  1. Data sensitivity (confidential → local Ollama)
  2. Query complexity (simple → Flash, complex → Pro)
  3. Availability (Ollama down → fallback to cloud)

Set LLM_ROUTER_ENABLED=true to activate routing logic.
When disabled, all queries go to Gemini Pro (default behavior).
"""

import time as _time
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import (
    LLM_ROUTER_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL,
    GOOGLE_API_KEY, SENSITIVE_TAGS,
)

# Simple query patterns (lowercased)
SIMPLE_PATTERNS = [
    "hello", "hi ", "hey", "thanks", "thank you", "bye", "goodbye",
    "what time", "what date", "who are you", "help",
]


class RouteReason(str, Enum):
    CONFIDENTIAL_DATA = "confidential_data_policy"
    SIMPLE_QUERY = "simple_query_optimization"
    COMPLEX_REASONING = "complex_reasoning"
    ROUTER_DISABLED = "router_disabled_default"
    OLLAMA_FALLBACK = "ollama_unavailable_fallback"


@dataclass
class LLMConfig:
    """Configuration for a routed LLM call."""
    provider: str           # "gemini" | "ollama"
    model: str              # e.g. "gemini-2.5-pro", "deepseek-r1:14b"
    reason: RouteReason     # Why this route was chosen
    temperature: float = 0.7
    endpoint: str = ""      # For ollama: base URL

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason.value,
            "endpoint": self.endpoint or "cloud",
        }


# ──────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────

class LLMRouter:
    """
    Stateless router that selects the optimal LLM for each query.

    Decision hierarchy:
      1. Confidential data → Local (Ollama)
      2. Simple queries → Gemini Flash (fast + cheap)
      3. Everything else → Gemini Pro (best quality)
      4. Ollama unavailable → fallback to Gemini Flash
    """

    def route(
        self,
        query: str,
        intent: str = "rag",
        access_tags: list[str] | None = None,
    ) -> LLMConfig:
        """
        Determine the optimal LLM for this query.

        Args:
            query: The user's query text.
            intent: Planner classification ("rag" | "web" | "direct").
            access_tags: User's expanded access tags from JWT/RBAC.
        """
        if not LLM_ROUTER_ENABLED:
            return LLMConfig(
                provider="gemini",
                model="gemini-2.5-pro",
                reason=RouteReason.ROUTER_DISABLED,
            )

        # Rule 1: If user has access to sensitive data, route to local LLM
        if access_tags and SENSITIVE_TAGS & set(access_tags):
            if self._is_ollama_available():
                logger.info("LLM Router: CONFIDENTIAL → local Ollama (%s)", OLLAMA_MODEL)
                return LLMConfig(
                    provider="ollama",
                    model=OLLAMA_MODEL,
                    reason=RouteReason.CONFIDENTIAL_DATA,
                    endpoint=OLLAMA_BASE_URL,
                    temperature=0.3,
                )
            else:
                logger.warning("LLM Router: Ollama unavailable, falling back to Gemini Flash")
                return LLMConfig(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    reason=RouteReason.OLLAMA_FALLBACK,
                )

        # Rule 2: Simple queries use fast/cheap model
        if self._is_simple_query(query):
            logger.info("LLM Router: SIMPLE → Gemini Flash")
            return LLMConfig(
                provider="gemini",
                model="gemini-2.5-flash",
                reason=RouteReason.SIMPLE_QUERY,
                temperature=0.5,
            )

        # Rule 3: Complex reasoning uses best available
        logger.info("LLM Router: COMPLEX → Gemini Pro")
        return LLMConfig(
            provider="gemini",
            model="gemini-2.5-pro",
            reason=RouteReason.COMPLEX_REASONING,
        )

    def _is_simple_query(self, query: str) -> bool:
        """Heuristic: detect simple/trivial queries."""
        q = query.lower().strip()
        if len(q) < 20:
            return True
        return any(q.startswith(p) for p in SIMPLE_PATTERNS)

    def _is_ollama_available(self) -> bool:
        """Quick health check on Ollama endpoint with 30s TTL cache."""
        now = _time.time()
        if now - self._ollama_checked_at < 30:
            return self._ollama_available
        try:
            import urllib.request
            req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                self._ollama_available = resp.status == 200
        except Exception:
            self._ollama_available = False
        self._ollama_checked_at = now
        return self._ollama_available

    _ollama_available: bool = False
    _ollama_checked_at: float = 0


# ──────────────────────────────────────────────
# LLM Factory
# ──────────────────────────────────────────────

# Cache for LLM instances
_llm_cache: dict[str, object] = {}


def get_llm_for_config(config: LLMConfig):
    """
    Factory: return a LangChain-compatible LLM instance for the given config.

    Caches instances by (provider, model) to avoid repeated initialization.
    """
    cache_key = f"{config.provider}:{config.model}"
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if config.provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=config.model,
            google_api_key=GOOGLE_API_KEY,
            temperature=config.temperature,
        )
    elif config.provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(
                model=config.model,
                base_url=config.endpoint or OLLAMA_BASE_URL,
                temperature=config.temperature,
            )
        except ImportError:
            logger.warning("langchain-ollama not installed, falling back to Gemini Flash")
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=GOOGLE_API_KEY,
                temperature=config.temperature,
            )
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")

    _llm_cache[cache_key] = llm
    return llm


# Singleton router instance
_router = LLMRouter()


def get_router() -> LLMRouter:
    return _router


# ──────────────────────────────────────────────
# Centralized Agent LLM Factories (replaces per-agent globals)
# ──────────────────────────────────────────────

def get_planner_llm() -> ChatGoogleGenerativeAI:
    """Fast model for intent classification (Gemini Flash)."""
    return get_llm_for_config(LLMConfig(
        provider="gemini", model="gemini-2.5-flash",
        reason=RouteReason.SIMPLE_QUERY, temperature=0,
    ))


def get_reviewer_llm() -> ChatGoogleGenerativeAI:
    """Fast model for relevance grading (Gemini Flash, temp=0)."""
    return get_llm_for_config(LLMConfig(
        provider="gemini", model="gemini-2.5-flash",
        reason=RouteReason.SIMPLE_QUERY, temperature=0,
    ))
