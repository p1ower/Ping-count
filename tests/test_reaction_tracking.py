
import pytest
import os
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    ensure_reaction_json_exists,
    append_spoiler_reaction_json,
    read_reaction_json,
    load_reaction_stats,
    save_reaction_stats,
    record_reaction
)


@pytest.fixture
def test_guild_id():
    """Provide a test guild ID"""
    return "test_guild_999"


@pytest.fixture
def cleanup_test_files(test_guild_id):
    """Clean up test files after tests"""
    yield
    # Cleanup after test
    stats_path = f"data/reactions/stats/{test_guild_id}.json"
    if os.path.exists(stats_path):
        os.remove(stats_path)


def test_ensure_reaction_json_exists(test_guild_id, cleanup_test_files):
    """Test reaction JSON file creation"""
    ensure_reaction_json_exists(test_guild_id)
    
    path = f"data/reactions/stats/{test_guild_id}.json"
    assert os.path.exists(path)
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        assert "reactions" in data
        assert data["reactions"] == []


def test_append_spoiler_reaction(test_guild_id, cleanup_test_files):
    """Test appending a spoiler reaction"""
    message_id = "msg123"
    user_id = "user456"
    emoji = "😂"
    
    append_spoiler_reaction_json(test_guild_id, message_id, user_id, emoji)
    
    reactions = read_reaction_json(test_guild_id)
    assert len(reactions) == 1
    assert reactions[0]["message_id"] == str(message_id)
    assert reactions[0]["user_id"] == str(user_id)
    assert reactions[0]["emoji"] == str(emoji)
    assert "timestamp" in reactions[0]


def test_record_reaction(test_guild_id, cleanup_test_files):
    """Test recording a reaction"""
    message_id = "msg789"
    user_id = "user012"
    emoji = "👍"
    
    record_reaction(test_guild_id, message_id, user_id, emoji)
    
    stats = load_reaction_stats(test_guild_id)
    assert len(stats["reactions"]) == 1
    assert stats["reactions"][0]["message_id"] == str(message_id)
    assert stats["reactions"][0]["user_id"] == str(user_id)
    assert stats["reactions"][0]["emoji"] == emoji


def test_multiple_reactions(test_guild_id, cleanup_test_files):
    """Test recording multiple reactions"""
    for i in range(5):
        record_reaction(test_guild_id, f"msg{i}", f"user{i}", "🎉")
    
    stats = load_reaction_stats(test_guild_id)
    assert len(stats["reactions"]) == 5
