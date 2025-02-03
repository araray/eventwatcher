import os
import signal
import time
import threading
import json
import click
import sqlite3
from eventwatcher import config
from eventwatcher import db
from eventwatcher import monitor
from eventwatcher import daemon as daemon_module
from eventwatcher import rule_helpers
import psutil
from rich.console import Console
from rich.table import Table
import csv
import io
import sys

DEFAULT_PID_FILENAME = "eventwatcher.pid"

@click.group()
@click.option("--config", "-c", "config_path", default=None, help="Path to configuration TOML file.")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx, config_path, debug):
    """
    EventWatcher CLI: Monitor files and directories for events.
    """
    try:
        cfg = config.load_config(config_path)
        if debug:
            cfg.setdefault("logging", {})["level"] = "DEBUG"
        cfg["__config_path__"] = config_path
    except Exception as e:
        click.echo(f"Error loading configuration: {e}")
        ctx.abort()
    ctx.obj = {"config": cfg, "config_path": config_path, "debug": debug}

def get_log_dir(cfg, config_path):
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
    watch_groups_config_path = cfg.get("watch_groups", {}).get("configs_dir", "watch_groups.yaml")
    try:
        watch_groups = config.load_watch_groups_configs(watch_groups_config_path)
    except Exception as e:
        click.echo(f"Error loading watch groups configuration: {e}")
        return

    for group in watch_groups.get("watch_groups", []):
        m = monitor.Monitor(group, db_path, log_dir, log_level=cfg.get("logging", {}).get("level", "INFO"))
        sample, events = m.run_once()
        click.echo(f"Group '{group.get('name', 'Unnamed')}' sample: {json.dumps(sample, indent=2)}")
        if events:
            click.echo(f"Triggered events: {json.dumps(events, indent=2)}")
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
    Displays process info (memory, CPU, threads, start time) and watch group details.
    Also logs this info to daemon.log.
    """
    cfg = ctx.obj.get("config")
    log_dir = get_log_dir(cfg, ctx.obj.get("config_path"))
    pid_file = get_pid_file(log_dir)
    console = Console()

    if not os.path.exists(pid_file):
        click.echo("Daemon is not running (pid file not found).")
        return

    with open(pid_file, 'r') as f:
        pid = int(f.read().strip())
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        click.echo("Daemon process not found.")
        return

    status_table = Table(title="EventWatcher Daemon Status")
    status_table.add_column("Property", style="cyan")
    status_table.add_column("Value", style="magenta")
    status_table.add_row("PID", str(proc.pid))
    status_table.add_row("CPU %", f"{proc.cpu_percent(interval=0.1)}")
    status_table.add_row("Memory %", f"{proc.memory_percent():.2f}")
    status_table.add_row("Memory RSS", str(proc.memory_info().rss))
    status_table.add_row("Threads", str(proc.num_threads()))
    status_table.add_row("Start Time", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(proc.create_time())))

    # For watch groups info, load the watch groups configuration.
    watch_groups_config_path = cfg.get("watch_groups", {}).get("configs_dir", "watch_groups.yaml")
    try:
        watch_groups_data = config.load_watch_groups_configs(watch_groups_config_path)
        groups = watch_groups_data.get("watch_groups", [])
        status_table.add_row("Watch Groups Count", str(len(groups)))
        group_names = ", ".join([g.get("name", "Unnamed") for g in groups])
        status_table.add_row("Watch Group Names", group_names)
    except Exception as e:
        status_table.add_row("Watch Groups", f"Error loading: {e}")

    console.print(status_table)

@main.command(name="show-events")
@click.option("--watch-group", "-w", default=None, help="Filter by watch group name.")
@click.option("--format", "-f", "out_format", default="tabulate", type=click.Choice(["tabulate", "json", "csv", "raw"], case_sensitive=False), help="Output format.")
@click.pass_context
def show_events(ctx, watch_group, out_format):
    """
    Show events stored in the database with various output formats.
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
    columns = [column[0] for column in cur.description]
    conn.close()

    if out_format.lower() == "json":
        click.echo(json.dumps([dict(row) for row in rows], indent=2))
    elif out_format.lower() == "csv":
        if rows:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(list(row))
            click.echo(output.getvalue())
        else:
            click.echo("No events found.")
    elif out_format.lower() == "raw":
        click.echo(rows)
    else:
        # Default: tabulate using rich table
        table = Table(title="EventWatcher Events")
        if rows:
            for col in columns:
                table.add_column(col)
            for row in rows:
                table.add_row(*[str(val) for val in row])
            Console().print(table)
        else:
            click.echo("No events found.")

@main.command()
@click.argument("sql_query", nargs=-1)
@click.pass_context
def query(ctx, sql_query):
    """
    Execute an arbitrary SQL query against the EventWatcher database.
    Example:
      eventwatcher query "SELECT * FROM events LIMIT 5"
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    query_str = " ".join(sql_query)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(query_str)
        rows = cur.fetchall()
        if rows:
            table = Table(title="Query Results")
            for col in rows[0].keys():
                table.add_column(col)
            for row in rows:
                table.add_row(*[str(val) for val in row])
            Console().print(table)
        else:
            click.echo("No results found.")
    except Exception as e:
        click.echo(f"Error executing query: {e}")
    finally:
        conn.close()

@main.command()
@click.pass_context
def info(ctx):
    """
    Show available database tables/columns and available rule helper functions.
    """
    cfg = ctx.obj.get("config")
    config_dir = os.path.dirname(ctx.obj.get("config_path") or "./config.toml")
    db_path = os.path.join(config_dir, cfg.get("database", {}).get("db_name", "eventwatcher.db"))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    console = Console()
    table = Table(title="Database Tables & Columns")
    table.add_column("Table Name", style="cyan")
    table.add_column("Columns", style="magenta")
    for t in tables:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({t})")
        cols = [row[1] for row in cur.fetchall()]
        conn.close()
        table.add_row(t, ", ".join(cols))
    console.print(table)

    # List available rule helper functions.
    console.print("\n[bold]Available Rule Helper Functions:[/bold]")
    available_funcs = {
        "aggregate_metric": rule_helpers.aggregate_metric,
        "get_previous_metric": rule_helpers.get_previous_metric,
        # plus safe builtins
        "min": min,
        "max": max,
        "any": any,
        "all": all,
        "sum": sum,
        "len": len,
    }
    for func_name in available_funcs:
        console.print(f" - {func_name}")

if __name__ == "__main__":
    main()
