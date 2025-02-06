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


def periodic_cleanup_daemon(db_path, watch_groups, interval=120):
    """
    Run a periodic cleanup daemon to remove old records from the database.
    """
    wg_tm = ThreadManager()
    for group in watch_groups:
        wg_name = group.get('name', 'Unnamed')
        wg_max_samples = group.get('max_samples', 3)
        # wg_sample_rate = group.watch_group.get('sample_rate', 60)
        wg_cleanup_worker = spawn_periodic_worker(
            remove_old_samples,
            interval,
            db_path,
            wg_name,
            wg_max_samples
        )
        wg_tm.register_thread(wg_cleanup_worker)

    return wg_tm

def log_daemon_status(root_logger, watch_groups):
    """
    Log detailed daemon status information using psutil and watch groups info.
    """
    proc = psutil.Process(os.getpid())
    status_info = {
        "PID": proc.pid,
        "CPU %": proc.cpu_percent(interval=0.1),
        "Memory %": proc.memory_percent(),
        "Memory RSS": proc.memory_info().rss,
        "Threads": proc.num_threads(),
        "Started At": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(proc.create_time())),
        "Watch Groups": len(watch_groups)
    }
    # Optionally, list each watch group's name.
    group_names = [wg.get("name", "Unnamed") for wg in watch_groups]
    status_info["Watch Group Names"] = ", ".join(group_names)
    root_logger.info("Daemon Status:\n" + "\n".join(f"{k}: {v}" for k, v in status_info.items()))

def periodic_status_logger(root_logger, watch_groups, interval=60):
    """
    Log daemon status periodically.
    """
    while True:
        log_daemon_status(root_logger, watch_groups)
        time.sleep(interval)

def run_daemon(watch_groups, db_path, pid_file, config):
    """
    Run the monitoring service as a daemon with auto-reload functionality.
    """
    config_file_path = config.get("__config_path__", "./config.toml")
    watch_groups_config_path = config.get("watch_groups", {}).get("configs_dir", "watch_groups.yaml")

    # Set up logging for the daemon.
    log_dir = os.path.join(".", config.get("logging", {}).get("log_dir", "logs"))
    numeric_level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)
    root_logger = logger.setup_logger("EventWatcherDaemon", log_dir, "daemon.log", level=numeric_level, console=True)

    # Start a background thread to log status if debug is enabled.
    if numeric_level <= logging.DEBUG:
        status_thread = threading.Thread(target=periodic_status_logger, args=(root_logger, watch_groups), daemon=True)
        status_thread.start()

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

        # Log initial status
        log_daemon_status(root_logger, watch_groups)

        try:
            config_mtime = os.path.getmtime(config_file_path)
        except Exception as e:
            root_logger.error(f"Error getting modification time for config file: {e}")
            config_mtime = None

        if os.path.isdir(watch_groups_config_path):
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

        while True:
            reload_needed = False
            try:
                new_config_mtime = os.path.getmtime(config_file_path)
                if config_mtime and new_config_mtime != config_mtime:
                    reload_needed = True
            except Exception as e:
                root_logger.error(f"Error checking config file mtime: {e}")

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

            for t in threads:
                if not t.is_alive():
                    root_logger.error("A monitor thread has stopped unexpectedly.")
            time.sleep(10)

        for m in monitors:
            m.stop()
        for t in threads:
            t.join()

    pidfile_obj = PIDLockFile(pid_file)
    with daemon.DaemonContext(pidfile=pidfile_obj):
        root_logger.info("Daemon started with auto-reload enabled.")
        wg_tm = periodic_cleanup_daemon(db_path, watch_groups)
        while True:
            run_monitors()
            try:
                new_config = config_module.load_config(config_file_path)
                new_config["__config_path__"] = config_file_path
                new_watch_groups_data = config_module.load_watch_groups_configs(
                    new_config.get("watch_groups", {}).get("watch_groups_config", "watch_groups.yaml")
                )
                new_watch_groups = new_watch_groups_data.get("watch_groups", [])
                root_logger.info("Configuration reloaded. Restarting monitors.")
                watch_groups = new_watch_groups
                config = new_config
                root_logger.info(wg_tm.get_all_statuses())
            except Exception as e:
                root_logger.error(f"Error reloading configuration: {e}")
                time.sleep(10)
