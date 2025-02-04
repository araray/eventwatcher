"""
Unit tests for the ThreadManager class in thread_manager.py.
"""
import time
import unittest

from eventwatcher.thread_manager import ThreadManager
from eventwatcher.utils import spawn_periodic_worker


class DummyWorker:
    """
    A dummy worker function that increments a counter.
    """
    def __init__(self):
        self.counter = 0

    def __call__(self):
        self.counter += 1
        # Sleep briefly to simulate work
        time.sleep(0.1)

class TestThreadManager(unittest.TestCase):
    def test_register_and_get_status(self):
        """
        Test that a thread can be registered and its status is reported correctly.
        """
        manager = ThreadManager()
        dummy = DummyWorker()
        worker = spawn_periodic_worker(dummy, 0.5)
        manager.register_thread(worker)

        # Check status immediately after registration.
        status = manager.get_status(worker)
        self.assertEqual(status['name'], worker.name)
        self.assertTrue(status['is_alive'], "Worker should be alive immediately after start.")

        # Stop the worker and wait for it to finish.
        worker.stop()
        worker.join(timeout=1)
        status = manager.get_status(worker)
        self.assertFalse(status['is_alive'], "Worker should not be alive after stopping.")
        manager.unregister_thread(worker)

    def test_stop_and_join_all(self):
        """
        Test that stop_and_join_all stops and joins all registered threads.
        """
        manager = ThreadManager()
        dummy1 = DummyWorker()
        dummy2 = DummyWorker()

        worker1 = spawn_periodic_worker(dummy1, 0.5)
        worker2 = spawn_periodic_worker(dummy2, 0.5)

        manager.register_thread(worker1)
        manager.register_thread(worker2)

        # Allow the threads to run for a short time.
        time.sleep(1)
        statuses_before = manager.get_all_statuses()
        self.assertTrue(statuses_before[worker1.name]['is_alive'])
        self.assertTrue(statuses_before[worker2.name]['is_alive'])

        manager.stop_and_join_all(timeout=1)
        statuses_after = manager.get_all_statuses()
        self.assertFalse(statuses_after[worker1.name]['is_alive'])
        self.assertFalse(statuses_after[worker2.name]['is_alive'])

    def test_clear_finished(self):
        """
        Test that clear_finished removes threads that have finished.
        """
        manager = ThreadManager()
        dummy = DummyWorker()
        worker = spawn_periodic_worker(dummy, 0.5)
        manager.register_thread(worker)

        # Stop and join the worker.
        worker.stop()
        worker.join(timeout=1)
        manager.clear_finished()
        self.assertEqual(len(manager.threads), 0, "Finished threads should be cleared.")

if __name__ == '__main__':
    unittest.main()
