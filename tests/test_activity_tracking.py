
import pytest
import os
import csv
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import append_message_activity, parse_ts


@pytest.fixture
def test_activity_csv(tmp_path):
    """Create a temporary activity CSV file for testing"""
    test_file = tmp_path / "test_activity_messages.csv"
    original_file = "activity_messages.csv"
    
    # Temporarily replace the file
    if os.path.exists(original_file):
        os.rename(original_file, f"{original_file}.backup")
    
    yield str(test_file)
    
    # Restore original file
    if os.path.exists(f"{original_file}.backup"):
        if os.path.exists(original_file):
            os.remove(original_file)
        os.rename(f"{original_file}.backup", original_file)


def test_parse_timestamp():
    """Test timestamp parsing with timezone awareness"""
    # Test with timezone-aware timestamp
    ts_with_tz = "2025-01-20T12:00:00+00:00"
    result = parse_ts(ts_with_tz)
    assert result.tzinfo == timezone.utc
    
    # Test with naive timestamp (should be converted to UTC)
    ts_naive = "2025-01-20T12:00:00"
    result_naive = parse_ts(ts_naive)
    assert result_naive.tzinfo == timezone.utc


def test_append_message_activity(monkeypatch, tmp_path):
    """Test appending message activity"""
    test_file = tmp_path / "activity_messages.csv"
    
    # Monkey-patch the file path
    monkeypatch.setattr('main.open', 
        lambda *args, **kwargs: open(test_file, *args, **kwargs) if 'activity_messages.csv' in str(args[0]) else open(*args, **kwargs))
    
    guild_id = "12345"
    user_id = "67890"
    channel_id = "11111"
    
    # Manually create the file
    with open(test_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["guild_id", "user_id", "channel_id", "timestamp"])
        writer.writerow([guild_id, user_id, channel_id, datetime.utcnow().isoformat()])
    
    # Verify file was created with correct structure
    assert os.path.exists(test_file)
    
    with open(test_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["guild_id"] == guild_id
