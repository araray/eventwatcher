# USAGE Guide for EventWatcher

## Overview

EventWatcher monitors files and directories for events based on user-defined rules.
It can be used as both a library and a CLI tool.

## CLI Commands

- **show-config:** Display the effective configuration.
- **init-db:** Initialize the SQLite database.
- **monitor-once:** Run a single monitoring sample.
- **start:** Start the service (default is daemon mode; use `--foreground` for foreground execution).
- **show-db:** Display stored events from the database.

## Configuration

The main configuration is defined in a TOML file (`config.toml`). This file specifies global settings,
including the database file name and the path to the watch groups configuration.

Watch groups are defined in a YAML file (e.g., `watch_groups.yaml`). Each watch group includes:
- `name`: Identifier for the group.
- `watch_items`: List of files/directories or glob patterns to monitor.
- `sample_rate`: Sampling interval (in seconds; minimum 60 seconds).
- `max_samples`: Maximum number of samples to retain.
- `max_depth`: (Optional) Maximum directory traversal depth.
- `pattern`: (Optional) A string to search for in files.
- `rules`: A list of rules to evaluate, each with:
  - `name`: Event name.
  - `condition`: A Python expression evaluated against the sample data.

## Using as a Library

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load configurations
config = load_config("config.toml")
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Use the first watch group
group_config = watch_groups.get("watch_groups", [])[0]
monitor = Monitor(group_config, db_path="eventwatcher.db")
sample, events = monitor.run_once()
```

## Extending and Customizing

- **Rules:** Modify or add new rules in `eventwatcher/rules.py`.
- **Monitoring:** Enhance file/directory scanning in `eventwatcher/monitor.py`.
- **Logging/DB:** Customize logging or data storage in `eventwatcher/db.py`.

For further details, see the inline documentation in the source code.
