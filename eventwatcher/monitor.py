"""Tests for the improved monitor module."""

import os
import tempfile
import time
import unittest

from eventwatcher.monitor import Monitor, compare_samples, get_event_type


class TestMonitorComparison(unittest.TestCase):
    def test_compare_samples_new_file(self):
        """Test detection of new files."""
        sample1 = {
            "/path/file1": {"size": 100, "md5": "abc"},
            "/path/file2": {"size": 200, "md5": "def"}
        }
        sample2 = {
            "/path/file1": {"size": 100, "md5": "abc"}
        }

        diff = compare_samples(sample1, sample2)
        self.assertEqual(diff['new'], ["/path/file2"])
        self.assertEqual(diff['removed'], [])
        self.assertEqual(diff['modified'], {})

    def test_compare_samples_removed_file(self):
        """Test detection of removed files."""
        sample1 = {
            "/path/file1": {"size": 100, "md5": "abc"}
        }
        sample2 = {
            "/path/file1": {"size": 100, "md5": "abc"},
            "/path/file2": {"size": 200, "md5": "def"}
        }

        diff = compare_samples(sample1, sample2)
        self.assertEqual(diff['new'], [])
        self.assertEqual(diff['removed'], ["/path/file2"])
        self.assertEqual(diff['modified'], {})

    def test_compare_samples_modified_file(self):
        """Test detection of modified files."""
        sample1 = {
            "/path/file1": {"size": 150, "md5": "abc"}
        }
        sample2 = {
            "/path/file1": {"size": 100, "md5": "abc"}
        }

        diff = compare_samples(sample1, sample2)
        self.assertEqual(diff['new'], [])
        self.assertEqual(diff['removed'], [])
        self.assertTrue("/path/file1" in diff['modified'])
        self.assertEqual(
            diff['modified']["/path/file1"]["size"],
            {"old": 100, "new": 150}
        )

    def test_compare_samples_ignore_sample_epoch(self):
        """Test that sample_epoch is ignored in comparisons."""
        sample1 = {
            "/path/file1": {"size": 100, "md5": "abc", "sample_epoch": 1000}
        }
        sample2 = {
            "/path/file1": {"size": 100, "md5": "abc", "sample_epoch": 900}
        }

        diff = compare_samples(sample1, sample2)
        self.assertEqual(diff['new'], [])
        self.assertEqual(diff['removed'], [])
        self.assertEqual(diff['modified'], {})


class TestEventTypes(unittest.TestCase):
    def test_get_event_type_size_change(self):
        """Test event type detection for size changes."""
        changes = {
            "size": {"old": 100, "new": 200}
        }
        self.assertEqual(get_event_type(changes), "size_changed")

    def test_get_event_type_content_modification(self):
        """Test event type detection for content modifications."""
        changes = {
            "last_modified": {"old": 1000, "new": 1100}
        }
        self.assertEqual(get_event_type(changes), "content_modified")

    def test_get_event_type_multiple_changes(self):
        """Test event type detection for multiple changes."""
        changes = {
            "size": {"old": 100, "new": 200},
            "md5": {"old": "abc", "new": "def"}
        }
        self.assertEqual(
            get_event_type(changes),
            "content_changed,size_changed"
        )

    def test_get_event_type_pattern_changes(self):
        """Test event type detection for pattern changes."""
        changes = {
            "pattern_found": {"old": False, "new": True}
        }
        self.assertEqual(get_event_type(changes), "pattern_found")

        changes = {
            "pattern_found": {"old": True, "new": False}
        }
        self.assertEqual(get_event_type(changes), "pattern_removed")


class TestMonitorIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up temporary directory and files for testing."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_file = os.path.join(cls.temp_dir, "test.txt")
        with open(cls.test_file, "w") as f:
            f.write("Initial content")

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary files."""
        try:
            os.remove(cls.test_file)
            os.rmdir(cls.temp_dir)
        except:
            pass

    def setUp(self):
        """Set up a Monitor instance for each test."""
        self.watch_group = {
            "name": "TestGroup",
            "watch_items": [self.test_file],
            "sample_rate": 60,
            "max_samples": 2,
            "pattern": "ERROR",
            "rules": [
                {
                    "name": "ContentChanged",
                    "condition": "True",  # Always evaluate for testing
                    "severity": "INFO"
                }
            ]
        }
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.log_dir = os.path.join(self.temp_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        # Initialize database
        from eventwatcher.db import init_db
        init_db(self.db_path)

        self.monitor = Monitor(
            self.watch_group,
            self.db_path,
            self.log_dir,
            log_level="DEBUG"
        )

    def tearDown(self):
        """Clean up after each test."""
        try:
            os.remove(self.db_path)
            for f in os.listdir(self.log_dir):
                os.remove(os.path.join(self.log_dir, f))
            os.rmdir(self.log_dir)
        except:
            pass

    def test_initial_run(self):
        """Test initial monitoring run."""
        sample, events = self.monitor.run_once()

        # First run should have no events as there's no previous sample
        self.assertTrue(len(events) == 0)
        self.assertTrue(self.test_file in sample)
        self.assertTrue("size" in sample[self.test_file])
        self.assertTrue("md5" in sample[self.test_file])

    def test_content_modification(self):
        """Test detection of content modifications."""
        # First run to establish baseline
        self.monitor.run_once()

        # Modify file content
        time.sleep(1)  # Ensure timestamp change
        with open(self.test_file, "w") as f:
            f.write("Modified content")

        # Second run to detect changes
        sample, events = self.monitor.run_once()

        self.assertTrue(len(events) > 0)
        self.assertTrue(any(
            e["event_type"] in ("content_changed", "content_modified", "size_changed")
            for e in events
        ))

    def test_file_removal(self):
        """Test detection of file removal."""
        # First run to establish baseline
        self.monitor.run_once()

        # Remove the file
        os.remove(self.test_file)

        # Second run to detect removal
        sample, events = self.monitor.run_once()

        self.assertTrue(len(events) > 0)
        self.assertTrue(any(
            e["event_type"] == "removed"
            for e in events
        ))

    def test_pattern_detection(self):
        """Test pattern detection changes."""
        # First run to establish baseline
        self.monitor.run_once()

        # Add pattern to file
        with open(self.test_file, "w") as f:
            f.write("An ERROR occurred")

        # Second run to detect pattern
        sample, events = self.monitor.run_once()

        self.assertTrue(len(events) > 0)
        self.assertTrue(any(
            "pattern_found" in e["event_type"]
            for e in events
        ))


if __name__ == "__main__":
    unittest.main()
