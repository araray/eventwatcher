import click
import os
from . import config
from . import db
from . import monitor
from . import daemon as daemon_module
import threading

DEFAULT_PIDFILE = "/tmp/eventwatcher.pid"

@click.group()
@click.option("--config", "-c", "config_path", default=None, help="Path to configuration TOML file.")
@click.pass_context
def main(ctx, config_path):
    """
    EventWatcher CLI: Monitor files and directories for events.
    """
    try:
        cfg = config.load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}")
        ctx.abort()
    ctx.obj = {"config": cfg, "config_path": config_path}

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

    # Load watch groups configuration from YAML.
    watch_groups_config_path = cfg.get("watch_groups_config", "watch_groups.yaml")
    try:
        watch_groups = config.load_watch_groups_config(watch_groups_config_path)
    except Exception as e:
        click.echo(f"Error loading watch groups configuration: {e}")
        return

    for group in watch_groups.get("watch_groups", []):
        m = monitor.Monitor(group, db_path, log_func=click.echo)
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

    # Load watch groups configuration from YAML.
    watch_groups_config_path = cfg.get("watch_groups_config", "watch_groups.yaml")
    try:
        watch_groups_data = config.load_watch_groups_config(watch_groups_config_path)
    except Exception as e:
        click.echo(f"Error loading watch groups configuration: {e}")
        return

    watch_groups = watch_groups_data.get("watch_groups", [])
    if foreground:
        click.echo("Running in foreground...")
        monitors = []
        threads = []
        for group in watch_groups:
            m = monitor.Monitor(group, db_path, log_func=click.echo)
            monitors.append(m)
            t = threading.Thread(target=m.run)
            t.daemon = True
            t.start()
            threads.append(t)
        try:
            while True:
                pass
        except KeyboardInterrupt:
            for m in monitors:
                m.stop()
    else:
        click.echo("Starting daemon...")
        daemon_module.run_daemon(watch_groups, db_path, pidfile=DEFAULT_PIDFILE, log_func=click.echo)

@main.command()
@click.pass_context
def show_db(ctx):
    """
    Show events stored in the database.
    """
    import sqlite3
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
