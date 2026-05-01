"""
Memory — SQLite-backed Window Buffer Memory for Conversation History
=====================================================================
Persists conversation history to a SQLite database (memory.db).
Reads only the last N exchanges per session for the context window.
Thread-safe for concurrent FastAPI requests (SQLite WAL mode).
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.core.config import MEMORY_DB_PATH


@dataclass
class Exchange:
    """A single user-assistant exchange."""
    user: str
    assistant: str


class WindowBufferMemory:
    """
    SQLite-backed sliding window memory.

    Keeps the last `max_exchanges` conversation pairs per session_id.
    All history is persisted to disk; the window only limits what gets
    loaded into the LLM context.

    Usage:
        memory = WindowBufferMemory(max_exchanges=5)
        memory.add("session-1", user="What plans exist?", assistant="We have Bronze...")
        history = memory.get_history("session-1")
        prompt_messages = memory.to_messages("session-1")
    """

    def __init__(self, db_path: str | None = None, max_exchanges: int = 5):
        self.max_exchanges = max_exchanges
        self.db_path = str(db_path or MEMORY_DB_PATH)
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection (SQLite is thread-safe with per-thread connections)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read performance
        conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s on locks
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the conversation_history table if it doesn't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_turn
                ON conversation_history (session_id, turn_index)
            """)
            conn.commit()
        finally:
            conn.close()

    def _next_turn_index(self, conn: sqlite3.Connection, session_id: str) -> int:
        """Get the next turn index for a session."""
        row = conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM conversation_history WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0]

    def add(self, session_id: str, user: str, assistant: str) -> None:
        """
        Add an exchange (user + assistant pair) to the database.
        Each pair gets a single turn_index (user and assistant are stored as 2 rows).
        """
        with self._lock:
            conn = self._get_conn()
            try:
                turn = self._next_turn_index(conn, session_id)
                now = datetime.now(timezone.utc).isoformat()
                conn.executemany(
                    "INSERT INTO conversation_history (session_id, turn_index, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                    [
                        (session_id, turn, "user", user, now),
                        (session_id, turn, "assistant", assistant, now),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

    def get_history(self, session_id: str) -> list[Exchange]:
        """
        Return the last `max_exchanges` exchanges for a session.
        Reads from SQLite, returns only the window.
        """
        conn = self._get_conn()
        try:
            # Get the last N turn indices, then fetch their rows in order
            rows = conn.execute(
                """
                SELECT role, content, turn_index FROM conversation_history
                WHERE session_id = ? AND turn_index IN (
                    SELECT DISTINCT turn_index FROM conversation_history
                    WHERE session_id = ?
                    ORDER BY turn_index DESC
                    LIMIT ?
                )
                ORDER BY turn_index ASC, id ASC
                """,
                (session_id, session_id, self.max_exchanges),
            ).fetchall()

            # Pair up user/assistant rows into Exchange objects
            exchanges = []
            i = 0
            while i < len(rows):
                user_msg = ""
                asst_msg = ""
                if i < len(rows) and rows[i]["role"] == "user":
                    user_msg = rows[i]["content"]
                    i += 1
                if i < len(rows) and rows[i]["role"] == "assistant":
                    asst_msg = rows[i]["content"]
                    i += 1
                if user_msg or asst_msg:
                    exchanges.append(Exchange(user=user_msg, assistant=asst_msg))

            return exchanges
        finally:
            conn.close()

    def to_messages(self, session_id: str) -> list[dict]:
        """
        Convert history into OpenAI-style message dicts for LLM context.
        Returns list of {"role": "user"/"assistant", "content": "..."} dicts.
        """
        messages = []
        for ex in self.get_history(session_id):
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

    def get_full_history(self, session_id: str) -> list[dict]:
        """Return ALL exchanges for a session (not just the window). For auditing."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT turn_index, role, content, created_at FROM conversation_history WHERE session_id = ? ORDER BY turn_index ASC, role ASC",
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def clear(self, session_id: str) -> None:
        """Clear history for a session."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM conversation_history WHERE session_id = ?", (session_id,))
                conn.commit()
            finally:
                conn.close()

    def clear_all(self) -> None:
        """Clear all sessions."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM conversation_history")
                conn.commit()
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Singleton instance — shared across the application
# ---------------------------------------------------------------------------
memory = WindowBufferMemory(max_exchanges=5)
