"""Interface with Cursor's chat store.db files."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


def find_chat_db_path(conversation_id: str) -> Optional[Path]:
    """Find the store.db file for a given conversation ID.
    
    CLI chats are stored at: ~/.cursor/chats/<hash>/<conversation_id>/store.db
    """
    chats_dir = Path.home() / ".cursor" / "chats"
    
    if not chats_dir.exists():
        return None
    
    # Direct path lookup: ~/.cursor/chats/*/<conversation_id>/store.db
    for hash_dir in chats_dir.iterdir():
        if not hash_dir.is_dir():
            continue
        db_path = hash_dir / conversation_id / "store.db"
        if db_path.exists():
            return db_path
    
    return None


def read_meta(db_path: Path) -> Optional[dict[str, Any]]:
    """Read the meta table from a chat store.db file."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM meta WHERE key = '0'")
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            data = bytes.fromhex(row[0]) if isinstance(row[0], str) else row[0]
            return json.loads(data.decode("utf-8"))
    except (sqlite3.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        pass
    
    return None


def list_json_blobs(db_path: Path) -> list[tuple[str, dict]]:
    """List all JSON blobs from a chat store.db file.
    
    Uses efficient SQL filter: hex(substr(data,1,1)) = '7B' where 7B = '{'
    """
    results = []
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, CAST(data AS TEXT) AS json 
            FROM blobs 
            WHERE hex(substr(data,1,1)) = '7B'
        """)
        rows = cursor.fetchall()
        conn.close()
        
        for blob_id, json_text in rows:
            try:
                parsed = json.loads(json_text)
                results.append((blob_id, parsed))
            except (json.JSONDecodeError, TypeError):
                continue
    except sqlite3.Error:
        pass
    
    return results
