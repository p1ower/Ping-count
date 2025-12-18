
import pytest
import os
import csv
from datetime import datetime, timezone, timedelta
from collections import Counter
import sys

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    ensure_csv_exists,
    append_ping,
    read_all_pings,
    write_all_pings,
    cleanup_old_entries,
    get_top_for_role,
    get_counts_for_user,
    reset_role_counts,
    reset_user_counts
)


@pytest.fixture
def test_csv_path(tmp_path):
    """Create a temporary CSV file for testing"""
    test_file = tmp_path / "test_role_pings.csv"
    # Patch the CSV_PATH in main module
    import main
    original_path = main.CSV_PATH
    main.CSV_PATH = str(test_file)
    yield str(test_file)
    main.CSV_PATH = original_path


def test_ensure_csv_exists(test_csv_path):
    """Test CSV file creation"""
    ensure_csv_exists()
    assert os.path.exists(test_csv_path)
    
    with open(test_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == ["guild_id", "role_id", "user_id", "channel_id", "timestamp"]


def test_append_ping(test_csv_path):
    """Test appending a ping to CSV"""
    ensure_csv_exists()
    
    guild_id = "123456"
    role_id = "789012"
    user_id = "345678"
    channel_id = "901234"
    
    append_ping(guild_id, role_id, user_id, channel_id)
    
    rows = read_all_pings()
    assert len(rows) == 1
    assert rows[0]["guild_id"] == guild_id
    assert rows[0]["role_id"] == role_id
    assert rows[0]["user_id"] == user_id
    assert rows[0]["channel_id"] == channel_id


def test_read_all_pings(test_csv_path):
    """Test reading all pings from CSV"""
    ensure_csv_exists()
    
    append_ping("111", "222", "333", "444")
    append_ping("555", "666", "777", "888")
    
    rows = read_all_pings()
    assert len(rows) == 2


def test_get_top_for_role(test_csv_path):
    """Test getting top users for a specific role"""
    ensure_csv_exists()
    
    guild_id = "1000"
    role_id = "2000"
    
    # User 1 pings 3 times
    for _ in range(3):
        append_ping(guild_id, role_id, "user1", "channel1")
    
    # User 2 pings 2 times
    for _ in range(2):
        append_ping(guild_id, role_id, "user2", "channel1")
    
    # User 3 pings 1 time
    append_ping(guild_id, role_id, "user3", "channel1")
    
    top_users = get_top_for_role(guild_id, role_id, limit=10)
    
    assert len(top_users) == 3
    assert top_users[0] == ("user1", 3)
    assert top_users[1] == ("user2", 2)
    assert top_users[2] == ("user3", 1)


def test_get_counts_for_user(test_csv_path):
    """Test getting role counts for a specific user"""
    ensure_csv_exists()
    
    guild_id = "1000"
    user_id = "user1"
    
    # User pings role1 twice
    for _ in range(2):
        append_ping(guild_id, "role1", user_id, "channel1")
    
    # User pings role2 once
    append_ping(guild_id, "role2", user_id, "channel1")
    
    counts = get_counts_for_user(guild_id, user_id)
    
    assert len(counts) == 2
    assert counts[0] == ("role1", 2)
    assert counts[1] == ("role2", 1)


def test_reset_role_counts(test_csv_path):
    """Test resetting counts for a specific role"""
    ensure_csv_exists()
    
    guild_id = "1000"
    role_id = "role1"
    
    append_ping(guild_id, role_id, "user1", "channel1")
    append_ping(guild_id, role_id, "user2", "channel1")
    append_ping(guild_id, "role2", "user1", "channel1")
    
    reset_role_counts(guild_id, role_id)
    
    rows = read_all_pings()
    assert len(rows) == 1
    assert rows[0]["role_id"] == "role2"


def test_reset_user_counts(test_csv_path):
    """Test resetting counts for a specific user"""
    ensure_csv_exists()
    
    guild_id = "1000"
    user_id = "user1"
    
    append_ping(guild_id, "role1", user_id, "channel1")
    append_ping(guild_id, "role2", user_id, "channel1")
    append_ping(guild_id, "role1", "user2", "channel1")
    
    reset_user_counts(guild_id, user_id)
    
    rows = read_all_pings()
    assert len(rows) == 1
    assert rows[0]["user_id"] == "user2"


def test_cleanup_old_entries(test_csv_path):
    """Test cleanup of old entries"""
    ensure_csv_exists()
    
    guild_id = "1000"
    
    # Add a recent entry
    append_ping(guild_id, "role1", "user1", "channel1")
    
    # Add an old entry manually
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    with open(test_csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([guild_id, "role2", "user2", "channel2", old_timestamp])
    
    cleanup_old_entries(days=30)
    
    rows = read_all_pings()
    assert len(rows) == 1
    assert rows[0]["role_id"] == "role1"
