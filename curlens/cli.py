"""Main CLI entry point for curlens."""

import argparse
import os
import subprocess
import sys
from typing import Optional

from .config import load_config
from .db import list_recent_summaries
from .search import rank_summaries


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Curlens - Search and resume Cursor chat sessions"
    )
    parser.add_argument(
        "--description", "-d",
        type=str,
        help="Description of what you're looking for"
    )
    parser.add_argument(
        "--smart", "-s",
        action="store_true",
        help="Use LLM for ranking (slower but smarter)"
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill summaries for all existing chats"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of chats to process during backfill"
    )
    
    args = parser.parse_args()
    
    # Handle backfill mode
    if args.backfill:
        from .backfill import backfill_summaries
        backfill_summaries(dry_run=args.dry_run, limit=args.limit)
        return
    
    # Search mode requires description
    if not args.description:
        parser.error("--description is required for search mode")
    
    config = load_config()
    
    summaries = list_recent_summaries(
        config.summary_db_path,
        days=config.search_window_days
    )
    
    if not summaries:
        print("No chat summaries found. Interact with some chats first.")
        sys.exit(0)
    
    ranked = rank_summaries(
        args.description,
        summaries,
        model=config.search_model,
        max_results=3,
        use_llm=args.smart
    )
    
    if not ranked:
        print("No relevant chats found for your description.")
        sys.exit(0)
    
    _print_results(ranked)
    selection = _prompt_selection(ranked)
    
    if selection:
        _resume_chat(selection)
    else:
        print("No chat selected.")


def _print_results(results: list[dict]) -> None:
    """Print results to console."""
    from datetime import datetime
    
    print(f"\nFound {len(results)} matching chat(s):\n")
    for idx, r in enumerate(results, start=1):
        name = r.get('chat_name', 'Unnamed')
        directory = r.get('chat_directory', 'Unknown')
        summary = r.get('summary_text', '')[:120]
        reason = r.get('reason', '')
        created_at = r.get('created_at', 0)
        
        # Format date from milliseconds timestamp
        date_str = "Unknown"
        if created_at:
            try:
                dt = datetime.fromtimestamp(created_at / 1000)
                date_str = dt.strftime("%b %d, %Y %H:%M")
            except (ValueError, OSError):
                pass
        
        print(f"[{idx}] {name}")
        print(f"    Dir: {directory}")
        print(f"    Time: {date_str}")
        print(f"    {summary}...")
        if reason:
            print(f"    Why: {reason}")
        print()


def _prompt_selection(results: list[dict]) -> Optional[dict]:
    """Prompt user to select a chat."""
    if len(results) == 1:
        confirm = input("Select this chat? [Y/n]: ").strip().lower()
        if confirm in ("", "y", "yes"):
            return results[0]
        return None
    
    try:
        choice = input("Select chat [1-{}] or q to quit: ".format(len(results))).strip()
        if choice.lower() == "q":
            return None
        idx = int(choice) - 1
        if 0 <= idx < len(results):
            return results[idx]
        print("Invalid selection.")
    except (ValueError, EOFError):
        pass
    return None


def _resume_chat(chat: dict) -> None:
    """Resume the selected chat."""
    conv_id = chat.get("conversation_id")
    directory = chat.get("chat_directory")
    
    if not conv_id:
        print("Error: No conversation ID found.")
        return
    
    print(f"\n→ Resuming: {chat.get('chat_name', conv_id)}")
    
    if directory and os.path.isdir(directory):
        os.chdir(directory)
        print(f"→ Directory: {directory}")
    
    cmd = ["cursor", "agent", "--resume", conv_id]
    
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        print("Error: 'cursor' command not found. Make sure Cursor CLI is installed.")
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
