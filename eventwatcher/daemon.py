import json
import logging
import os
import threading
import time

import daemon
import psutil
from daemon.pidfile import PIDLockFile

import eventwatcher.config as config_module
from eventwatcher import logger, monitor
from eventwatcher.db import remove_old_samples
from eventwatcher.thread_manager import ThreadManager
from eventwatcher.utils import spawn_periodic_worker


def setup_daemon_logger(config, config_path):
    """
    Set up logging for the daemon with proper path resolution and error handling.

    Args:
        config (dict): The loaded configuration dictionary
        config_path (str): Path to the config file

    Returns:
        logging.Logger: Configured logger instance
    """
    try:
        if not config_path:
            raise ValueError("Config path must be provided")

        # Get the absolute path to the config directory
        config_dir = os.path.dirname(os.path.abspath(config_path))

        # Construct absolute path to log directory
        log_dir = os.path.join(
            config_dir, config.get("logging", {}).get("log_dir", "logs")
        )

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Get logging level with a safe default
        log_level = config.get("logging", {}).get("level", "INFO").upper()
        numeric_level = getattr(logging, log_level, logging.INFO)

        # Set up the logger
        daemon_logger = logger.setup_logger(
            "EventWatcherDaemon",
            log_dir,
            "daemon.log",
            level=numeric_level,
            console=True,
        )

        # Test write to log
        daemon_logger.info("Daemon logger initialized successfully")
        daemon_logger.info(f"Using config from: {config_path}")
        daemon_logger.info(f"Log directory: {log_dir}")

        return daemon_logger

    except Exception as e:
        # If we can't set up logging, write to a failsafe log file
        failsafe_log = "/tmp/eventwatcher_daemon_error.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        error_msg = f"{timestamp} - Error setting up daemon logger: {str(e)}\n"
        try:
            with open(failsafe_log, "a") as f:
                f.write(error_msg)
        except Exception as write_error:
            print(f"Failed to write to failsafe log: {str(write_error)}")
            print(error_msg)
        raise RuntimeError(f"Failed to set up daemon logger: {str(e)}")


def periodic_cleanup_daemon(db_path, watch_groups, interval=120):
    """
    Run a periodic cleanup daemon to remove old records from the database.
    """
    wg_tm = ThreadManager()
    for group in watch_groups:
        wg_name = group.get("name", "Unnamed")
        wg_max_samples = group.get("max_samples", 3)
        wg_cleanup_worker = spawn_periodic_worker(
            remove_old_samples, interval, db_path, wg_name, wg_max_samples
        )
        wg_tm.register_thread(wg_cleanup_worker)

    return wg_tm


def log_daemon_status(root_logger, watch_groups):
    """
    Log detailed daemon status information using psutil and watch groups info.
    """
    try:
        proc = psutil.Process(os.getpid())
        status_info = {
            "PID": proc.pid,
            "CPU %": proc.cpu_percent(interval=0.1),
            "Memory %": proc.memory_percent(),
            "Memory RSS": proc.memory_info().rss,
            "Threads": proc.num_threads(),
            "Started At": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(proc.create_time())
            ),
            "Watch Groups": len(watch_groups),
        }
        # List each watch group's name
        group_names = [wg.get("name", "Unnamed") for wg in watch_groups]
        status_info["Watch Group Names"] = ", ".join(group_names)
        root_logger.info(
            "Daemon Status:\n" + "\n".join(f"{k}: {v}" for k, v in status_info.items())
        )
    except Exception as e:
        root_logger.error(f"Error logging daemon status: {str(e)}")


def periodic_status_logger(wg_tm, root_logger, watch_groups, interval=60):
    """
    Periodically logs the status the daemon and of all threads managed by the ThreadManager.

    Args:
        wg_tm (ThreadManager): The thread manager instance to monitor
        root_logger (logging.Logger): Logger instance for output
        watch_groups (list): List of watch group configurations
        interval (int): How often to log status, in seconds
    """
    while True:
        try:
            log_daemon_status(root_logger, watch_groups)
            statuses = wg_tm.get_all_statuses()
            root_logger.info("=== Thread Manager Status Report ===")
            for thread_name, status in statuses.items():
                root_logger.info(
                    f"Thread '{thread_name}': "
                    f"alive={status.get('is_alive', False)}, "
                    f"daemon={status.get('daemon', False)}, "
                    f"id={status.get('id')}"
                )
            root_logger.info("================================")
            time.sleep(interval)
        except Exception as e:
            root_logger.error(f"Error in status logger: {e}", exc_info=True)
            time.sleep(interval)  # Still sleep on error to prevent tight loop


def run_daemon(watch_groups, db_path, pid_file, config, config_path=None):
    """Run the monitoring service as a daemon with auto-reload functionality."""
    # Get config path, with proper fallback logic
    if config_path is None:
        config_path = config.get("__config_path__")
        if config_path is None:
            config_path = "./config.toml"
            if not os.path.exists(config_path):
                raise ValueError("No valid config path provided or found")

    config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(config_path)

    # Get log directory from config
    log_dir = os.path.join(config_dir, config.get("logging", {}).get("log_dir", "logs"))
    log_dir = os.path.abspath(log_dir)  # Ensure absolute path

    watch_groups_config_path = config.get("watch_groups", {}).get(
        "configs_dir", "watch_groups.yaml"
    )

    # Set up logging before daemonization
    root_logger = setup_daemon_logger(config, config_path)
    root_logger.info(f"Using absolute log directory: {log_dir}")

    def run_monitors(
        config_path=config_path, watch_groups_config_path=watch_groups_config_path
    ):
        try:
            monitors = []
            threads = []
            for group in watch_groups:
                root_logger.info(f"Creating monitor for group: {group.get('name')}")
                root_logger.info(f"Using log directory: {log_dir}")

                m = monitor.Monitor(
                    group,
                    db_path,
                    log_dir,  # Pass the absolute log directory path
                    log_level=config.get("logging", {}).get("level", "INFO"),
                )
                monitors.append(m)
                t = threading.Thread(
                    target=m.run,
                    name=f"Monitor-{group.get('name', 'Unnamed')}",  # Named thread for better debugging
                )
                t.daemon = True
                t.start()
                threads.append(t)
                root_logger.info(f"Started monitor thread: {t.name}")

            # Log initial status
            log_daemon_status(root_logger, watch_groups)

            try:
                config_mtime = os.path.getmtime(config_path)
                root_logger.debug(
                    f"Initial config mtime: {config_mtime} for {config_path}"
                )
            except Exception as e:
                root_logger.error(
                    f"Error getting modification time for config file {config_path}: {e}"
                )
                config_mtime = None

            # Initialize watch_groups_mtimes
            watch_groups_mtimes = {}
            if os.path.isdir(watch_groups_config_path):
                for filename in os.listdir(watch_groups_config_path):
                    if filename.endswith((".yaml", ".yml")):
                        full_path = os.path.join(watch_groups_config_path, filename)
                        try:
                            watch_groups_mtimes[full_path] = os.path.getmtime(full_path)
                            root_logger.debug(
                                f"Initial watch group config mtime: {watch_groups_mtimes[full_path]} for {full_path}"
                            )
                        except Exception as e:
                            root_logger.error(
                                f"Error getting modification time for {full_path}: {e}"
                            )
            else:
                try:
                    watch_groups_mtimes = {
                        watch_groups_config_path: os.path.getmtime(
                            watch_groups_config_path
                        )
                    }
                    root_logger.debug(
                        f"Initial watch group config mtime: {watch_groups_mtimes[watch_groups_config_path]} for {watch_groups_config_path}"
                    )
                except Exception as e:
                    root_logger.error(
                        f"Error getting modification time for watch groups config file: {e}"
                    )
                    watch_groups_mtimes = None

            while True:
                reload_needed = False
                try:
                    new_config_mtime = os.path.getmtime(config_path)
                    if config_mtime and new_config_mtime != config_mtime:
                        root_logger.info(
                            f"Config file {config_path} has changed. Old mtime: {config_mtime}, New mtime: {new_config_mtime}"
                        )
                        reload_needed = True
                except Exception as e:
                    root_logger.error(
                        f"Error checking config file mtime for {config_path}: {e}"
                    )

                if os.path.isdir(watch_groups_config_path):
                    for filename in os.listdir(watch_groups_config_path):
                        if filename.endswith((".yaml", ".yml")):
                            full_path = os.path.join(watch_groups_config_path, filename)
                            try:
                                new_mtime = os.path.getmtime(full_path)
                                if (
                                    full_path not in watch_groups_mtimes
                                    or watch_groups_mtimes[full_path] != new_mtime
                                ):
                                    root_logger.info(
                                        f"Watch group config {full_path} has changed"
                                    )
                                    reload_needed = True
                                    break
                            except Exception as e:
                                root_logger.error(
                                    f"Error checking mtime for {full_path}: {e}"
                                )
                else:
                    try:
                        new_watch_mtime = os.path.getmtime(watch_groups_config_path)
                        if (
                            watch_groups_mtimes
                            and watch_groups_mtimes[watch_groups_config_path]
                            != new_watch_mtime
                        ):
                            root_logger.info(
                                f"Watch group config {watch_groups_config_path} has changed"
                            )
                            reload_needed = True
                    except Exception as e:
                        root_logger.error(
                            f"Error checking watch groups config file mtime: {e}"
                        )

                if reload_needed:
                    root_logger.info(
                        "Configuration change detected. Restarting monitors."
                    )
                    break

                # Check thread health
                for idx, t in enumerate(threads):
                    if not t.is_alive():
                        root_logger.error(
                            f"Monitor thread {idx} has stopped unexpectedly"
                        )

                time.sleep(10)

            # Stop and clean up monitors
            root_logger.info("Stopping monitors for reload")
            for m in monitors:
                m.stop()
            for t in threads:
                t.join(timeout=5.0)  # Give threads 5 seconds to stop

        except Exception as e:
            root_logger.error(f"Error in run_monitors: {str(e)}", exc_info=True)

    # Create daemon context with our logger
    context = daemon.DaemonContext(
        pidfile=PIDLockFile(pid_file),
        files_preserve=[
            handler.stream.fileno()
            for handler in root_logger.handlers
            if hasattr(handler, "stream") and hasattr(handler.stream, "fileno")
        ],
    )

    with context:
        try:
            root_logger.info(
                f"Daemon started with auto-reload enabled. Config path: {config_path}"
            )
            wg_tm = periodic_cleanup_daemon(db_path, watch_groups)

            # Create and start the status logging thread
            status_logger_thread = threading.Thread(
                target=periodic_status_logger,
                args=(wg_tm, root_logger, watch_groups, 300),  # Log every 5 minutes
                daemon=True,  # Make it a daemon thread so it exits with the main program
                name="EVW_StatusLogger",
            )
            status_logger_thread.start()

            # Initial status dump
            root_logger.info("Initial thread manager status:")
            root_logger.info(json.dumps(wg_tm.get_all_statuses(), default=str))

            while True:
                run_monitors()
                try:
                    root_logger.info("Reloading configuration...")
                    new_config = config_module.load_config(config_path)
                    new_config["__config_path__"] = config_path
                    new_watch_groups_data = config_module.load_watch_groups_configs(
                        new_config.get("watch_groups", {}).get(
                            "watch_groups_config", "watch_groups.yaml"
                        )
                    )
                    new_watch_groups = new_watch_groups_data.get("watch_groups", [])
                    root_logger.info(
                        "Configuration reloaded successfully. Restarting monitors."
                    )
                    watch_groups = new_watch_groups
                    config = new_config

                    try:
                        statuses = wg_tm.get_all_statuses()
                        root_logger.info("Thread manager statuses:")
                        for thread_name, status in statuses.items():
                            root_logger.info(
                                f"Thread '{thread_name}': alive={status.get('is_alive', False)}, "
                                f"daemon={status.get('daemon', False)}"
                            )
                    except Exception as status_err:
                        root_logger.error(
                            f"Error getting thread statuses: {status_err}",
                            exc_info=True,
                        )

                except Exception as e:
                    root_logger.error(
                        f"Error reloading configuration: {e}", exc_info=True
                    )
                    time.sleep(10)

        except Exception as e:
            root_logger.error(f"Fatal error in daemon: {str(e)}", exc_info=True)
            raise
