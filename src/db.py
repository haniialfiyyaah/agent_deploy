from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import APP_DB, TELEMETRY_DB


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def create_app_schema(path: Path = APP_DB) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY,
                segment TEXT NOT NULL,
                authenticated INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            );
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            );
            CREATE TABLE IF NOT EXISTS kb_documents (
                document_id TEXT NOT NULL,
                kb_version TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                effective_date TEXT NOT NULL,
                status TEXT NOT NULL,
                source_path TEXT NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY(document_id, kb_version)
            );
            CREATE TABLE IF NOT EXISTS kb_chunks (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL UNIQUE,
                document_id TEXT NOT NULL,
                kb_version TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                kb_version UNINDEXED,
                title,
                category,
                content,
                tokenize='porter unicode61'
            );
            """
        )


def create_telemetry_schema(path: Path = TELEMETRY_DB) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                profile TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                kb_version TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                category TEXT NOT NULL,
                customer_segment TEXT NOT NULL,
                outcome TEXT NOT NULL,
                output TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS trace_spans (
                span_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                parent_span_id TEXT,
                span_type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                input_summary TEXT NOT NULL,
                output_summary TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES agent_runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS retrieval_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                query TEXT NOT NULL,
                kb_version TEXT NOT NULL,
                chunk_ids TEXT NOT NULL,
                document_ids TEXT NOT NULL,
                scores TEXT NOT NULL,
                expected_document_ids TEXT NOT NULL,
                hit_at_3 REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES agent_runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                sanitized_arguments TEXT NOT NULL,
                status TEXT NOT NULL,
                authorized INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES agent_runs(run_id)
            );
            """
        )


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
