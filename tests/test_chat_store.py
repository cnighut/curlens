"""Tests for chat_store module using example/store.db."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from curlens.chat_store import read_meta, list_json_blobs

EXAMPLE_DB = Path(__file__).parent.parent / "example" / "store.db"


def test_example_db_exists():
    """Verify example DB exists."""
    assert EXAMPLE_DB.exists(), f"Example DB not found at {EXAMPLE_DB}"


def test_read_meta():
    """Test reading meta from example DB."""
    meta = read_meta(EXAMPLE_DB)
    
    assert meta is not None, "Meta should not be None"
    assert "agentId" in meta, "Meta should have agentId"
    assert "name" in meta, "Meta should have name"
    assert "createdAt" in meta, "Meta should have createdAt"
    
    print(f"Chat name: {meta.get('name')}")
    print(f"Agent ID: {meta.get('agentId')}")


def test_list_json_blobs():
    """Test listing JSON blobs from example DB."""
    blobs = list_json_blobs(EXAMPLE_DB)
    
    assert len(blobs) > 0, "Should have at least some JSON blobs"
    
    # Check structure
    for blob_id, blob_data in blobs[:5]:
        assert isinstance(blob_id, str), "Blob ID should be string"
        assert isinstance(blob_data, dict), "Blob data should be dict"
    
    print(f"Found {len(blobs)} JSON blobs")
    
    # Count message types
    roles = {}
    for _, blob_data in blobs:
        role = blob_data.get("role")
        if role:
            roles[role] = roles.get(role, 0) + 1
    
    print(f"Roles: {roles}")


def test_json_blobs_have_messages():
    """Test that blobs contain actual message content."""
    blobs = list_json_blobs(EXAMPLE_DB)
    
    messages_with_content = 0
    for _, blob_data in blobs:
        if blob_data.get("role") and blob_data.get("content"):
            messages_with_content += 1
    
    assert messages_with_content > 0, "Should have messages with content"
    print(f"Messages with content: {messages_with_content}")


if __name__ == "__main__":
    test_example_db_exists()
    test_read_meta()
    test_list_json_blobs()
    test_json_blobs_have_messages()
    print("\nAll tests passed!")
