import os
import tempfile
import pytest
from eventwatcher import monitor
import time

def create_temp_file(tmp_path, content="Hello World"):
    file_path = tmp_path / "test.txt"
    with open(file_path, "w") as f:
        f.write(content)
    return str(file_path)

@pytest.fixture
def temp_watch_group(tmp_path):
    # Create a temporary watch group configuration.
    temp_dir = tmp_path
    file_path = create_temp_file(temp_dir, "Sample Content")
    return {
        "name": "TestGroup",
        "watch_items": [file_path],
        "sample_rate": 60,
        "max_samples": 1,
        "max_depth": None,
        "pattern": "Sample",
        "rules": [
            {
                "name": "PatternFound",
                "condition": "data.get('" + file_path + "', {}).get('pattern_found', False)"
            }
        ]
    }

def test_collect_sample(tmp_path):
    # Test collecting sample for a file.
    file_path = create_temp_file(tmp_path, "Test Content with ERROR")
    sample = monitor.collect_sample(str(file_path), pattern="ERROR")
    assert file_path in sample
    assert sample[file_path].get("size") > 0
    assert "md5" in sample[file_path]
    # Check if the pattern is found.
    assert sample[file_path].get("pattern_found") == True

def test_monitor_run_once(temp_watch_group, tmp_path):
    # Create a temporary database file.
    db_path = str(tmp_path / "test.db")
    from eventwatcher import db as db_module
    db_module.init_db(db_path)

    m = monitor.Monitor(temp_watch_group, db_path, log_func=lambda x: None)
    sample, events = m.run_once()
    # Verify that the sample contains our file and the event is triggered.
    assert events == ["PatternFound"]
