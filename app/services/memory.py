"""
Chat Memory Store — In-memory session-based conversation history.

Stores chat history per session_id with automatic TTL cleanup.
For production, replace with Redis-backed implementation.
"""

import logging
import time
import threading
from collections import OrderedDict
from typing import Optional
from dataclasses import dataclass, field
from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

# Maximum messages per session (sliding window)
MAX_MESSAGES_PER_SESSION = 50
# Maximum number of sessions in memory
MAX_SESSIONS = 1000
# Session TTL in seconds (2 hours)
SESSION_TTL_SECONDS = 7200


@dataclass
class Session:
    """A single chat session with metadata."""
    session_id: str
    title: str = "New Conversation"
    messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class ChatMemoryStore:
    """
    Thread-safe, in-memory chat memory store with LRU eviction and TTL.
    
    Usage:
        store = ChatMemoryStore()
        store.add_message("session-123", "user", "What is iPhone 18?")
        store.add_message("session-123", "assistant", "iPhone 18 costs 19999 RMB.")
        history = store.get_history("session-123")
    """

    def __init__(self):
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()
        logger.info("ChatMemoryStore initialized (max_sessions=%d, ttl=%ds)", MAX_SESSIONS, SESSION_TTL_SECONDS)

    def get_or_create_session(self, session_id: str) -> Session:
        """Get an existing session or create a new one."""
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = time.time()
                # Move to end (most recently used)
                self._sessions.move_to_end(session_id)
                return session
            
            # Create new session
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
            
            # Evict oldest if over capacity
            while len(self._sessions) > MAX_SESSIONS:
                evicted_id, _ = self._sessions.popitem(last=False)
                logger.info("Evicted session %s (LRU)", evicted_id)
            
            logger.info("Created new session: %s", session_id)
            return session

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session's history."""
        session = self.get_or_create_session(session_id)
        with self._lock:
            session.messages.append({
                "role": role,
                "content": content,
                "timestamp": time.time(),
            })
            # Enforce sliding window
            if len(session.messages) > MAX_MESSAGES_PER_SESSION:
                session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
            
            # Auto-generate title from first user message
            if session.title == "New Conversation" and role == "user":
                session.title = content[:50] + ("..." if len(content) > 50 else "")

    def get_history(self, session_id: str) -> list[ChatMessage]:
        """Get chat history as LlamaIndex ChatMessage objects."""
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
        """Return a summary list of all active sessions (for sidebar)."""
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
            # Cleanup expired
            for sid in expired:
                del self._sessions[sid]
                logger.info("Expired session: %s", sid)
            
            return list(reversed(result))  # Newest first

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Deleted session: %s", session_id)
                return True
            return False


# Global singleton
memory_store = ChatMemoryStore()
