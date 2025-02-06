"""
This module provides a ThreadManager class that manages worker threads.
It is designed to work with threads (such as those created by thread_factory.py)
that implement a cooperative stop mechanism via a stop() method.

Features:
- Register and unregister threads.
- Query the status of individual threads or all registered threads.
- Stop threads by calling their stop() method.
- Join threads (wait for them to finish).
- Stop and join all threads at once.

Note:
    In Python, threads cannot be forcefully killed. Instead, a cooperative
    cancellation pattern is used (i.e. each thread must check for a stop signal).
"""

import logging
import threading

# Configure logging for debug output
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")


class ThreadManager:
    """
    A class to manage worker threads.

    Attributes:
        threads (list): A list to keep track of the registered threads.
    """

    def __init__(self):
        """Initialize the ThreadManager with an empty list of threads."""
        self.threads = []

    def register_thread(self, thread):
        """
        Register a thread with the manager.

        Args:
            thread (threading.Thread): The thread to register.

        Raises:
            ValueError: If the thread is not an instance of threading.Thread.
        """
        if not isinstance(thread, threading.Thread):
            raise ValueError("Only threading.Thread instances can be registered.")
        self.threads.append(thread)
        logging.debug("Registered thread: %s", thread.name)

    def unregister_thread(self, thread):
        """
        Unregister a thread from the manager.

        Args:
            thread (threading.Thread): The thread to unregister.
        """
        if thread in self.threads:
            self.threads.remove(thread)
            logging.debug("Unregistered thread: %s", thread.name)

    def get_status(self, thread):
        """
        Get the status of a specific thread.

        Args:
            thread (threading.Thread): The thread whose status is to be checked.

        Returns:
            dict: A dictionary with thread information:
                - name (str): The thread's name
                - is_alive (bool): Whether the thread is still running
                - daemon (bool): Whether the thread is a daemon
                - id (int): Thread identifier
        """
        return {
            'name': str(thread.name),
            'is_alive': bool(thread.is_alive()),
            'daemon': bool(thread.daemon),
            'id': thread.ident
        }

    def get_all_statuses(self):
        """
        Get statuses for all registered threads.

        Returns:
            dict: A dictionary where keys are thread names and values are status dictionaries.
                 All values are guaranteed to be JSON-serializable.
        """
        return {str(thread.name): self.get_status(thread) for thread in self.threads}

    def stop_all(self):
        """
        Stop all registered threads by calling their stop() method if available.
        Threads that do not implement a stop() method will be skipped with a warning.
        """
        for thread in self.threads:
            if hasattr(thread, 'stop') and callable(thread.stop):
                logging.debug("Stopping thread: %s", thread.name)
                thread.stop()
            else:
                logging.warning("Thread %s does not have a stop() method.", thread.name)

    def join_all(self, timeout=None):
        """
        Join (wait for) all registered threads.

        Args:
            timeout (float, optional): Timeout in seconds to wait for each thread.
        """
        for thread in self.threads:
            logging.debug("Joining thread: %s", thread.name)
            thread.join(timeout)

    def stop_and_join_all(self, timeout=None):
        """
        Stop all threads and then join them.

        Args:
            timeout (float, optional): Timeout in seconds to wait for each thread.
        """
        self.stop_all()
        self.join_all(timeout)

    def clear_finished(self):
        """
        Remove threads that have finished running from the manager.
        """
        initial_count = len(self.threads)
        self.threads = [thread for thread in self.threads if thread.is_alive()]
        logging.debug("Cleared finished threads. %d removed, %d remaining.",
                      initial_count - len(self.threads), len(self.threads))
