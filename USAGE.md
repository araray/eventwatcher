# USAGE Guide for EventWatcher

This guide explains how to use EventWatcher as both a command-line tool and as a library. The latest release of EventWatcher includes advanced features such as differential analysis, structured event metadata, per-file directory explosion, and flexible rule evaluation.

---

## Overview

EventWatcher is a Python-based tool that monitors files and directories for changes based on user-defined rules. In this release, EventWatcher has been enhanced with:

- **Differential Analysis:**
  Each monitoring cycle compares the current sample with the previous one to detect exactly what has changed (e.g., new files, deleted files, or modifications with detailed deltas such as changes in file size or modification time).

- **Structured Event Metadata:**
  Events now include structured information with additional fields:
  - **Event Type:** e.g., `created`, `modified`, `deleted`, or `pattern_match`.
  - **Severity Level:** e.g., `INFO`, `WARNING`, or `CRITICAL`.
  - **Affected File(s):** Only the files that triggered the event.
  - **Timestamp Differences:** The computed delta (e.g., change in last modified time) for affected files.

- **Per-File Directory Explosion:**
  With the new configuration option `explode_directories`, directories can be scanned recursively (up to a configurable maximum depth) so that each file is recorded individually with detailed metrics (size, last modified, creation time, MD5, SHA256, and pattern detection). If disabled, directories will be stored as aggregated snapshots.

- **Flexible Rule Evaluation:**
  Rule conditions can now refer to both the current sample and historical data (via the computed diff). The evaluation context provides:
  - `data`: The current sample (a mapping of file paths to their metrics).
  - `diff`: The computed differences between the previous and current samples.
  - `now`: The current epoch time.
  - Helper functions such as `aggregate`, `get_previous_metric`, and `compute_diff`.

---

## CLI Commands

EventWatcher comes with several CLI commands:

1. **Display the Loaded Configuration:**

   ```bash
   eventwatcher show-config --config path/to/config.toml
   ```

2. **Initialize the Database:**

   This command creates the necessary tables, including the updated `events` table with structured metadata.

   ```bash
   eventwatcher init-db --config path/to/config.toml
   ```

3. **Run a Single Monitoring Cycle:**

   Collects a sample from all watch groups, computes differences with the previous sample, evaluates rules, and stores both the full sample and any triggered events.

   ```bash
   eventwatcher monitor-once --config path/to/config.toml
   ```

4. **Start the Service:**

   - **Foreground Mode (for testing):**

     ```bash
     eventwatcher start --foreground --config path/to/config.toml
     ```

   - **Daemon Mode (recommended for production):**

     ```bash
     eventwatcher start --config path/to/config.toml
     ```

5. **Stop the Service:**

   ```bash
   eventwatcher stop --config path/to/config.toml
   ```

6. **Check Daemon Status:**

   ```bash
   eventwatcher status --config path/to/config.toml
   ```

7. **Search the Database for Events:**

   ```bash
   eventwatcher search_db --watch-group "Example Group" --config path/to/config.toml
   ```

8. **Search Through Log Files:**

   ```bash
   eventwatcher search_logs --term "ERROR" --config path/to/config.toml
   ```

9. **Restart the Daemon:**

   ```bash
   eventwatcher restart --config path/to/config.toml
   ```

---

## Configuration Files

EventWatcher requires two configuration files: one global TOML file and one watch groups YAML file.

### config.toml

The global configuration file defines settings such as the database location, logging options, and the path to the watch groups configuration.

```toml
[database]
db_name = "/av/data/repos/eventwatcher/eventwatcher.db"
watch_groups_config = "/av/data/repos/eventwatcher/watch_groups.yaml"

[logging]
log_dir = "/av/data/repos/eventwatcher/logs"
level = "INFO"
```

### watch_groups.yaml

This file defines one or more watch groups, specifying what to monitor, the sample rate, and the rules (with advanced conditions and metadata). A sample configuration is shown below:

```yaml
watch_groups:
  - name: "Example Group"
    watch_items:
      - "/av/data/repos/eventwatcher/*.test"
      - "/av/data/repos/eventwatcher/*.log"
    sample_rate: 60                # Minimum enforced to 60 seconds
    max_samples: 5
    max_depth: 2
    pattern: "ERROR"
    explode_directories: true      # Enable per-file monitoring for directories
    rules:
      - name: "Modified in Last 10 Minutes"
        event_type: "modified"     # Optional: override default event type detection
        severity: "WARNING"
        condition: "now - aggregate(data, '*.test', 'last_modified', min) < 10 * 60"
```

---

## Using EventWatcher as a Library

EventWatcher can be embedded into your Python projects. The following example demonstrates loading configurations, selecting a watch group, and running a monitoring cycle:

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load the global configuration.
config = load_config("path/to/config.toml")

# Load the watch groups configuration.
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Select a watch group (by index or by name).
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

### Rule Evaluation Context

When a monitoring cycle is run, rules are evaluated using an extended context that includes:

- **data:** The current sample (a mapping of file paths to their metrics).
- **diff:** The computed differences between the previous sample and the current sample. This contains information on created, deleted, or modified files.
- **now:** The current epoch time.
- **aggregate:** A helper function to perform aggregation (e.g., `min`, `max`).
- **get_previous_metric:** Retrieves historical metric values.
- **compute_diff:** A helper to compute differences between samples.

This context allows you to write advanced rules. For example, a rule condition could check for significant file size increases like so:

```yaml
condition: "diff.get('modified') and any(delta > 20 for file, delta in diff.get('modified', {}).items())"
```

---

## Database Overview

EventWatcher uses SQLite and maintains several tables:

- **events:**
  Each event record now includes:
  - `event_uid`
  - `watch_group`
  - `event` (the rule name/description)
  - `event_type` (e.g., created, modified, deleted, pattern_match)
  - `severity`
  - `affected_files` (a JSON list of files that triggered the event)
  - `timestamp_diff` (a JSON mapping of file paths to their timestamp deltas)
  - `sample_data` (the full JSON sample that triggered the event)
  - `timestamp`

- **samples:**
  Stores the complete JSON sample from each monitoring cycle.

- **exploded_samples:**
  Each file or directory entry is stored separately with columns for:
  - `watch_group`
  - `sample_epoch`
  - `file_path`
  - `size`
  - `last_modified`
  - `creation_time`
  - `md5`
  - `sha256`
  - `pattern_found`

This design enables detailed SQL queries and historical comparisons.
