"""
Memory — Window Buffer Memory for Conversation History
========================================================
Maintains the last N exchanges (user + assistant pairs) per session.
Thread-safe, in-memory store keyed by session_id.
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Exchange:
    """A single user-assistant exchange."""
    user: str
    assistant: str


class WindowBufferMemory:
    """
    Keeps a sliding window of the last `max_exchanges` conversation pairs
    per session_id. Thread-safe for concurrent FastAPI requests.

    Usage:
        memory = WindowBufferMemory(max_exchanges=5)
        memory.add("session-1", user="What plans exist?", assistant="We have Bronze...")
        history = memory.get_history("session-1")
        prompt_messages = memory.to_messages("session-1")
    """

    def __init__(self, max_exchanges: int = 5):
        self.max_exchanges = max_exchanges
        self._store: dict[str, list[Exchange]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, session_id: str, user: str, assistant: str) -> None:
        """Add an exchange and trim to window size."""
        with self._lock:
            self._store[session_id].append(Exchange(user=user, assistant=assistant))
            # Trim to window
            if len(self._store[session_id]) > self.max_exchanges:
                self._store[session_id] = self._store[session_id][-self.max_exchanges:]

    def get_history(self, session_id: str) -> list[Exchange]:
        """Return the current window of exchanges for a session."""
        with self._lock:
            return list(self._store[session_id])

    def to_messages(self, session_id: str) -> list[dict]:
        """
        Convert history into OpenAI-style message dicts for LLM context.
        Returns list of {"role": "user"/"assistant", "content": "..."} dicts.
        """
        messages = []
        with self._lock:
            for ex in self._store[session_id]:
                messages.append({"role": "user", "content": ex.user})
                messages.append({"role": "assistant", "content": ex.assistant})
        return messages

    def get_context_string(self, session_id: str) -> str:
        """Return history as a formatted string for prompt injection."""
        history = self.get_history(session_id)
        if not history:
            return ""
        lines = []
        for ex in history:
            lines.append(f"User: {ex.user}")
            lines.append(f"Assistant: {ex.assistant}")
        return "\n".join(lines)

    def clear(self, session_id: str) -> None:
        """Clear history for a session."""
        with self._lock:
            self._store.pop(session_id, None)

    def clear_all(self) -> None:
        """Clear all sessions."""
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Singleton instance — shared across the application
# ---------------------------------------------------------------------------
memory = WindowBufferMemory(max_exchanges=5)
