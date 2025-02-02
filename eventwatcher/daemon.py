import daemon
from daemon.pidfile import PIDLockFile
import threading
import time
import os
import logging
from . import monitor
from . import logger

def run_daemon(watch_groups, db_path, pid_file, config):
    """
    Run the monitoring service as a daemon.

    Args:
        watch_groups (list): List of watch group configurations.
        db_path (str): Path to the SQLite database.
        pid_file (str): Path to the PID file.
        config (dict): The configuration settings.
    """
    # Determine the log directory and logging level from config.
    log_dir = os.path.join(".", config.get("logging", {}).get("log_dir", "logs"))
    numeric_level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)
    root_logger = logger.setup_logger("EventWatcherDaemon", log_dir, "daemon.log", level=numeric_level)

    def run_monitors():
        monitors = []
        threads = []
        for group in watch_groups:
            m = monitor.Monitor(
                group,
                db_path,
                log_dir,
                log_level=config.get("logging", {}).get("level", "INFO")
            )
            monitors.append(m)
            t = threading.Thread(target=m.run)
            t.daemon = True
            t.start()
            threads.append(t)
        # Keep the daemon running and check thread health.
        try:
            while True:
                for t in threads:
                    if not t.is_alive():
                        root_logger.error("A monitor thread has stopped unexpectedly.")
                time.sleep(10)
        except KeyboardInterrupt:
            for m in monitors:
                m.stop()

    # Use PIDLockFile to manage the PID file.
    pidfile_obj = PIDLockFile(pid_file)
    with daemon.DaemonContext(pidfile=pidfile_obj):
        root_logger.info("Daemon started.")
        run_monitors()
