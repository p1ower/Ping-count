
import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path, monkeypatch):
    """Setup test environment for all tests"""
    # Use temporary directory for test files
    monkeypatch.chdir(tmp_path)
    
    # Create necessary directories
    os.makedirs("data/reactions/stats", exist_ok=True)
    os.makedirs("data/reactions/configs", exist_ok=True)
    
    yield
    
    # Cleanup happens automatically with tmp_path
