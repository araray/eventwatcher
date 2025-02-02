import daemon
from daemon.pidfile import PIDLockFile
import threading
import time
import os
import logging
from . import monitor
from . import logger
import eventwatcher.config as config_module

def run_daemon(watch_groups, db_path, pid_file, config):
    """
    Run the monitoring service as a daemon with auto-reload functionality.

    The daemon monitors changes to the main configuration file and the watch groups configuration.
    If any changes are detected, the daemon will stop current monitors, reload the configuration,
    and restart the monitors.

    Args:
        watch_groups (list): List of watch group configurations.
        db_path (str): Path to the SQLite database.
        pid_file (str): Path to the PID file.
        config (dict): The configuration settings. It should include the key '__config_path__'
                       which is the path to the main configuration file.
    """
    # Get the config file path and watch groups config path from the config dictionary.
    # (The __config_path__ key should be set in cli.py when loading the config.)
    config_file_path = config.get("__config_path__", "./config.toml")
    watch_groups_config_path = config.get("watch_groups", {}).get("configs_dir", "watch_groups.yaml")

    # Set up logging for the daemon.
    log_dir = os.path.join(".", config.get("logging", {}).get("log_dir", "logs"))
    numeric_level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)
    root_logger = logger.setup_logger("EventWatcherDaemon", log_dir, "daemon.log", level=numeric_level)

    def run_monitors():
        """
        Start monitor threads for each watch group and poll for configuration changes.
        When a change is detected, all monitors are stopped.
        """
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

        # Record initial modification times.
        try:
            config_mtime = os.path.getmtime(config_file_path)
        except Exception as e:
            root_logger.error(f"Error getting modification time for config file: {e}")
            config_mtime = None

        if os.path.isdir(watch_groups_config_path):
            # For a directory, build a dict mapping file path to its modification time.
            watch_groups_mtimes = {}
            for filename in os.listdir(watch_groups_config_path):
                if filename.endswith(('.yaml', '.yml')):
                    full_path = os.path.join(watch_groups_config_path, filename)
                    try:
                        watch_groups_mtimes[full_path] = os.path.getmtime(full_path)
                    except Exception as e:
                        root_logger.error(f"Error getting modification time for {full_path}: {e}")
        else:
            try:
                watch_groups_mtimes = os.path.getmtime(watch_groups_config_path)
            except Exception as e:
                root_logger.error(f"Error getting modification time for watch groups config file: {e}")
                watch_groups_mtimes = None

        # Poll for configuration changes every 10 seconds.
        while True:
            reload_needed = False
            # Check main config file.
            try:
                new_config_mtime = os.path.getmtime(config_file_path)
                if config_mtime and new_config_mtime != config_mtime:
                    reload_needed = True
            except Exception as e:
                root_logger.error(f"Error checking config file mtime: {e}")

            # Check watch groups config (either directory or single file).
            if os.path.isdir(watch_groups_config_path):
                for filename in os.listdir(watch_groups_config_path):
                    if filename.endswith(('.yaml', '.yml')):
                        full_path = os.path.join(watch_groups_config_path, filename)
                        try:
                            new_mtime = os.path.getmtime(full_path)
                            if full_path not in watch_groups_mtimes or watch_groups_mtimes[full_path] != new_mtime:
                                reload_needed = True
                                break
                        except Exception as e:
                            root_logger.error(f"Error checking mtime for {full_path}: {e}")
            else:
                try:
                    new_watch_mtime = os.path.getmtime(watch_groups_config_path)
                    if watch_groups_mtimes and new_watch_mtime != watch_groups_mtimes:
                        reload_needed = True
                except Exception as e:
                    root_logger.error(f"Error checking watch groups config file mtime: {e}")

            if reload_needed:
                root_logger.info("Configuration change detected. Restarting monitors.")
                break

            # Also check that all monitor threads are alive.
            for t in threads:
                if not t.is_alive():
                    root_logger.error("A monitor thread has stopped unexpectedly.")
            time.sleep(10)

        # Stop all monitors.
        for m in monitors:
            m.stop()
        for t in threads:
            t.join()

    # Use PIDLockFile to manage the PID file.
    pidfile_obj = PIDLockFile(pid_file)
    with daemon.DaemonContext(pidfile=pidfile_obj):
        root_logger.info("Daemon started with auto-reload enabled.")
        # Run in a loop: each iteration runs the monitors until a config change is detected.
        while True:
            run_monitors()
            # After monitors have stopped, reload configuration.
            try:
                new_config = config_module.load_config(config_file_path)
                # Store the config file path in the new config dictionary.
                new_config["__config_path__"] = config_file_path
                new_watch_groups_data = config_module.load_watch_groups_configs(
                    new_config.get("watch_groups", {}).get("watch_groups_config", "watch_groups.yaml")                )
                new_watch_groups = new_watch_groups_data.get("watch_groups", [])
                root_logger.info("Configuration reloaded. Restarting monitors.")
                # Update variables for the next loop iteration.
                watch_groups = new_watch_groups
                config = new_config
                # Optionally, update db_path or log_dir if they have changed.
            except Exception as e:
                root_logger.error(f"Error reloading configuration: {e}")
                # If there is an error, wait a bit before trying again.
                time.sleep(10)
