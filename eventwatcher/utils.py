"""
This module provides utility functions to create worker threads using a factory pattern.
It includes two types of workers:

1. PeriodicWorker: Executes a given function periodically (every X seconds).
2. QueueWorker: Waits for items on a Queue and processes each item using a worker function.

Both worker threads run in an infinite loop until a stop signal is set.
"""

import threading
import time
import logging
from queue import Empty

# Configure logging for debug output
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")


class PeriodicWorker(threading.Thread):
    """
    A thread that runs a worker function periodically every `interval` seconds.
    """

    def __init__(self, worker_fn, interval, *args, **kwargs):
        """
        Initialize the periodic worker thread.

        Args:
            worker_fn (callable): The function to run periodically.
            interval (float): Time in seconds between each call.
            *args: Positional arguments passed to worker_fn.
            **kwargs: Keyword arguments passed to worker_fn.
        """
        super(PeriodicWorker, self).__init__()
        self.worker_fn = worker_fn
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.stop_event = threading.Event()
        self.daemon = True  # Runs as a daemon thread so it will exit when the main program exits.

    def run(self):
        """
        Run the worker function periodically until a stop signal is received.
        """
        logging.debug("PeriodicWorker started with interval: %s seconds", self.interval)
        while not self.stop_event.is_set():
            try:
                logging.debug("PeriodicWorker: Executing worker function.")
                self.worker_fn(*self.args, **self.kwargs)
            except Exception as e:
                logging.exception("Exception in periodic worker function: %s", e)
            # Wait for the specified interval, but exit early if stop_event is set.
            if self.stop_event.wait(self.interval):
                break
        logging.debug("PeriodicWorker stopped.")

    def stop(self):
        """
        Signal the thread to stop.
        """
        logging.debug("PeriodicWorker received stop signal.")
        self.stop_event.set()


class QueueWorker(threading.Thread):
    """
    A thread that waits for items on a queue and processes them using a worker function.
    """

    def __init__(self, queue, worker_fn, poll_interval=1.0, *args, **kwargs):
        """
        Initialize the queue worker thread.

        Args:
            queue (Queue): The queue to get items from.
            worker_fn (callable): The function to process items.
                This function should expect the queue item as its first parameter.
            poll_interval (float): Time in seconds to wait (timeout) for an item.
            *args: Additional positional arguments passed to worker_fn.
            **kwargs: Additional keyword arguments passed to worker_fn.
        """
        super(QueueWorker, self).__init__()
        self.queue = queue
        self.worker_fn = worker_fn
        self.args = args
        self.kwargs = kwargs
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()
        self.daemon = True  # Daemon thread to ensure it exits with the main program.

    def run(self):
        """
        Continuously poll the queue for new items and process them.
        """
        logging.debug("QueueWorker started with poll interval: %s seconds", self.poll_interval)
        while not self.stop_event.is_set():
            try:
                # Attempt to retrieve an item from the queue; wait for poll_interval seconds.
                item = self.queue.get(timeout=self.poll_interval)
                logging.debug("QueueWorker: Processing item from queue: %s", item)
                try:
                    self.worker_fn(item, *self.args, **self.kwargs)
                except Exception as e:
                    logging.exception("Exception in processing item %s: %s", item, e)
                finally:
                    # Mark the task as done.
                    self.queue.task_done()
            except Empty:
                # No item received within the poll interval; check stop_event and continue.
                continue
        logging.debug("QueueWorker stopped.")

    def stop(self):
        """
        Signal the thread to stop.
        """
        logging.debug("QueueWorker received stop signal.")
        self.stop_event.set()


def spawn_periodic_worker(worker_fn, interval, *args, **kwargs):
    """
    Factory function to spawn a periodic worker thread.

    Args:
        worker_fn (callable): Function to execute periodically.
        interval (float): Time interval in seconds between executions.
        *args: Positional arguments for worker_fn.
        **kwargs: Keyword arguments for worker_fn.

    Returns:
        PeriodicWorker: The running periodic worker thread instance.
    """
    worker = PeriodicWorker(worker_fn, interval, *args, **kwargs)
    worker.start()
    logging.debug("spawn_periodic_worker: Started a new PeriodicWorker thread.")
    return worker


def spawn_queue_worker(queue, worker_fn, poll_interval=1.0, *args, **kwargs):
    """
    Factory function to spawn a queue worker thread.

    Args:
        queue (Queue): Queue instance to monitor.
        worker_fn (callable): Function to process queue items.
            The function should accept the queue item as its first parameter.
        poll_interval (float): Time interval to poll the queue for items.
        *args: Positional arguments for worker_fn.
        **kwargs: Keyword arguments for worker_fn.

    Returns:
        QueueWorker: The running queue worker thread instance.
    """
    worker = QueueWorker(queue, worker_fn, poll_interval, *args, **kwargs)
    worker.start()
    logging.debug("spawn_queue_worker: Started a new QueueWorker thread.")
    return worker
