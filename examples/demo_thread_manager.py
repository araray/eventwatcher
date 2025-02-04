from queue import Queue
import time
from eventwatcher.utils import spawn_periodic_worker, spawn_queue_worker
from eventwatcher.thread_manager import ThreadManager

# Define a simple periodic function.
def say_hello():
    print("Hello every 2 seconds!")

# Define a queue processing function.
def process_item(item):
    print(f"Processing item: {item}")

# Create a ThreadManager instance.
manager = ThreadManager()

# Start a periodic worker and register it.
periodic_worker = spawn_periodic_worker(say_hello, interval=2)
manager.register_thread(periodic_worker)

# Create a queue and start a queue worker.
q = Queue()
queue_worker = spawn_queue_worker(q, process_item, poll_interval=0.5)
manager.register_thread(queue_worker)

# Simulate adding items to the queue.
for i in range(10):
    q.put(f"Task {i}")
    time.sleep(1)

# Allow some extra time for processing.
time.sleep(5)

# Print the statuses of all registered threads.
print("Thread statuses before stopping:", manager.get_all_statuses())

# Stop and join all threads using the manager.
manager.stop_and_join_all(timeout=2)
print("All threads stopped.")

# Clear finished threads from the manager.
manager.clear_finished()
print("Final thread registry:", manager.threads)

