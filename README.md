# EventWatcher

EventWatcher is a Python-based file and directory monitoring tool that detects changes based on user-defined rules. It supports both command-line interface (CLI) and library usage. In its latest release, EventWatcher has been significantly enhanced with advanced features such as differential analysis, structured event metadata, per-file directory explosion, and flexible rule evaluation.

## Features

- **Differential Analysis:**
  Compares the current sample with the previous one to detect detailed changes. This includes:
  - Detecting new, deleted, or modified files.
  - Reporting specific deltas (e.g., file size changes or modifications in file timestamps).

- **Structured Event Metadata:**
  Events are now recorded with rich metadata, including:
  - **Event Type:** e.g., `created`, `modified`, `deleted`, or `pattern_match`.
  - **Severity Level:** e.g., `INFO`, `WARNING`, or `CRITICAL`.
  - **Affected Files:** A list of files that triggered the event.
  - **Timestamp Differences:** Computed deltas for modifications (for example, changes in `last_modified` time).

- **Per-File Directory Explosion:**
  With the new configuration option `explode_directories`, directories can be scanned recursively (up to a configurable maximum depth) so that each file is recorded individually with detailed metrics such as size, last modified, creation time, MD5, SHA256, and pattern detection. When disabled, directories are stored as aggregated snapshots.

- **Flexible Rule Evaluation:**
  Rule conditions are evaluated in an extended context that includes:
  - The current sample (`data`).
  - The computed differences between the previous and current samples (`diff`).
  - The current timestamp (`now`).
  - Helper functions like `aggregate`, `get_previous_metric`, and `compute_diff` for advanced rule conditions.

- **Daemon Mode:**
  Run EventWatcher as a background service with auto-reload capability upon configuration changes.

- **Comprehensive Logging and Database Storage:**
  All samples and events are logged and stored in an SQLite database for later analysis and querying.

## Installation

To install EventWatcher, clone the repository and install the dependencies using pip:

```bash
git clone https://github.com/araray/eventwatcher.git
cd eventwatcher
pip install .
```

The project requires Python 3.11 or higher.

## Usage

### Command-Line Interface (CLI)

EventWatcher provides several CLI commands to manage monitoring, configuration, and the database.

- **Show Loaded Configuration:**

  ```bash
  eventwatcher show-config --config path/to/config.toml
  ```

- **Initialize the Database:**

  This command creates the necessary tables—including the enhanced `events` table with structured metadata.

  ```bash
  eventwatcher init-db --config path/to/config.toml
  ```

- **Run a Single Monitoring Cycle:**

  Collects a sample from all watch groups, computes differences with the previous sample, evaluates rules, and stores both the full sample and any triggered events.

  ```bash
  eventwatcher monitor-once --config path/to/config.toml
  ```

- **Start the Service:**

  - **Foreground mode (for testing):**

    ```bash
    eventwatcher start --foreground --config path/to/config.toml
    ```

  - **Daemon mode (for production):**

    ```bash
    eventwatcher start --config path/to/config.toml
    ```

- **Stop the Service:**

  ```bash
  eventwatcher stop --config path/to/config.toml
  ```

- **Check Service Status:**

  ```bash
  eventwatcher status --config path/to/config.toml
  ```

- **Search the Database:**

  ```bash
  eventwatcher search_db --watch-group "Example Group" --config path/to/config.toml
  ```

- **Search Logs:**

  ```bash
  eventwatcher search_logs --term "ERROR" --config path/to/config.toml
  ```

- **Restart the Service:**

  ```bash
  eventwatcher restart --config path/to/config.toml
  ```

For a detailed guide on using EventWatcher, please refer to [USAGE.md](USAGE.md).

### Library Usage

You can also integrate EventWatcher into your own Python projects:

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load configurations.
config = load_config("path/to/config.toml")
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Select a watch group.
group_config = watch_groups.get("watch_groups", [])[0]

# Create a Monitor instance.
monitor_instance = Monitor(
    group_config,
    db_path="/path/to/eventwatcher.db",
    log_dir="/path/to/logs",
    log_level="INFO"
)

# Run one monitoring cycle.
sample, events = monitor_instance.run_once()

print("Collected Sample:")
print(sample)
print("Triggered Events:")
print(events)
```

## Configuration

EventWatcher requires two configuration files: a global TOML file and a watch groups YAML file.

### Global Configuration (`config.toml`)

This file defines settings such as the database location, logging options, and the path to the watch groups configuration.

```toml
[database]
db_name = "/path/to/eventwatcher.db"
watch_groups_config = "/path/to/watch_groups.yaml"

[logging]
log_dir = "/path/to/logs"
level = "INFO"
```

### Watch Groups Configuration (`watch_groups.yaml`)

This file defines one or more watch groups, specifying what to monitor, the sample rate, and the rules (with advanced conditions and metadata).

```yaml
watch_groups:
  - name: "Example Group"
    watch_items:
      - "/path/to/*.test"
      - "/path/to/*.log"
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

For further details on configuration and rule syntax, see [USAGE.md](USAGE.md).

## Database Schema

EventWatcher uses an SQLite database with the following tables:

- **events:**
  Contains structured event records with fields such as:
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
  Stores complete JSON samples from each monitoring cycle.

- **exploded_samples:**
  Stores individual file records (if directory explosion is enabled) with detailed metrics such as size, last modified time, creation time, and cryptographic hashes.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request. Ensure that your changes are accompanied by relevant tests and updated documentation.

## License

EventWatcher is licensed under the [MIT License](LICENSE).
