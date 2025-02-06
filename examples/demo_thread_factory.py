import time
from queue import Queue

from eventwatcher.utils import spawn_periodic_worker, spawn_queue_worker


# Define a simple periodic function.
def say_hello():
    print("Hello every 2 seconds!")


# Define a queue processing function.
def process_item(item):
    print(f"Processing item: {item}")


# Start a periodic worker.
periodic_worker = spawn_periodic_worker(say_hello, interval=2)

# Create a queue and start a queue worker.
q = Queue()
queue_worker = spawn_queue_worker(q, process_item, poll_interval=0.5)

# Simulate adding items to the queue.
for i in range(10):
    q.put(f"Task {i}")
    time.sleep(1)

# Give some time for processing.
time.sleep(5)

# Stop the threads gracefully.
periodic_worker.stop()
queue_worker.stop()

# Join threads if necessary.
periodic_worker.join()
queue_worker.join()
