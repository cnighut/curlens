"""SQLite database operations for chat summaries."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

def ensure_db(db_path: str) -> None:
    """Create the summary database schema if needed.
    
    Checks if DB file exists with content - if so, skips schema creation.
    This avoids SQL overhead on every invocation.
    """
    db_file = Path(db_path)
    
    # If DB exists and has content, schema is already there
    if db_file.exists() and db_file.stat().st_size > 0:
        return
    
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            conversation_id TEXT PRIMARY KEY,
            summary_text TEXT NOT NULL,
            blob_ids_json TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            chat_name TEXT,
            chat_directory TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_updated ON summaries(updated_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_directory ON summaries(chat_directory)")
    
    conn.commit()
    conn.close()


def upsert_summary(
    db_path: str,
    conversation_id: str,
    summary_text: str,
    blob_ids: list[str],
    chat_name: Optional[str] = None,
    chat_directory: Optional[str] = None,
) -> None:
    """Insert or update a chat summary."""
    ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now = int(time.time() * 1000)
    blob_ids_json = json.dumps(blob_ids)
    
    cursor.execute("SELECT created_at FROM summaries WHERE conversation_id = ?", (conversation_id,))
    row = cursor.fetchone()
    created_at = row[0] if row else now
    
    cursor.execute("""
        INSERT INTO summaries (
            conversation_id, summary_text, blob_ids_json, created_at, updated_at,
            chat_name, chat_directory
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            summary_text = excluded.summary_text,
            blob_ids_json = excluded.blob_ids_json,
            updated_at = excluded.updated_at,
            chat_name = excluded.chat_name,
            chat_directory = excluded.chat_directory
    """, (
        conversation_id, summary_text, blob_ids_json, created_at, now,
        chat_name, chat_directory
    ))
    
    conn.commit()
    conn.close()


def get_summary_state(db_path: str, conversation_id: str) -> Optional[dict[str, Any]]:
    """Get stored summary state for a conversation."""
    ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT conversation_id, summary_text, blob_ids_json, created_at, updated_at,
               chat_name, chat_directory
        FROM summaries WHERE conversation_id = ?
    """, (conversation_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "conversation_id": row["conversation_id"],
        "summary_text": row["summary_text"],
        "blob_ids": json.loads(row["blob_ids_json"]) if row["blob_ids_json"] else [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "chat_name": row["chat_name"],
        "chat_directory": row["chat_directory"],
    }


def list_recent_summaries(db_path: str, days: int = 20) -> list[dict[str, Any]]:
    """List summaries updated within the last N days."""
    ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff = int((time.time() - days * 86400) * 1000)
    
    cursor.execute("""
        SELECT conversation_id, summary_text, created_at, updated_at,
               chat_name, chat_directory
        FROM summaries
        WHERE updated_at >= ?
        ORDER BY updated_at DESC
    """, (cutoff,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "conversation_id": row["conversation_id"],
            "summary_text": row["summary_text"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "chat_name": row["chat_name"],
            "chat_directory": row["chat_directory"],
        }
        for row in rows
    ]
