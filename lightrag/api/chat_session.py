"""
In-memory session store for chat-based conversation tracking.

Sessions are keyed by UUID, expire after CHAT_SESSION_TTL seconds of inactivity,
and store at most CHAT_MAX_HISTORY conversation turns.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from lightrag.utils import get_env_value, logger


@dataclass
class SessionData:
    history: List[Dict[str, str]] = field(default_factory=list)
    """Conversation turns: [{"role": "user"|"assistant", "content": "..."}]"""
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


class SessionStore:
    """Thread-safe (single-process) in-memory session store.

    Sessions are evicted lazily when accessed after TTL has elapsed.
    """

    def __init__(self, max_history: int = 20, ttl_seconds: int = 3600):
        self.max_history = max_history
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, SessionData] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(
        self, session_id: Optional[str]
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Return (session_id, history) for the given session_id.

        If session_id is None or does not exist, a new session is created and
        an empty history is returned.
        """
        self._evict_expired()

        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_accessed = time.time()
            return session_id, list(session.history)

        # Create a new session
        new_id = session_id if session_id else str(uuid.uuid4())
        self._sessions[new_id] = SessionData()
        logger.debug(f"[SessionStore] Created new session: {new_id}")
        return new_id, []

    def append(
        self, session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Append a user/assistant exchange to the session history."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionData()

        session = self._sessions[session_id]
        session.history.append({"role": "user", "content": user_msg})
        session.history.append({"role": "assistant", "content": assistant_msg})
        session.last_accessed = time.time()

        # Trim to max_history turns (each turn = 2 messages)
        max_messages = self.max_history * 2
        if len(session.history) > max_messages:
            session.history = session.history[-max_messages:]

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Return the history for a session, or an empty list if not found."""
        self._evict_expired()
        if session_id not in self._sessions:
            return []
        session = self._sessions[session_id]
        session.last_accessed = time.time()
        return list(session.history)

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed, False otherwise."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"[SessionStore] Deleted session: {session_id}")
            return True
        return False

    def list_sessions(self) -> List[str]:
        """Return all active (non-expired) session IDs."""
        self._evict_expired()
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        """Remove sessions whose last_accessed is older than ttl_seconds."""
        now = time.time()
        expired = [
            sid
            for sid, data in self._sessions.items()
            if (now - data.last_accessed) > self.ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.debug(f"[SessionStore] Evicted expired session: {sid}")


# ---------------------------------------------------------------------------
# Module-level singleton – imported by query_routes and lightrag_server
# ---------------------------------------------------------------------------

session_store = SessionStore(
    max_history=get_env_value("CHAT_MAX_HISTORY", 20, int),
    ttl_seconds=get_env_value("CHAT_SESSION_TTL", 3600, int),
)
