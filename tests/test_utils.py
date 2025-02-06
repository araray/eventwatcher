"""
Unit tests for the utils module.
"""

import time
import unittest
from queue import Queue

from eventwatcher.utils import spawn_periodic_worker, spawn_queue_worker


class TestThreadFactory(unittest.TestCase):
    def test_periodic_worker(self):
        """
        Test that the periodic worker calls the function periodically.
        """
        call_counter = [0]

        def worker_fn():
            call_counter[0] += 1

        # Spawn a periodic worker with a 0.5-second interval.
        worker = spawn_periodic_worker(worker_fn, 0.5)
        # Allow the worker to run for approximately 2 seconds.
        time.sleep(2)
        # Stop the worker and wait for it to finish.
        worker.stop()
        worker.join(timeout=1)
        # Expect at least 3 executions in 2 seconds.
        self.assertGreaterEqual(
            call_counter[0], 3, "Periodic worker did not execute enough times"
        )

    def test_queue_worker(self):
        """
        Test that the queue worker processes items from the queue.
        """
        processed_items = []

        def worker_fn(item):
            processed_items.append(item)

        q = Queue()
        # Spawn a queue worker with a short poll interval.
        worker = spawn_queue_worker(q, worker_fn, poll_interval=0.1)
        # Enqueue several items.
        for i in range(5):
            q.put(i)
        # Wait until all items have been processed.
        q.join()
        # Stop the worker and wait for it to finish.
        worker.stop()
        worker.join(timeout=1)
        self.assertEqual(
            processed_items,
            list(range(5)),
            "Queue worker did not process items correctly",
        )


if __name__ == "__main__":
    unittest.main()
