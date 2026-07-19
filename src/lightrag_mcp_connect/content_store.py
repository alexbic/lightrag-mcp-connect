"""Durable source-text mirror for safe append operations."""

import asyncio
import hashlib
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import fcntl


class DocumentContentStore:
    """Persist exact source text for documents managed through this MCP server."""

    def __init__(self, database_path: Optional[str] = None) -> None:
        configured = database_path or os.getenv("LIGHTRAG_MCP_CONTENT_DB")
        self.path = (
            Path(configured).expanduser()
            if configured
            else (Path.home() / ".local/share/lightrag-mcp-connect/content.sqlite3")
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS document_content (
                filename TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        return connection

    def get(self, filename: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content FROM document_content WHERE filename = ?", (filename,)
            ).fetchone()
        return row[0] if row else None

    def put(self, filename: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_content(filename, content, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET
                    content = excluded.content,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (filename, content),
            )

    def delete(self, filename: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM document_content WHERE filename = ?", (filename,)
            )

    @asynccontextmanager
    async def lock(self, filename: str) -> AsyncIterator[None]:
        """Serialize mutations across stateless MCP child processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()
        lock_path = self.path.parent / f".{digest}.lock"
        handle = lock_path.open("a+")
        try:
            await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
