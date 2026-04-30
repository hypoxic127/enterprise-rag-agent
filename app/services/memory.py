"""
Chat Memory Store — Redis-backed session persistence with in-memory fallback.

Production: Uses Redis for cross-restart persistence.
Development: Falls back to in-memory store if Redis is unavailable.
"""

import json
import time
import threading
from collections import OrderedDict
from typing import Optional
from dataclasses import dataclass, field
from llama_index.core.llms import ChatMessage, MessageRole
from loguru import logger

# Configuration
MAX_MESSAGES_PER_SESSION = 50
MAX_SESSIONS = 1000
SESSION_TTL_SECONDS = 7200  # 2 hours


# ──────────────────────────────────────────────
# Redis Backend
# ──────────────────────────────────────────────
class RedisMemoryStore:
    """Redis-backed chat memory with automatic TTL."""

    def __init__(self, redis_url: str):
        import redis as redis_lib
        self._r = redis_lib.from_url(redis_url, decode_responses=True)
        self._r.ping()  # Verify connection
        logger.info("RedisMemoryStore connected → %s", redis_url)

    def _session_key(self, sid: str) -> str:
        return f"rag:session:{sid}"

    def _meta_key(self, sid: str) -> str:
        return f"rag:meta:{sid}"

    def _index_key(self) -> str:
        return "rag:sessions"

    def get_or_create_session(self, session_id: str) -> None:
        meta_key = self._meta_key(session_id)
        if not self._r.exists(meta_key):
            self._r.hset(meta_key, mapping={
                "title": "New Conversation",
                "created_at": str(time.time()),
                "last_active": str(time.time()),
            })
            self._r.sadd(self._index_key(), session_id)
            logger.info("Created new Redis session: %s", session_id)
        self._r.hset(meta_key, "last_active", str(time.time()))
        self._r.expire(meta_key, SESSION_TTL_SECONDS)
        self._r.expire(self._session_key(session_id), SESSION_TTL_SECONDS)

    def add_message(self, session_id: str, role: str, content: str, sources: list = None, image_url: str = None) -> None:
        self.get_or_create_session(session_id)
        msg = {
            "role": role,
            "content": content,
            "sources": sources or [],
            "timestamp": time.time(),
        }
        if image_url:
            msg["image_url"] = image_url

        self._r.rpush(self._session_key(session_id), json.dumps(msg, ensure_ascii=False))
        # Enforce sliding window
        self._r.ltrim(self._session_key(session_id), -MAX_MESSAGES_PER_SESSION, -1)
        # Auto-generate title from first user message
        if role == "user":
            meta = self._r.hgetall(self._meta_key(session_id))
            if meta.get("title") == "New Conversation":
                title = content[:50] + ("..." if len(content) > 50 else "")
                self._r.hset(self._meta_key(session_id), "title", title)

    def get_history(self, session_id: str) -> list[ChatMessage]:
        self.get_or_create_session(session_id)
        raw = self._r.lrange(self._session_key(session_id), 0, -1)
        return [
            ChatMessage(
                role=MessageRole.USER if json.loads(m)["role"] == "user" else MessageRole.ASSISTANT,
                content=json.loads(m)["content"],
            )
            for m in raw
        ]

    def get_sessions_list(self) -> list[dict]:
        session_ids = self._r.smembers(self._index_key())
        result = []
        expired = []
        now = time.time()
        for sid in session_ids:
            meta = self._r.hgetall(self._meta_key(sid))
            if not meta:
                expired.append(sid)
                continue
            last_active = float(meta.get("last_active", 0))
            if now - last_active > SESSION_TTL_SECONDS:
                expired.append(sid)
                continue
            msg_count = self._r.llen(self._session_key(sid))
            result.append({
                "session_id": sid,
                "title": meta.get("title", "Untitled"),
                "message_count": msg_count,
                "last_active": last_active,
            })
        # Cleanup expired
        for sid in expired:
            self._r.srem(self._index_key(), sid)
            self._r.delete(self._meta_key(sid), self._session_key(sid))
            logger.info("Expired Redis session: %s", sid)
        # Sort newest first
        result.sort(key=lambda x: x["last_active"], reverse=True)
        return result

    def get_messages(self, session_id: str) -> list[dict] | None:
        if not self._r.exists(self._meta_key(session_id)):
            return None
        self._r.hset(self._meta_key(session_id), "last_active", str(time.time()))
        raw = self._r.lrange(self._session_key(session_id), 0, -1)
        result = []
        for m in raw:
            msg = json.loads(m)
            entry = {
                "role": msg["role"],
                "content": msg["content"],
                "sources": msg.get("sources", []),
            }
            if msg.get("image_url"):
                entry["image_url"] = msg["image_url"]
            result.append(entry)
        return result

    def delete_session(self, session_id: str) -> bool:
        if self._r.exists(self._meta_key(session_id)):
            self._r.delete(self._meta_key(session_id), self._session_key(session_id))
            self._r.srem(self._index_key(), session_id)
            logger.info("Deleted Redis session: %s", session_id)
            return True
        return False


# ──────────────────────────────────────────────
# In-Memory Fallback (original implementation)
# ──────────────────────────────────────────────
@dataclass
class Session:
    """A single chat session with metadata."""
    session_id: str
    title: str = "New Conversation"
    messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class InMemoryStore:
    """Thread-safe, in-memory chat memory store with LRU eviction and TTL."""

    def __init__(self):
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()
        logger.info("InMemoryStore initialized (fallback mode)")

    def get_or_create_session(self, session_id: str) -> Session:
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = time.time()
                self._sessions.move_to_end(session_id)
                return session
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
            while len(self._sessions) > MAX_SESSIONS:
                evicted_id, _ = self._sessions.popitem(last=False)
                logger.info("Evicted session %s (LRU)", evicted_id)
            logger.info("Created new session: %s", session_id)
            return session

    def add_message(self, session_id: str, role: str, content: str, sources: list = None, image_url: str = None) -> None:
        session = self.get_or_create_session(session_id)
        with self._lock:
            msg = {
                "role": role,
                "content": content,
                "sources": sources or [],
                "timestamp": time.time(),
            }
            if image_url:
                msg["image_url"] = image_url
            session.messages.append(msg)
            if len(session.messages) > MAX_MESSAGES_PER_SESSION:
                session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
            if session.title == "New Conversation" and role == "user":
                session.title = content[:50] + ("..." if len(content) > 50 else "")

    def get_history(self, session_id: str) -> list[ChatMessage]:
        session = self.get_or_create_session(session_id)
        with self._lock:
            return [
                ChatMessage(
                    role=MessageRole.USER if msg["role"] == "user" else MessageRole.ASSISTANT,
                    content=msg["content"],
                )
                for msg in session.messages
            ]

    def get_sessions_list(self) -> list[dict]:
        with self._lock:
            now = time.time()
            result = []
            expired = []
            for sid, session in self._sessions.items():
                if now - session.last_active > SESSION_TTL_SECONDS:
                    expired.append(sid)
                    continue
                result.append({
                    "session_id": session.session_id,
                    "title": session.title,
                    "message_count": len(session.messages),
                    "last_active": session.last_active,
                })
            for sid in expired:
                del self._sessions[sid]
                logger.info("Expired session: %s", sid)
            return list(reversed(result))

    def get_messages(self, session_id: str) -> list[dict] | None:
        with self._lock:
            if session_id not in self._sessions:
                return None
            session = self._sessions[session_id]
            session.last_active = time.time()
            result = []
            for msg in session.messages:
                entry = {
                    "role": msg["role"],
                    "content": msg["content"],
                    "sources": msg.get("sources", []),
                }
                if msg.get("image_url"):
                    entry["image_url"] = msg["image_url"]
                result.append(entry)
            return result

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Deleted session: %s", session_id)
                return True
            return False


# ──────────────────────────────────────────────
# Factory: Redis → InMemory fallback
# ──────────────────────────────────────────────
def _create_store():
    from app.core.config import REDIS_URL
    if REDIS_URL:
        try:
            return RedisMemoryStore(REDIS_URL)
        except Exception as e:
            logger.warning("Redis connection failed (%s), falling back to in-memory store", e)
    return InMemoryStore()


# Global singleton
memory_store = _create_store()
