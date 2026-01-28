"""Tests for hook message extraction using example/store.db."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from curlens.chat_store import list_json_blobs
from curlens.hooks.session_end import _extract_messages, _extract_text_content, _extract_user_query

EXAMPLE_DB = Path(__file__).parent.parent / "example" / "store.db"


def test_extract_messages():
    """Test message extraction filters metadata correctly."""
    blobs = list_json_blobs(EXAMPLE_DB)
    messages = _extract_messages(blobs)
    
    assert len(messages) > 0, "Should extract some messages"
    
    # Verify no system messages
    for msg in messages:
        assert msg["role"] != "system", "System messages should be filtered"
    
    # Verify content is extracted
    for msg in messages:
        assert len(msg["content"]) > 0, "Messages should have content"
    
    print(f"Extracted {len(messages)} messages from {len(blobs)} blobs")
    
    # Show sample
    for msg in messages[:3]:
        preview = msg["content"][:80].replace("\n", " ")
        print(f"  [{msg['role']}]: {preview}...")


def test_extract_text_content_string():
    """Test extracting text from string content."""
    text = _extract_text_content("Hello world")
    assert text == "Hello world"


def test_extract_text_content_list():
    """Test extracting text from array content."""
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "reasoning", "text": "thinking..."},  # Should be skipped
        {"type": "text", "text": "World"},
    ]
    text = _extract_text_content(content)
    assert "Hello" in text
    assert "World" in text
    assert "thinking" not in text


def test_extract_user_query_with_tags():
    """Test extracting user query from tagged content."""
    text = "<user_info>info</user_info><user_query>What is Python?</user_query>"
    query = _extract_user_query(text)
    assert query == "What is Python?"


def test_extract_user_query_skips_metadata():
    """Test that metadata-only messages return empty."""
    text = "<user_info>OS: macOS\nShell: zsh</user_info>"
    query = _extract_user_query(text)
    assert query == ""


def test_metadata_filtering():
    """Test that short metadata messages are filtered."""
    blobs = list_json_blobs(EXAMPLE_DB)
    messages = _extract_messages(blobs)
    
    # No message should start with model name indicators
    for msg in messages:
        content = msg["content"].lower()
        assert not content.startswith("you are gpt-"), "Should filter model metadata"
        assert not content.startswith("you are claude-"), "Should filter model metadata"
    
    print("Metadata filtering: OK")


if __name__ == "__main__":
    test_extract_messages()
    test_extract_text_content_string()
    test_extract_text_content_list()
    test_extract_user_query_with_tags()
    test_extract_user_query_skips_metadata()
    test_metadata_filtering()
    print("\nAll tests passed!")
