#!/usr/bin/env python3
"""
Hook handler for Cursor CLI events.
Called by hooks defined in ~/.cursor/hooks.json

Working CLI hooks:
- afterShellExecution
- afterMCPExecution  
- afterFileEdit

Receives JSON payload on stdin with:
- hook_event_name
- conversation_id
- workspace_roots
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from curlens.config import load_config
from curlens.db import get_summary_state, upsert_summary
from curlens.chat_store import find_chat_db_path, read_meta, list_json_blobs
from curlens.summarize import generate_summary, has_meaningful_messages, is_summary_actionable


def log_debug(config, message: str) -> None:
    """Log debug message if debug mode is enabled."""
    if not config.debug:
        return
    
    log_path = Path.home() / ".cursor" / "curlens" / "hook.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def main() -> None:
    """Main hook handler entry point."""
    if os.environ.get("CURLENS_SKIP_HOOKS") == "1":
        print(json.dumps({"continue": True}))
        return
    
    config = load_config()
    
    if not config.hooks_enabled:
        print(json.dumps({"continue": True}))
        return
    
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"continue": True}))
            return
        
        payload = json.loads(raw_input)
    except json.JSONDecodeError as e:
        log_debug(config, f"JSON decode error: {e}")
        print(json.dumps({"continue": True}))
        return
    
    event_name = payload.get("hook_event_name", "unknown")
    conversation_id = payload.get("conversation_id")
    workspace_roots = payload.get("workspace_roots", [])
    
    log_debug(config, f"Event: {event_name}, Conv: {conversation_id}, Roots: {workspace_roots}")
    
    if not conversation_id:
        log_debug(config, "No conversation_id, skipping")
        print(json.dumps({"continue": True}))
        return
    
    chat_directory = workspace_roots[0] if workspace_roots else None
    
    db_path = find_chat_db_path(conversation_id)
    if not db_path:
        # IDE chats or chats not yet persisted - skip silently
        log_debug(config, f"Chat DB not found for {conversation_id} - skipping (likely IDE)")
        print(json.dumps({"continue": True}))
        return
    
    meta = read_meta(db_path)
    chat_name = meta.get("name", "Unnamed") if meta else "Unnamed"
    
    # Skip "New Agent" chats created after Jan 2026 - these are typically curlens's
    # own summarization calls (cursor agent -p). Before Jan 2026, Cursor CLI named
    # all chats "New Agent" by default, so we process those.
    JAN_2026_MS = 1767205800000  # Jan 1, 2026 00:00:00 UTC in milliseconds
    created_at = meta.get("createdAt", 0) if meta else 0
    if chat_name == "New Agent" and created_at >= JAN_2026_MS:
        log_debug(config, f"Skipping 'New Agent' chat {conversation_id} (post-Jan-2026)")
        print(json.dumps({"continue": True}))
        return
    
    blobs = list_json_blobs(db_path)
    blob_ids = [blob_id for blob_id, _ in blobs]
    
    # Check if there are new blobs since last summary
    existing = get_summary_state(config.summary_db_path, conversation_id)
    existing_summary = None
    new_blob_ids = set()
    
    if existing:
        existing_ids = set(existing.get("blob_ids", []))
        current_ids = set(blob_ids)
        new_blob_ids = current_ids - existing_ids
        
        if not new_blob_ids:
            log_debug(config, f"No new blobs for {conversation_id} (total: {len(blob_ids)})")
            print(json.dumps({"continue": True}))
            return
        
        existing_summary = existing.get("summary_text")
        log_debug(config, f"Found {len(new_blob_ids)} new blobs for {conversation_id} (total: {len(blob_ids)})")
    else:
        log_debug(config, f"First summary for {conversation_id} with {len(blob_ids)} blobs")
    
    # Extract messages from NEW blobs only (for incremental update)
    if new_blob_ids:
        new_blobs = [(bid, bdata) for bid, bdata in blobs if bid in new_blob_ids]
        messages = _extract_messages(new_blobs)
    else:
        messages = _extract_messages(blobs)
    
    if not messages:
        log_debug(config, f"No messages found for {conversation_id}")
        print(json.dumps({"continue": True}))
        return
    
    if not has_meaningful_messages(messages):
        log_debug(config, f"No meaningful messages for {conversation_id}")
        print(json.dumps({"continue": True}))
        return
    
    summary = generate_summary(
        messages,
        model=config.summary_model,
        max_words=config.summary_max_words,
        existing_summary=existing_summary
    )
    
    if not is_summary_actionable(summary):
        log_debug(config, f"Summary not actionable for {conversation_id}")
        print(json.dumps({"continue": True}))
        return
    
    upsert_summary(
        db_path=config.summary_db_path,
        conversation_id=conversation_id,
        summary_text=summary,
        blob_ids=blob_ids,
        chat_name=chat_name,
        chat_directory=chat_directory,
    )
    
    log_debug(config, f"Summary created for {conversation_id}: {summary[:50]}...")
    
    print(json.dumps({"continue": True}))


def _extract_messages(blobs: list[tuple[str, dict]]) -> list[dict]:
    """Extract meaningful message content from blobs."""
    messages = []
    for _, blob_data in blobs:
        if not isinstance(blob_data, dict):
            continue
        
        role = blob_data.get("role")
        content = blob_data.get("content")
        
        if not role or not content:
            continue
        
        # Skip system messages - they contain model names and setup info
        if role == "system":
            continue
        
        # Extract text from content
        text = _extract_text_content(content)
        if not text or len(text.strip()) < 10:
            continue
        
        # For user messages, extract actual user query (skip metadata-only messages)
        if role == "user":
            user_query = _extract_user_query(text)
            if not user_query or len(user_query.strip()) < 10:
                continue
            text = user_query
        
        # Skip messages that are mostly system metadata (not actual content)
        if _is_mostly_metadata(text):
            continue
        
        messages.append({"role": role, "content": text[:2000]})
    
    return messages


def _is_mostly_metadata(text: str) -> bool:
    """Check if text is mostly system metadata rather than actual content."""
    # Only filter very short messages with metadata indicators
    if len(text) > 500:
        return False
    
    metadata_indicators = [
        "You are gpt-",
        "You are claude-",
        "You are running as",
        "interactive CLI coding agent",
        "Plan mode is active",
    ]
    
    text_lower = text.lower()
    for indicator in metadata_indicators:
        if indicator.lower() in text_lower:
            return True
    
    return False


def _extract_text_content(content) -> str:
    """Extract plain text from various content formats."""
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                # Skip reasoning blocks
                if item_type == "reasoning":
                    continue
                if item_type == "text":
                    text_parts.append(item.get("text", ""))
        return " ".join(text_parts)
    
    return ""


def _extract_user_query(text: str) -> str:
    """Extract the actual user query from message text."""
    import re
    
    # Look for <user_query> tags first - this is the actual user content
    match = re.search(r'<user_query>\s*(.*?)\s*</user_query>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Skip messages that are primarily metadata
    metadata_tags = ["<user_info>", "<rules>", "<system_reminder>", "<always_applied"]
    for tag in metadata_tags:
        if text.strip().startswith(tag):
            return ""
    
    # If text has system_reminder somewhere, skip that part
    if "<system_reminder>" in text:
        parts = text.split("</system_reminder>")
        if len(parts) > 1:
            remaining = parts[-1].strip()
            if remaining:
                return remaining
            return ""
    
    return text


if __name__ == "__main__":
    main()
