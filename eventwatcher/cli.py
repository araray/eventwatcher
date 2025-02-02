import os
import signal
import time
import threading
import click
import sqlite3
from . import config
from . import db
from . import monitor
from . import daemon as daemon_module

DEFAULT_PID_FILENAME = "eventwatcher.pid"

@click.group()
@click.option("--config", "-c", "config_path", default=None, help="Path to configuration TOML file.")
@click.pass_context
def main(ctx, config_path):
    """
    EventWatcher CLI: Monitor files and directories for events.
    """
    try:
        cfg = config.load_config(config_path)
        # Store the config file path in the config dict for use by the daemon.
        cfg["__config_path__"] = config_path
    except Exception as e:
        click.echo(f"Error loading configuration: {e}")
        ctx.abort()
    ctx.obj = {"config": cfg, "config_path": config_path}

def get_log_dir(cfg, config_path):
    # Determine logs directory from config.
    config_dir = os.path.dirname(cfg.get("config_path", config_path) or "./config.toml")
    return os.path.join(config_dir, cfg.get("logging", {}).get("log_dir", "logs"))

def get_pid_file(log_dir):
    return os.path.join(log_dir, DEFAULT_PID_FILENAME)

@main.command()
@click.pass_context
def show_config(ctx):
    """
    Show the loaded configuration.
    """
    cfg = ctx.obj.get("config")
    click.echo(cfg)

@main.command()
@click.pass_context
def init_db(ctx):
    """
    Initialize the SQLite database.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    db.init_db(db_path)
    db.init_exploded_samples(db_path)
    click.echo(f"Database initialized at {db_path}")

@main.command()
@click.pass_context
def monitor_once(ctx):
    """
    Run one monitoring sample for all watch groups.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    # Load watch groups configuration from YAML file or directory.
    watch_groups_config_path = cfg.get("watch_groups_config", "watch_groups.yaml")
    try:
        watch_groups = config.load_watch_groups_configs(watch_groups_config_path)
    except Exception as e:
        click.echo(f"Error loading watch groups configuration: {e}")
        return

    for group in watch_groups.get("watch_groups", []):
        m = monitor.Monitor(group, db_path, log_dir, log_level=cfg.get("logging", {}).get("level", "INFO"))
        sample, events = m.run_once()
        click.echo(f"Group '{group.get('name', 'Unnamed')}' sample: {sample}")
        if events:
            click.echo(f"Triggered events: {events}")
        else:
            click.echo("No events triggered.")

@main.command()
@click.option("--foreground", is_flag=True, help="Run in foreground (not as daemon).")
@click.pass_context
def start(ctx, foreground):
    """
    Start the EventWatcher service.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    pid_file = get_pid_file(log_dir)
    # Load watch groups configuration from YAML.
    watch_groups_config_path = cfg.get("watch_groups", {}).get("configs_dir", "watch_groups.yaml")
    try:
        watch_groups_data = config.load_watch_groups_configs(watch_groups_config_path)
    except Exception as e:
        click.echo(f"Error loading watch groups configuration: {e}")
        return

    watch_groups = watch_groups_data.get("watch_groups", [])

    if foreground:
        click.echo("Running in foreground...")
        monitors = []
        threads = []
        for group in watch_groups:
            m = monitor.Monitor(group, db_path, log_dir, log_level=cfg.get("logging", {}).get("level", "INFO"))
            monitors.append(m)
            t = threading.Thread(target=m.run)
            t.daemon = True
            t.start()
            threads.append(t)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            for m in monitors:
                m.stop()
    else:
        click.echo("Starting daemon...")
        daemon_module.run_daemon(watch_groups, db_path, pid_file=pid_file, config=cfg)

@main.command()
@click.pass_context
def stop(ctx):
    """
    Stop the EventWatcher daemon.
    """
    cfg = ctx.obj.get("config")
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    pid_file = get_pid_file(log_dir)
    if not os.path.exists(pid_file):
        click.echo("Daemon is not running (pid file not found).")
        return
    with open(pid_file, 'r') as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Sent SIGTERM to daemon (pid {pid}).")
        # Optionally, wait for process to terminate.
        time.sleep(2)
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception as e:
        click.echo(f"Error stopping daemon: {e}")

@main.command()
@click.pass_context
def status(ctx):
    """
    Check the status of the EventWatcher daemon.
    """
    cfg = ctx.obj.get("config")
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    pid_file = get_pid_file(log_dir)
    if not os.path.exists(pid_file):
        click.echo("Daemon is not running (pid file not found).")
        return
    with open(pid_file, 'r') as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 0)
        click.echo(f"Daemon is running (pid {pid}).")
    except Exception:
        click.echo("Daemon is not running, but pid file exists.")

@main.command()
@click.option("--watch-group", "-w", default=None, help="Filter by watch group name.")
@click.pass_context
def search_db(ctx, watch_group):
    """
    Search events in the database.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    if watch_group:
        cur.execute("SELECT * FROM events WHERE watch_group = ?", (watch_group,))
    else:
        cur.execute("SELECT * FROM events")
    rows = cur.fetchall()
    if rows:
        click.echo("Events:")
        for row in rows:
            click.echo(row)
    else:
        click.echo("No events found.")
    conn.close()

@main.command()
@click.option("--term", "-t", default="", help="Search term for log files.")
@click.pass_context
def search_logs(ctx, term):
    """
    Search through log files in the logs directory.
    """
    cfg = ctx.obj.get("config")
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    if not os.path.isdir(log_dir):
        click.echo("Logs directory not found.")
        return
    for root, _, files in os.walk(log_dir):
        for file in files:
            if file.endswith(".log"):
                file_path = os.path.join(root, file)
                with open(file_path, "r") as f:
                    contents = f.read()
                    if term in contents:
                        click.echo(f"Found in {file_path}:")
                        click.echo(contents)
                        click.echo("-" * 40)

@main.command()
@click.pass_context
def restart(ctx):
    """
    Restart the EventWatcher daemon.
    """
    ctx.invoke(stop)
    time.sleep(1)
    ctx.invoke(start)

@main.command()
@click.pass_context
def show_db(ctx):
    """
    Show events stored in the database.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM events")
    rows = cur.fetchall()
    if rows:
        click.echo("Events:")
        for row in rows:
            click.echo(row)
    else:
        click.echo("No events found.")
    conn.close()

if __name__ == "__main__":
    main()
