# EventWatcher

EventWatcher is a versatile Python library and CLI tool that monitors files and directories for changes and events based on user‐defined rules. It supports configuration via TOML (for global settings) and YAML (for watch groups), runs as a daemon or in the foreground, and stores detailed sample data in a SQLite database.

This version includes an improved event system and rule evaluation framework. It allows you to write rules that reference file metrics through glob patterns rather than hardcoded file paths. In addition, samples are "exploded" into a dedicated database table to support advanced, SQL‐based comparisons and historical queries.

---

## Table of Contents

1. [Features](#features)
2. [Installation](#installation)
3. [Configuration](#configuration)
   - [Main Configuration (TOML)](#main-configuration-toml)
   - [Watch Groups Configuration (YAML)](#watch-groups-configuration-yaml)
4. [Usage](#usage)
   - [Command-Line Interface (CLI)](#command-line-interface-cli)
   - [As a Library](#as-a-library)
5. [Rule Evaluation Enhancements](#rule-evaluation-enhancements)
6. [Database Structure](#database-structure)
7. [Systemd Service](#systemd-service)
8. [Testing](#testing)
9. [Future Improvements](#future-improvements)
10. [License](#license)

---

## Features

- **Flexible Configuration:**
  - Global settings in a TOML file.
  - Watch groups defined in YAML for easy, human‐readable rules.

- **Robust Monitoring:**
  - Monitor files and directories using glob patterns.
  - Collect detailed information including size, timestamps, file hashes, and pattern matches.

- **Enhanced Rule Evaluation:**
  - Write flexible rules that can aggregate metrics over file sets.
  - Use a safe evaluation context with helper functions (e.g., `aggregate`) and trusted built-in functions like `min`, `max`, etc.

- **Data Storage & Advanced Querying:**
  - Full samples are logged as JSON.
  - Exploded samples (one row per file/directory per sample cycle) enable SQL‐based comparisons.

- **CLI and Daemon Support:**
  - A rich command-line interface for management.
  - Daemon mode with systemd integration for continuous monitoring.

---

## Installation

Clone the repository and install via pip:

```bash
git clone <repository_url>
cd eventwatcher
pip install .
```

Alternatively, if the package is published to PyPI:

```bash
pip install eventwatcher
```

---

## Configuration

EventWatcher uses two configuration files: one for global settings and another for watch group definitions.

### Main Configuration (TOML)

The main configuration file (`config.toml`) specifies settings such as the database file, logging directory, and the path to your watch groups configuration.

Example `config.toml`:

```toml
[database]
db_name = "eventwatcher.db"

watch_groups_config = "watch_groups.yaml"

[logging]
log_dir = "logs"
level = "INFO"
```

### Watch Groups Configuration (YAML)

The watch groups configuration file (`watch_groups.yaml`) defines one or more groups, each with its own watch items, sampling rate, rules, and optional settings such as maximum depth and search patterns.

Example `watch_groups.yaml`:

```yaml
watch_groups:
  - name: "Example Group"
    watch_items:
      - "/path/to/monitor/*.test"
      - "/path/to/monitor/*.log"
    sample_rate: 60  # Minimum enforced sample rate is 60 seconds.
    max_samples: 5
    max_depth: 2
    pattern: "ERROR"
    rules:
      - name: "Modified in Last 10 Minutes"
        # This rule triggers if the earliest last_modified timestamp among files matching '*.test'
        # is less than 10 minutes ago.
        condition: "now - aggregate(data, '*.test', 'last_modified', min) < 10 * 60"
```

---

## Usage

### Command-Line Interface (CLI)

EventWatcher comes with a CLI tool that provides several commands:

- **show-config:**
  Display the currently loaded configuration.

  ```bash
  eventwatcher show-config --config path/to/config.toml
  ```

- **init-db:**
  Initialize the SQLite database (creates tables such as `events`, `samples`, and `exploded_samples`).

  ```bash
  eventwatcher init-db --config path/to/config.toml
  ```

- **monitor-once:**
  Run a single monitoring cycle (sample).

  ```bash
  eventwatcher monitor-once --config path/to/config.toml
  ```

- **start:**
  Start the monitoring service. Use `--foreground` to run in the foreground.

  ```bash
  eventwatcher start --config path/to/config.toml
  eventwatcher start --foreground --config path/to/config.toml
  ```

- **stop:**
  Stop the running daemon.

  ```bash
  eventwatcher stop --config path/to/config.toml
  ```

- **status:**
  Check the status of the daemon.

  ```bash
  eventwatcher status --config path/to/config.toml
  ```

- **search_db:**
  Query stored events from the database.

  ```bash
  eventwatcher search_db --watch-group "Example Group" --config path/to/config.toml
  ```

- **search_logs:**
  Search log files for a specified term.

  ```bash
  eventwatcher search_logs --term "ERROR" --config path/to/config.toml
  ```

- **restart:**
  Restart the daemon.

  ```bash
  eventwatcher restart --config path/to/config.toml
  ```

- **show_db:**
  Display all events stored in the database.

  ```bash
  eventwatcher show_db --config path/to/config.toml
  ```

### As a Library

You can also use EventWatcher programmatically in your own projects:

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load global configuration and watch groups.
config = load_config("path/to/config.toml")
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Select a watch group.
group_config = watch_groups.get("watch_groups", [])[0]

# Create a Monitor instance.
monitor_instance = Monitor(
    group_config,
    db_path="path/to/eventwatcher.db",
    log_dir="logs",
    log_level="INFO"
)

# Run one monitoring cycle.
sample, events = monitor_instance.run_once()
print("Sample:", sample)
print("Triggered Events:", events)
```

---

## Rule Evaluation Enhancements

The rule evaluation system has been upgraded to support more flexible and abstract expressions. Key changes include:

- **Glob Pattern Matching:**
  Instead of hardcoding file paths, you can now use glob patterns to reference files in a watch group.

- **Helper Functions:**
  The `aggregate` helper function (defined in `eventwatcher/rule_helpers.py`) aggregates a specified metric from files matching a glob pattern. For example, to get the minimum `last_modified` value among all files matching `*.test`, you can use:

  ```python
  aggregate(data, '*.test', 'last_modified', min)
  ```

- **Safe Evaluation Context:**
  The evaluation context passed to `eval()` includes only safe built-ins (such as `min`, `max`, `sum`, and `len`) along with our helper functions. This provides both flexibility and security.

Example rule configuration:

```yaml
rules:
  - name: "Modified in Last 10 Minutes"
    condition: "now - aggregate(data, '*.test', 'last_modified', min) < 10 * 60"
```

---

## Database Structure

EventWatcher uses SQLite to store both full JSON samples and exploded file metrics for advanced querying.

- **events:**
  Stores triggered events along with a unique event ID, watch group name, event description, full JSON sample, and timestamp.

- **samples:**
  Records the complete JSON sample for each monitoring cycle.

- **exploded_samples:**
  Each file or directory from a sample cycle is stored as an individual row. This table includes columns for:
  - `watch_group`
  - `sample_epoch` (the timestamp when the sample was taken)
  - `file_path`
  - `size`
  - `last_modified`
  - `creation_time`
  - `md5`
  - `sha256`
  - `pattern_found`

These exploded samples enable SQL-based analysis to compare current and historical metrics.

---

## Systemd Service

To run EventWatcher as a daemon, you can use a systemd service file. Create a file at `/etc/systemd/system/eventwatcher.service` with the following content:

```ini
[Unit]
Description=EventWatcher Service
After=network.target

[Service]
ExecStart=/usr/local/bin/eventwatcher start
Restart=on-failure
User=youruser
Environment=EVENTWATCHER_CONFIG_DIR=/path/to/config/dir

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:

```bash
sudo systemctl enable eventwatcher
sudo systemctl start eventwatcher
```

---

## Testing

Automated tests are provided using pytest. To run the test suite:

```bash
pytest
```

The tests cover configuration loading, database operations, CLI commands, and monitor functionality.

---

## Future Improvements

- **Event Deduplication:**
  Mechanisms to avoid repeated alerts for the same event condition will be added in future versions.

- **Advanced SQL-Based Rule Evaluation:**
  With exploded samples, more sophisticated SQL queries and historical comparisons can be implemented directly in rules.

- **Automated Sample Cleanup:**
  Strategies for pruning older samples while preserving full logs may be developed.

---

## License

EventWatcher is released under the [MIT License](LICENSE).

---

## Contact

For questions, issues, or contributions, please open an issue on the GitHub repository or contact the author.

Happy monitoring!
