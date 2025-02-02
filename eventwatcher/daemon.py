import daemon
import threading
from .monitor import Monitor

def run_daemon(watch_groups, db_path, pidfile="/tmp/eventwatcher.pid", log_func=print):
    """
    Run the monitoring service as a daemon.

    Args:
        watch_groups (list): List of watch group configurations.
        db_path (str): Path to the SQLite database.
        pidfile (str): Path to the PID file.
        log_func (callable): Logging function.
    """
    def run_monitors():
        monitors = []
        threads = []
        for group in watch_groups:
            monitor_instance = Monitor(group, db_path, log_func=log_func)
            monitors.append(monitor_instance)
            t = threading.Thread(target=monitor_instance.run)
            t.daemon = True
            t.start()
            threads.append(t)
        # Keep the daemon running.
        try:
            while True:
                for t in threads:
                    if not t.is_alive():
                        log_func("A monitor thread has stopped unexpectedly.")
                import time
                time.sleep(10)
        except KeyboardInterrupt:
            for m in monitors:
                m.stop()

    # Using a pidfile for process management.
    with daemon.DaemonContext(pidfile=open(pidfile, 'w+')):
        run_monitors()
