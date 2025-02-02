# USAGE Guide for EventWatcher

This guide explains how to use EventWatcher as both a command-line tool and a library. It covers configuration, running the monitor, advanced rule evaluation, and an overview of the database structure.

---

## Overview

EventWatcher is a Python-based tool that monitors files and directories for changes based on user-defined rules. It supports two configuration files:
- A **global configuration** (`config.toml`) for general settings (database, logging, etc.).
- A **watch groups configuration** (`watch_groups.yaml`) that defines what to monitor, how often to sample, and the rules that trigger events.

The latest version introduces:
- **Enhanced Rule Evaluation:**
  Use helper functions (e.g., `aggregate`) along with safe built-ins (`min`, `max`, etc.) so that rules can reference metrics over files matching glob patterns.

- **Exploded Samples:**
  Each file/directory from a monitoring cycle is stored as an individual row in the database, enabling SQL-based queries and comparisons between current and historical data.

---

## CLI Commands

EventWatcher comes with several CLI commands to manage configuration, the database, and the monitoring service.

### 1. Display the Loaded Configuration

Prints out the currently loaded configuration settings.

```bash
eventwatcher show-config --config path/to/config.toml
```

### 2. Initialize the Database

Creates (if they do not exist) the necessary tables:
- `events` for triggered events,
- `samples` for full JSON snapshots of each monitoring cycle, and
- `exploded_samples` for per-file metrics.

```bash
eventwatcher init-db --config path/to/config.toml
```

### 3. Run a Single Monitoring Cycle

Collect a single sample from all watch groups, evaluate rules, log the sample, and insert any triggered events into the database.

```bash
eventwatcher monitor-once --config path/to/config.toml
```

### 4. Start the Service

Launch EventWatcher either in the foreground (useful for testing) or as a daemon (recommended for production).

- **Foreground Mode:**

  ```bash
  eventwatcher start --foreground --config path/to/config.toml
  ```

- **Daemon Mode:**

  ```bash
  eventwatcher start --config path/to/config.toml
  ```

### 5. Stop the Daemon

Stop a running daemon by sending a termination signal.

```bash
eventwatcher stop --config path/to/config.toml
```

### 6. Check Daemon Status

Check whether the daemon is running.

```bash
eventwatcher status --config path/to/config.toml
```

### 7. Search the Database and Logs

- **Search Events in the Database:**

  ```bash
  eventwatcher search_db --watch-group "Example Group" --config path/to/config.toml
  ```

- **Search through Log Files:**

  ```bash
  eventwatcher search_logs --term "ERROR" --config path/to/config.toml
  ```

### 8. Restart the Daemon

Restart the running daemon.

```bash
eventwatcher restart --config path/to/config.toml
```

---

## Configuration Files

EventWatcher requires two configuration files.

### config.toml

This file contains global settings. For example:

```toml
[database]
db_name = "/av/data/repos/eventwatcher/eventwatcher.db"
watch_groups_config = "/av/data/repos/eventwatcher/watch_groups.yaml"

[logging]
log_dir = "/av/data/repos/eventwatcher/logs"
level = "INFO"
```

### watch_groups.yaml

Defines watch groups, watch items, sample rate, and rules. For example:

```yaml
watch_groups:
  - name: "Example Group"
    watch_items:
      - "/av/data/repos/eventwatcher/*.test"
      - "/av/data/repos/eventwatcher/*.log"
    sample_rate: 60 # seconds (minimum enforced to 60)
    max_samples: 5
    max_depth: 2
    pattern: "ERROR"
    rules:
      - name: "Modified in Last 10 Minutes"
        # Evaluates the earliest modification time among files matching '*.test'
        # using the helper 'aggregate' and built-in 'min'. If this time is within 10 minutes,
        # the rule triggers.
        condition: "now - aggregate(data, '*.test', 'last_modified', min) < 10 * 60"
```

---

## Using EventWatcher as a Library

EventWatcher can be embedded in your own Python projects. The following example shows how to load the configuration, select a watch group, and run a monitoring cycle.

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load the global configuration.
config = load_config("path/to/config.toml")

# Load the watch groups configuration.
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Select the first watch group (or select by name).
group_config = watch_groups.get("watch_groups", [])[0]

# Create a Monitor instance.
monitor_instance = Monitor(
    group_config,
    db_path="/av/data/repos/eventwatcher/eventwatcher.db",
    log_dir="/av/data/repos/eventwatcher/logs",
    log_level="INFO"
)

# Run one monitoring cycle.
sample, triggered_events = monitor_instance.run_once()

print("Collected Sample:")
print(sample)
print("Triggered Events:")
print(triggered_events)
```

### Rule Evaluation in Code

When the monitor collects a sample, it evaluates rules with an extended context that includes:
- `data`: The collected sample (a dictionary with file paths as keys).
- `now`: The current epoch time.
- `aggregate`: A helper function to aggregate file metrics based on a glob pattern.
- Safe built-ins like `min`, `max`, etc.

This lets you write rule conditions like:

```yaml
condition: "now - aggregate(data, '*.test', 'last_modified', min) < 10 * 60"
```

The rule checks whether the minimum `last_modified` timestamp among files matching `*.test` is within the last 10 minutes.

---

## Database Overview

EventWatcher uses SQLite and maintains several tables:

- **events:**
  Records each triggered event with a unique event ID, watch group name, event description, the full JSON sample that triggered it, and a timestamp.

- **samples:**
  Stores the entire JSON sample collected during each monitoring cycle.

- **exploded_samples:**
  Each file or directory monitored is stored as a separate row with columns for:
  - `watch_group`
  - `sample_epoch` (timestamp of the monitoring cycle)
  - `file_path`
  - `size`
  - `last_modified`
  - `creation_time`
  - `md5`
  - `sha256`
  - `pattern_found`

This design allows you to run SQL queries to compare current metrics against historical data for advanced rule evaluation.

---

Happy monitoring!
