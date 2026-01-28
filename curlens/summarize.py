"""Summary generation using Cursor agent CLI."""

import json
import os
import re
import subprocess
from typing import Optional


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def truncate_to_words(text: str, max_words: int) -> str:
    """Truncate text to max words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def build_summary_prompt(messages: list[dict], max_words: int = 70, existing_summary: Optional[str] = None) -> str:
    """Build a prompt for summary generation."""
    trimmed = _trim_json_messages(messages, max_chars=6000)
    messages_json = json.dumps(trimmed, indent=2)
    
    if existing_summary:
        return f"""Update this chat summary with new messages. Max {max_words} words.

EXISTING SUMMARY:
{existing_summary}

NEW MESSAGES:
{messages_json}

Create an updated summary incorporating the new content. Focus on tasks, technologies, and outcomes.
Output ONLY the updated summary."""
    
    return f"""Summarize this coding chat in {max_words} words or less.

FOCUS ON:
- The specific task/problem the user wanted to solve
- Technologies, frameworks, or files involved
- Key outcomes or solutions implemented

DO NOT INCLUDE:
- Model names (gpt-5, claude, grok, etc.)
- System setup information
- Generic phrases like "user initiated a chat"

If the conversation has no meaningful coding task, respond with just: "No actionable content"

Output ONLY the summary, nothing else.

Messages:
{messages_json}"""


def _trim_json_messages(messages: list[dict], max_chars: int = 8000) -> list[dict]:
    """Trim messages to fit within character limit."""
    result = []
    total = 0
    
    for msg in messages:
        msg_str = json.dumps(msg)
        if total + len(msg_str) > max_chars:
            if msg.get("content") and len(msg.get("content", "")) > 200:
                trimmed_msg = {**msg, "content": msg["content"][:200] + "... [trimmed]"}
                result.append(trimmed_msg)
            break
        result.append(msg)
        total += len(msg_str)
    
    return result


def run_agent(prompt: str, model: str = "grok", timeout: int = 60) -> Optional[str]:
    """Run the Cursor agent CLI with a prompt and return the response."""
    env = os.environ.copy()
    env["CURLENS_SKIP_HOOKS"] = "1"
    
    try:
        result = subprocess.run(
            ["cursor", "agent", "-p", "--model", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return None


def generate_summary(
    messages: list[dict],
    model: str = "grok",
    max_words: int = 70,
    existing_summary: Optional[str] = None
) -> Optional[str]:
    """Generate or update a summary for the given messages."""
    if not messages:
        return None
    
    prompt = build_summary_prompt(messages, max_words, existing_summary)
    summary = run_agent(prompt, model)
    
    if summary and word_count(summary) > max_words:
        summary = truncate_to_words(summary, max_words)
    
    return summary


def is_summary_actionable(summary: Optional[str]) -> bool:
    """Check if a summary is meaningful and actionable."""
    if not summary:
        return False
    
    # Need at least 10 words for a meaningful summary
    if word_count(summary) < 10:
        return False
    
    # Need substantial alphabetic content
    alpha_chars = sum(1 for c in summary if c.isalpha())
    if alpha_chars < 50:
        return False
    
    lower = summary.lower()
    
    # Reject non-actionable markers from LLM
    reject_phrases = [
        "no actionable content",
        "no specific coding task",
        "no meaningful",
        "user initiated a chat",
        "user started a chat",
        "testing",
        "just saying",
        "no specific task",
        "empty conversation",
    ]
    for phrase in reject_phrases:
        if phrase in lower:
            return False
    
    return True


def has_meaningful_messages(messages: list[dict]) -> bool:
    """Check if messages contain meaningful content worth summarizing."""
    if not messages:
        return False
    
    # Need at least 1 message
    if len(messages) < 1:
        return False
    
    total_content = ""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_content += content
    
    # Skip curlens's own meta-chats (summarization requests)
    if is_curlens_meta_chat(total_content):
        return False
    
    # Need substantial content (at least 100 chars)
    if len(total_content) < 100:
        return False
    
    # Need meaningful alphabetic content
    alpha_chars = sum(1 for c in total_content if c.isalpha())
    if alpha_chars < 50:
        return False
    
    return True


def is_curlens_meta_chat(content: str) -> bool:
    """Detect if this is a curlens summarization request chat.
    
    When curlens runs 'cursor agent -p' to generate summaries,
    Cursor creates a chat entry for that interaction. We should
    skip these meta-chats during backfill/hooks.
    """
    meta_indicators = [
        "Summarize this coding chat in",
        "Update this chat summary with new messages",
        "rank these chat summaries",
        "Output ONLY the summary",
        "No actionable content",
    ]
    
    content_lower = content.lower()
    for indicator in meta_indicators:
        if indicator.lower() in content_lower:
            return True
    
    return False
