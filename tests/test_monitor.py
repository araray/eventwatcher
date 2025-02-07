"""
Tests for the EventWatcher monitor module using pytest.

This test suite covers:
- Sample collection
- File and directory comparison
- Event type detection
- Event triggering
- Monitor integration
"""

import os
import shutil
import time
from pathlib import Path

import pytest

from eventwatcher import db
from eventwatcher.monitor import (Monitor, collect_sample, compare_samples,
                                  get_event_type)


@pytest.fixture
def temp_dir(tmp_path):
    """Fixture to create a temporary directory structure."""
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()

    # Create some files
    (test_dir / "file1.txt").write_text("Initial content 1")
    (test_dir / "file2.txt").write_text("Initial content 2")

    # Create a subdirectory with files
    subdir = test_dir / "subdir"
    subdir.mkdir()
    (subdir / "subfile1.txt").write_text("Subdir content 1")

    yield test_dir
    # Cleanup happens automatically via tmp_path


@pytest.fixture
def watch_group(temp_dir):
    """Fixture to create a watch group configuration."""
    return {
        "name": "TestGroup",
        "watch_items": [str(temp_dir)],
        "sample_rate": 60,
        "max_samples": 2,
        "pattern": "ERROR",
        "max_depth": 3,
        "rules": [
            {
                "name": "ContentChanged",
                "condition": "True",  # Always evaluate for testing
                "severity": "INFO"
            },
            {
                "name": "DirectoryGrowth",
                "condition": (
                    "file.get('type') == 'directory' and "
                    "file.get('file_count', 0) > prev_file.get('file_count', 0)"
                ),
                "severity": "WARNING"
            }
        ]
    }


@pytest.fixture
def monitor_instance(temp_dir, watch_group, tmp_path):
    """Fixture to create a Monitor instance."""
    db_path = str(tmp_path / "test.db")
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Initialize database
    db.init_db(db_path)

    monitor = Monitor(watch_group, db_path, log_dir, log_level="DEBUG")
    return monitor


def test_compare_samples_new_file():
    """Test detection of new files."""
    sample1 = {
        "/path/file1": {
            "type": "file",
            "size": 100,
            "md5": "abc"
        },
        "/path/file2": {
            "type": "file",
            "size": 200,
            "md5": "def"
        }
    }
    sample2 = {
        "/path/file1": {
            "type": "file",
            "size": 100,
            "md5": "abc"
        }
    }

    diff = compare_samples(sample1, sample2)
    assert "/path/file2" in diff['new']
    assert not diff['removed']
    assert not diff['modified']


def test_compare_samples_removed_file():
    """Test detection of removed files."""
    sample1 = {
        "/path/file1": {
            "type": "file",
            "size": 100,
            "md5": "abc"
        }
    }
    sample2 = {
        "/path/file1": {
            "type": "file",
            "size": 100,
            "md5": "abc"
        },
        "/path/file2": {
            "type": "file",
            "size": 200,
            "md5": "def"
        }
    }

    diff = compare_samples(sample1, sample2)
    assert not diff['new']
    assert "/path/file2" in diff['removed']
    assert not diff['modified']


def test_compare_samples_directory_changes():
    """Test detection of directory changes."""
    sample1 = {
        "/path/dir": {
            "type": "directory",
            "file_count": 5,
            "dir_count": 2,
            "total_size": 1000
        }
    }
    sample2 = {
        "/path/dir": {
            "type": "directory",
            "file_count": 3,
            "dir_count": 2,
            "total_size": 800
        }
    }

    diff = compare_samples(sample1, sample2)
    assert not diff['new']
    assert not diff['removed']
    assert "/path/dir" in diff['modified']
    assert diff['modified']["/path/dir"]["file_count"]["old"] == 3
    assert diff['modified']["/path/dir"]["file_count"]["new"] == 5
    assert diff['modified']["/path/dir"]["total_size"]["old"] == 800
    assert diff['modified']["/path/dir]["total_size"]["new"] == 1000


def test_get_event_type_file_changes():
    """Test event type detection for file changes."""
    changes = {
        "size": {"old": 100, "new": 200},
        "md5": {"old": "abc", "new": "def"}
    }
    event_type = get_event_type(changes, "file")
    assert "size_changed" in event_type
    assert "content_changed" in event_type


def test_get_event_type_directory_changes():
    """Test event type detection for directory changes."""
    changes = {
        "file_count": {"old": 3, "new": 5},
        "total_size": {"old": 800, "new": 1000}
    }
    event_type = get_event_type(changes, "directory")
    assert "files_changed" in event_type
    assert "dir_size_changed" in event_type


def test_collect_sample_structure(temp_dir, watch_group):
    """Test that collect_sample properly captures directory structure."""
    sample, _ = collect_sample(watch_group, str(temp_dir))

    # Check main directory
    main_dir = str(temp_dir)
    assert main_dir in sample
    assert sample[main_dir]["type"] == "directory"
    assert sample[main_dir]["file_count"] == 2  # file1.txt and file2.txt
    assert sample[main_dir]["dir_count"] == 1   # subdir

    # Check files
    file1 = str(temp_dir / "file1.txt")
    assert file1 in sample
    assert sample[file1]["type"] == "file"
    assert "size" in sample[file1]
    assert "md5" in sample[file1]

    # Check subdirectory
    subdir = str(temp_dir / "subdir")
    assert subdir in sample
    assert sample[subdir]["type"] == "directory"
    assert sample[subdir]["file_count"] == 1  # subfile1.txt


@pytest.mark.parametrize("change_type", [
    "file_content",
    "add_file",
    "remove_file",
    "add_subdir",
    "pattern_change"
])
def test_monitor_change_detection(monitor_instance, temp_dir, change_type):
    """Test various types of changes are properly detected."""
    # First run to establish baseline
    monitor_instance.run_once()

    # Make the specified change
    if change_type == "file_content":
        (temp_dir / "file1.txt").write_text("Modified content")
    elif change_type == "add_file":
        (temp_dir / "newfile.txt").write_text("New content")
    elif change_type == "remove_file":
        (temp_dir / "file2.txt").unlink()
    elif change_type == "add_subdir":
        new_subdir = temp_dir / "new_subdir"
        new_subdir.mkdir()
        (new_subdir / "subfile.txt").write_text("Content")
    elif change_type == "pattern_change":
        (temp_dir / "file1.txt").write_text("An ERROR occurred")

    # Allow filesystem events to propagate
    time.sleep(1)

    # Second run to detect changes
    sample, events = monitor_instance.run_once()

    # Verify appropriate events were generated
    assert events, f"No events generated for {change_type}"

    if change_type == "file_content":
        assert any("content" in e["event_type"].lower() for e in events)
    elif change_type == "add_file":
        assert any("created" in e["event_type"].lower() for e in events)
    elif change_type == "remove_file":
        assert any("removed" in e["event_type"].lower() for e in events)
    elif change_type == "add_subdir":
        assert any(
            "files_changed" in e["event_type"].lower() or
            "subdirs_changed" in e["event_type"].lower()
            for e in events
        )
    elif change_type == "pattern_change":
        assert any("pattern_found" in e["event_type"].lower() for e in events)


def test_monitor_multiple_changes(monitor_instance, temp_dir):
    """Test handling of multiple simultaneous changes."""
    # First run to establish baseline
    monitor_instance.run_once()

    # Make multiple changes
    (temp_dir / "file1.txt").write_text("Modified content")
    (temp_dir / "newfile.txt").write_text("New content")
    (temp_dir / "file2.txt").unlink()

    time.sleep(1)

    # Second run to detect changes
    sample, events = monitor_instance.run_once()

    # Verify all changes were detected
    event_types = [e["event_type"] for e in events]
    assert any("content" in et.lower() for et in event_types)
    assert any("created" in et.lower() for et in event_types)
    assert any("removed" in et.lower() for et in event_types)

    # Verify only changed files triggered events
    affected_files = [e["affected_file"] for e in events]
    assert str(temp_dir / "file1.txt") in affected_files
    assert str(temp_dir / "newfile.txt") in affected_files
    assert str(temp_dir / "file2.txt") in affected_files


def test_directory_explosion_depth(monitor_instance, temp_dir):
    """Test that directory scanning respects max_depth."""
    # Create a deep directory structure
    current = temp_dir
    for i in range(5):  # Beyond max_depth of 3
        current = current / f"level_{i}"
        current.mkdir()
        (current / "file.txt").write_text(f"Content level {i}")

    sample, _ = monitor_instance.run_once()

    # Count directory levels in sample
    dirs = [p for p in sample if sample[p]["type"] == "directory"]
    max_depth = max(str(p).count("level_") for p in map(Path, dirs))

    assert max_depth == 3  # Matches watch_group max_depth
