"""Backfill existing cursor chats into summary database."""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

from .config import load_config, CurlensConfig
from .db import get_summary_state, upsert_summary
from .chat_store import read_meta, list_json_blobs
from .summarize import generate_summary, has_meaningful_messages, is_summary_actionable
from .hooks.session_end import _extract_messages


def build_path_mapping() -> dict[str, str]:
    """Map MD5 hash -> workspace path from projects folder.
    
    Projects folder names like 'Users-john-workspace-myproject'
    encode paths as '/Users/john/workspace/myproject'.
    The chats folder uses MD5(path) as folder names.
    
    Validates that the decoded path actually exists on disk.
    """
    mapping = {}
    projects_dir = Path.home() / ".cursor" / "projects"
    
    if not projects_dir.exists():
        return mapping
    
    for folder in projects_dir.iterdir():
        if not folder.is_dir():
            continue
        
        name = folder.name
        if not name.startswith("Users-"):
            continue
        
        # Try to find valid path by checking if it exists
        resolved_path = _resolve_folder_name_to_path(name)
        if resolved_path:
            path_hash = hashlib.md5(resolved_path.encode()).hexdigest()
            mapping[path_hash] = resolved_path
    
    return mapping


def _resolve_folder_name_to_path(folder_name: str) -> Optional[str]:
    """Resolve folder name to actual path by checking existence.
    
    Folder name uses '-' as separator which is ambiguous.
    Try different interpretations and return the one that exists.
    """
    # Simple case: replace all '-' with '/'
    simple_path = "/" + folder_name.replace("-", "/")
    if os.path.isdir(simple_path):
        return simple_path
    
    # Try progressively: build path segment by segment
    parts = folder_name.split("-")
    
    # Start with /Users (most common)
    if parts[0] == "Users" and len(parts) > 1:
        current = "/Users"
        remaining = parts[1:]
        
        result = _build_path_segments(current, remaining)
        if result:
            return result
    
    return None


def _build_path_segments(base: str, remaining_parts: list[str]) -> Optional[str]:
    """Recursively build path by trying different segment combinations."""
    if not remaining_parts:
        return base if os.path.isdir(base) else None
    
    # Try combining 1, 2, 3... parts as single segment
    for i in range(1, len(remaining_parts) + 1):
        segment = "-".join(remaining_parts[:i])
        candidate = os.path.join(base, segment)
        
        if os.path.isdir(candidate):
            if i == len(remaining_parts):
                return candidate
            result = _build_path_segments(candidate, remaining_parts[i:])
            if result:
                return result
    
    return None


def discover_all_chats(path_mapping: dict[str, str]) -> list[tuple[str, Optional[str], Path]]:
    """Find all chats: (conversation_id, workspace_path, store_db_path).
    
    Iterates ~/.cursor/chats/<hash>/<conversation_id>/store.db
    and maps the hash folder to workspace path.
    """
    chats = []
    chats_dir = Path.home() / ".cursor" / "chats"
    
    if not chats_dir.exists():
        return chats
    
    for hash_dir in chats_dir.iterdir():
        if not hash_dir.is_dir():
            continue
        
        hash_name = hash_dir.name
        workspace_path = path_mapping.get(hash_name)
        
        for conv_dir in hash_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            
            store_db = conv_dir / "store.db"
            if store_db.exists():
                conversation_id = conv_dir.name
                chats.append((conversation_id, workspace_path, store_db))
    
    return chats


def backfill_summaries(
    dry_run: bool = False,
    limit: Optional[int] = None,
    delay: float = 0.0
) -> dict:
    """Main backfill function.
    
    Args:
        dry_run: If True, only show what would be processed
        limit: Maximum number of chats to process
        delay: Delay between LLM calls in seconds
    
    Returns:
        Stats dict with processed/skipped/failed counts
    """
    config = load_config()
    
    print("Building path mapping...")
    path_mapping = build_path_mapping()
    print(f"  Found {len(path_mapping)} workspace paths")
    
    print("Discovering chats...")
    all_chats = discover_all_chats(path_mapping)
    print(f"  Found {len(all_chats)} total chats")
    
    stats = {
        "total": len(all_chats),
        "processed": 0,
        "skipped_exists": 0,
        "skipped_no_messages": 0,
        "skipped_not_meaningful": 0,
        "skipped_not_actionable": 0,
        "failed": 0,
    }
    
    to_process = []
    skipped_unknown_path = 0
    for conv_id, workspace_path, store_db in all_chats:
        if not workspace_path:
            skipped_unknown_path += 1
            continue
        existing = get_summary_state(config.summary_db_path, conv_id)
        if existing:
            stats["skipped_exists"] += 1
            continue
        to_process.append((conv_id, workspace_path, store_db))
    
    print(f"  {len(to_process)} chats need processing ({stats['skipped_exists']} already exist, {skipped_unknown_path} skipped unknown path)")
    
    if limit:
        to_process = to_process[:limit]
        print(f"  Limited to {limit} chats")
    
    if dry_run:
        print(f"\n[DRY RUN] Would process {len(to_process)} chats:")
        for i, (conv_id, workspace_path, _) in enumerate(to_process[:20], 1):
            print(f"  {i}. {conv_id[:12]}... - {workspace_path or 'Unknown path'}")
        if len(to_process) > 20:
            print(f"  ... and {len(to_process) - 20} more")
        return stats
    
    result_map = {
        "success": ("processed", "OK"),
        "no_messages": ("skipped_no_messages", "skipped (no messages)"),
        "not_meaningful": ("skipped_not_meaningful", "skipped (not meaningful)"),
        "not_actionable": ("skipped_not_actionable", "skipped (not actionable)"),
    }
    
    print(f"\nProcessing {len(to_process)} chats...")
    
    for i, (conv_id, workspace_path, store_db) in enumerate(to_process, 1):
        try:
            result, name = _process_single_chat(config, conv_id, workspace_path, store_db)
            
            stat_key, message = result_map.get(result, ("failed", "unknown"))
            stats[stat_key] += 1
            print(f"  [{i}/{len(to_process)}] {name[:30]} - {message}")
            
            if result == "success" and i < len(to_process):
                time.sleep(delay)
                
        except Exception as e:
            stats["failed"] += 1
            print(f"  [{i}/{len(to_process)}] {conv_id[:8]}... - FAILED: {e}")
    
    print(f"\nBackfill complete:")
    print(f"  Processed: {stats['processed']}")
    print(f"  Skipped (already exist): {stats['skipped_exists']}")
    print(f"  Skipped (no messages): {stats['skipped_no_messages']}")
    print(f"  Skipped (not meaningful): {stats['skipped_not_meaningful']}")
    print(f"  Skipped (not actionable): {stats['skipped_not_actionable']}")
    print(f"  Failed: {stats['failed']}")
    
    return stats


def _process_single_chat(
    config: CurlensConfig,
    conversation_id: str,
    workspace_path: Optional[str],
    store_db: Path
) -> tuple[str, str]:
    """Process a single chat and return (result_status, chat_name)."""
    meta = read_meta(store_db)
    chat_name = meta.get("name", "Unnamed") if meta else "Unnamed"
    
    blobs = list_json_blobs(store_db)
    blob_ids = [blob_id for blob_id, _ in blobs]
    
    messages = _extract_messages(blobs)
    
    if not messages:
        return "no_messages", chat_name
    
    if not has_meaningful_messages(messages):
        return "not_meaningful", chat_name
    
    summary = generate_summary(
        messages,
        model=config.summary_model,
        max_words=config.summary_max_words
    )
    
    if not is_summary_actionable(summary):
        return "not_actionable", chat_name
    
    upsert_summary(
        db_path=config.summary_db_path,
        conversation_id=conversation_id,
        summary_text=summary,
        blob_ids=blob_ids,
        chat_name=chat_name,
        chat_directory=workspace_path,
    )
    
    return "success", chat_name
