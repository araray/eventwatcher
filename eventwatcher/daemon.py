import daemon
from daemon.pidfile import PIDLockFile
import threading
import time
import os
import logging
from eventwatcher import monitor
from eventwatcher import logger
import eventwatcher.config as config_module

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

            # End of the run_monitors loop.
        for m in monitors:
            m.stop()
        for t in threads:
            t.join()

    pidfile_obj = PIDLockFile(pid_file)
    with daemon.DaemonContext(pidfile=pidfile_obj):
        root_logger.info("Daemon started with auto-reload enabled.")
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
            except Exception as e:
                root_logger.error(f"Error reloading configuration: {e}")
                time.sleep(10)
