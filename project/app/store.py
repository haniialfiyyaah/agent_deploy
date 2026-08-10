"""Small SQLite repository for durable classroom conversation state."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.schemas import MessageRecord, MessageStatus, Role, ThreadDetail, ThreadSummary


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationStore:
    """Persist threads and ordered messages in one SQLite database."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self._lock = threading.RLock()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    summarized_through_position INTEGER NOT NULL DEFAULT -1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_threads_owner_updated
                    ON threads(owner_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(
                        status IN ('in_progress', 'completed', 'cancelled', 'error')
                    ),
                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(thread_id, position)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_thread_position
                    ON messages(thread_id, position);
                """
            )

    def create_thread(self, owner_id: str, title: str) -> ThreadSummary:
        thread_id = str(uuid4())
        now = _now()
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO threads(
                    id, owner_id, title, summary,
                    summarized_through_position, created_at, updated_at
                ) VALUES (?, ?, ?, '', -1, ?, ?)
                """,
                (thread_id, owner_id, title, now, now),
            )
        thread = self.get_thread(owner_id, thread_id)
        assert thread is not None
        return thread

    def list_threads(self, owner_id: str) -> list[ThreadSummary]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM threads
                WHERE owner_id = ?
                ORDER BY updated_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [self._thread_from_row(row) for row in rows]

    def get_thread(self, owner_id: str, thread_id: str) -> ThreadSummary | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM threads
                WHERE id = ? AND owner_id = ?
                """,
                (thread_id, owner_id),
            ).fetchone()
        return self._thread_from_row(row) if row else None

    def get_thread_detail(self, owner_id: str, thread_id: str) -> ThreadDetail | None:
        thread = self.get_thread(owner_id, thread_id)
        if thread is None:
            return None
        return ThreadDetail(**thread.model_dump(), messages=self.list_messages(thread_id))

    def delete_thread(self, owner_id: str, thread_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM threads WHERE id = ? AND owner_id = ?",
                (thread_id, owner_id),
            )
        return cursor.rowcount == 1

    def add_message(
        self,
        thread_id: str,
        role: Role,
        content: str,
        status: MessageStatus = "completed",
        estimated_tokens: int = 0,
    ) -> MessageRecord:
        message_id = str(uuid4())
        now = _now()
        with self._lock, self._connection() as connection:
            thread = connection.execute(
                "SELECT id FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
            if thread is None:
                raise KeyError(f"thread not found: {thread_id}")
            row = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_position "
                "FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            position = int(row["next_position"])
            connection.execute(
                """
                INSERT INTO messages(
                    id, thread_id, position, role, content, status,
                    estimated_tokens, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    thread_id,
                    position,
                    role,
                    content,
                    status,
                    estimated_tokens,
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
        message = self.get_message(message_id)
        assert message is not None
        return message

    def update_message(
        self,
        message_id: str,
        *,
        content: str,
        status: MessageStatus,
        estimated_tokens: int,
    ) -> MessageRecord:
        now = _now()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE messages
                SET content = ?, status = ?, estimated_tokens = ?, updated_at = ?
                WHERE id = ?
                """,
                (content, status, estimated_tokens, now, message_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"message not found: {message_id}")
            connection.execute(
                """
                UPDATE threads SET updated_at = ?
                WHERE id = (SELECT thread_id FROM messages WHERE id = ?)
                """,
                (now, message_id),
            )
        message = self.get_message(message_id)
        assert message is not None
        return message

    def get_message(self, message_id: str) -> MessageRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        return self._message_from_row(row) if row else None

    def list_messages(self, thread_id: str) -> list[MessageRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE thread_id = ?
                ORDER BY position ASC
                """,
                (thread_id,),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def update_summary(
        self,
        owner_id: str,
        thread_id: str,
        summary: str,
        summarized_through_position: int,
    ) -> ThreadSummary:
        now = _now()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE threads
                SET summary = ?, summarized_through_position = ?, updated_at = ?
                WHERE id = ? AND owner_id = ?
                """,
                (summary, summarized_through_position, now, thread_id, owner_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"thread not found: {thread_id}")
        thread = self.get_thread(owner_id, thread_id)
        assert thread is not None
        return thread

    @staticmethod
    def _thread_from_row(row: sqlite3.Row) -> ThreadSummary:
        return ThreadSummary(**dict(row))

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(**dict(row))
