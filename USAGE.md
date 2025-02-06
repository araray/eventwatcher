# USAGE Guide for EventWatcher

This guide explains how to use EventWatcher as both a command-line tool and as a library. The latest release of EventWatcher includes advanced features such as directory-aware monitoring, differential analysis, structured event metadata, and flexible rule evaluation.

---

## Overview

EventWatcher is a Python-based tool that monitors files and directories for changes based on user-defined rules. In this release, EventWatcher has been enhanced with:

- **Differential Analysis:**
  Each monitoring cycle compares the current sample with the previous one to detect exactly what has changed, including:
  - Added or removed files/directories
  - Modified content
  - Directory structure changes
  - File count and size variations

- **Structured Event Metadata:**
  Events now include structured information with additional fields:
  - **Event Type:**
    * File events: `created`, `removed`, `size_changed`, `content_modified`, `content_changed`, `pattern_found`, `pattern_removed`
    * Directory events: `files_changed`, `subdirs_changed`, `dir_size_changed`
  - **Severity Level:** e.g., `INFO`, `WARNING`, or `CRITICAL`
  - **Affected Items:** Only the files/directories that triggered the event
  - **Change Details:** Computed differences for affected items

- **Directory Monitoring:**
  Directories are now first-class citizens with:
  - File count tracking
  - Subdirectory enumeration
  - Total size monitoring
  - Recursive change detection
  - Depth-controlled scanning

- **Flexible Rule Evaluation:**
  Rule conditions can now refer to both current and historical data. The evaluation context provides:
  - `data`: The current sample mapping
  - `file`: Current file/directory metrics
  - `prev_file`: Previous metrics for comparison
  - `differences`: Structured change information
  - `now`: Current epoch time
  - Helper functions: `aggregate`, `get_previous_metric`

---

## CLI Commands

EventWatcher comes with several CLI commands:

1. **Display the Loaded Configuration:**
   ```bash
   eventwatcher show-config --config path/to/config.toml
   ```

2. **Initialize the Database:**
   Creates the necessary tables with the enhanced schema:
   ```bash
   eventwatcher init-db --config path/to/config.toml
   ```

3. **Run a Single Monitoring Cycle:**
   ```bash
   eventwatcher monitor-once --config path/to/config.toml
   ```

4. **Start the Service:**
   ```bash
   # Foreground Mode (testing)
   eventwatcher start --foreground --config path/to/config.toml

   # Daemon Mode (production)
   eventwatcher start --config path/to/config.toml
   ```

5. **Service Management:**
   ```bash
   # Stop Service
   eventwatcher stop --config path/to/config.toml

   # Check Status
   eventwatcher status --config path/to/config.toml

   # Restart Service
   eventwatcher restart --config path/to/config.toml
   ```

6. **Data Access:**
   ```bash
   # Search Events
   eventwatcher search_db --watch-group "Example Group" --config path/to/config.toml

   # Search Logs
   eventwatcher search_logs --term "ERROR" --config path/to/config.toml

   # Custom Queries
   eventwatcher query "SELECT * FROM events WHERE severity='CRITICAL'"
   ```

---

## Configuration Files

EventWatcher requires two configuration files: a global TOML file and a watch groups YAML file.

### config.toml

The global configuration file defines settings such as database location, logging options, and watch groups configuration path:

```toml
[database]
db_name = "/path/to/eventwatcher.db"
watch_groups_config = "/path/to/watch_groups.yaml"

[logging]
log_dir = "/path/to/logs"
level = "INFO"
```

### watch_groups.yaml

This file defines watch groups, specifying what to monitor and the rules for event generation:

```yaml
watch_groups:
  - name: "Critical Systems"
    watch_items:
      - "/var/log/*.log"
      - "/opt/application/data"
    sample_rate: 60
    max_samples: 5
    max_depth: 2
    pattern: "ERROR|FATAL"
    rules:
      # File-specific rules
      - name: "Critical File Modified"
        condition: |
          file.get('type') == 'file' and
          'content_changed' in differences.get('modified', {}).get(file_path, {})
        severity: "CRITICAL"

      # Directory monitoring rules
      - name: "Directory Growth Alert"
        condition: |
          file.get('type') == 'directory' and
          file.get('file_count', 0) > prev_file.get('file_count', 0) * 1.5
        severity: "WARNING"

      # Pattern detection rules
      - name: "Error Pattern Found"
        condition: |
          file.get('type') == 'file' and
          file.get('pattern_found', False)
        severity: "WARNING"

      # Size-based rules
      - name: "Large Directory Growth"
        condition: |
          file.get('type') == 'directory' and
          file.get('total_size', 0) > prev_file.get('total_size', 0) + 1024 * 1024 * 100
        severity: "WARNING"
```

---

## Using EventWatcher as a Library

EventWatcher can be embedded into your Python projects. Here's a comprehensive example:

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor
from eventwatcher.thread_manager import ThreadManager
import json

# Load configurations
config = load_config("path/to/config.toml")
watch_groups = load_watch_groups_config(config.get("watch_groups_config"))

# Create a thread manager
manager = ThreadManager()

# Initialize monitors for each watch group
monitors = []
for group_config in watch_groups.get("watch_groups", []):
    monitor = Monitor(
        group_config,
        db_path="/path/to/eventwatcher.db",
        log_dir="/path/to/logs",
        log_level="INFO"
    )
    monitors.append(monitor)

    # Create and register a monitoring thread
    thread = threading.Thread(
        target=monitor.run,
        name=f"Monitor-{group_config['name']}"
    )
    thread.daemon = True
    manager.register_thread(thread)
    thread.start()

# Run monitoring and handle events
try:
    while True:
        for monitor in monitors:
            sample, events = monitor.run_once()

            if events:
                print(f"Detected changes in {monitor.watch_group['name']}:")
                print(json.dumps(events, indent=2))

                # Access specific event details
                for event in events:
                    if event['event_type'] == 'files_changed':
                        print(f"Directory contents changed: {event['affected_file']}")
                    elif 'content_changed' in event['event_type']:
                        print(f"File modified: {event['affected_file']}")

        time.sleep(60)  # Wait before next cycle

except KeyboardInterrupt:
    # Clean shutdown
    manager.stop_and_join_all()
```

## Database Overview

EventWatcher uses SQLite with an enhanced schema:

### Events Table
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid TEXT NOT NULL,
    watch_group TEXT NOT NULL,
    event TEXT NOT NULL,
    event_type TEXT,
    severity TEXT,
    affected_files TEXT,
    sample_epoch INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_uid)
);
```

### Samples Table
```sql
CREATE TABLE samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_group TEXT NOT NULL,
    sample_epoch INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    type TEXT NOT NULL,
    size INTEGER,
    file_count INTEGER,
    dir_count INTEGER,
    total_size INTEGER,
    user_id INTEGER,
    group_id INTEGER,
    mode INTEGER,
    last_modified REAL,
    creation_time REAL,
    md5 TEXT,
    sha256 TEXT,
    pattern_found BOOLEAN
);
```

## Performance Considerations

1. **Sampling Rate:**
   - Minimum enforced to 60 seconds
   - Adjust based on system resources and monitoring needs

2. **Directory Scanning:**
   - Use `max_depth` to limit recursion
   - Consider file system performance
   - Monitor I/O impact

3. **Database Management:**
   - Configure `max_samples` appropriately
   - Consider periodic cleanup
   - Monitor database size

4. **Pattern Matching:**
   - Use efficient patterns
   - Consider file sizes when pattern matching
   - Monitor CPU usage

5. **Memory Usage:**
   - Large directories may require significant memory
   - Monitor process memory consumption
   - Consider limiting watch scope

## Troubleshooting

1. **Common Issues:**
   - Permission denied: Ensure proper file system permissions
   - High CPU usage: Adjust sample rate or pattern complexity
   - Database locks: Check for concurrent access
   - Memory issues: Review watch scope and depth

2. **Logging:**
   - Check logs in configured log directory
   - Use DEBUG level for detailed information
   - Monitor log rotation

3. **Debugging:**
   - Use foreground mode for testing
   - Enable DEBUG logging
   - Monitor process status
   - Use query commands for database inspection
