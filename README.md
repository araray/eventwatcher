# EventWatcher

EventWatcher is a sophisticated Python-based monitoring tool that tracks changes in files and directories based on user-defined rules. The latest release (0.4.0) introduces advanced features such as directory-aware monitoring, differential analysis, structured event metadata, and flexible rule evaluation.

## Overview

EventWatcher is designed to provide:

- **Robust Monitoring**: Files and directories are monitored with detailed metrics including size, content hashes, timestamps, permissions, and pattern matching.
- **Directory Intelligence**: Deep directory monitoring with metrics like file count, subdirectory count, and total size.
- **Differential Analysis**: Each monitoring cycle compares current and previous samples to detect exactly what changed.
- **Structured Events**: Events contain detailed metadata about the type of change, severity, affected files/dirs, and timestamps.
- **Flexible Rules**: Rules can evaluate both current and historical data with support for complex conditions.

## Feature Details

### Monitoring System
- **File Monitoring**
  - Detailed Metrics: size, md5, sha256, modification times, ownership, permissions
  - Content Pattern Matching: configurable pattern detection within files
  - Historical Tracking: maintain configurable number of past samples
  - Change Detection: precise identification of modifications

- **Directory Monitoring**
  - Directory-specific Metrics:
    * File count tracking
    * Subdirectory enumeration
    * Total size calculation
    * Recursive monitoring with depth control
  - Content Change Tracking:
    * New/removed files detection
    * Subdirectory structure changes
    * Aggregate size modifications

- **Sample Collection**
  - Configurable sampling rate (minimum 60 seconds)
  - Depth-limited directory traversal
  - Error handling for inaccessible items
  - Resource usage optimization

### Event System
**File Events**:
- `created`: New file detected
- `removed`: File deletion
- `size_changed`: Size modification
- `content_modified`: Timestamp-based changes
- `content_changed`: Hash-based modifications
- `pattern_found`: Pattern detection
- `pattern_removed`: Pattern removal

**Directory Events**:
- `files_changed`: File count changes
- `subdirs_changed`: Subdirectory structure changes
- `dir_size_changed`: Total size modifications

### Event Database
- **Events Table**:
  - `event_uid`: Unique identifier
  - `watch_group`: Group name
  - `event`: Rule description
  - `event_type`: Specific change type
  - `severity`: Event severity level
  - `affected_files`: Changed items
  - `sample_epoch`: Timestamp

- **Samples Table**:
  - Complete state snapshots
  - File/directory metrics
  - Historical data retention

## Installation & Setup

1. **System Requirements**:
   - Python 3.11+
   - SQLite3
   - Linux/Unix environment (for daemon mode)

2. **Installation**:
   ```bash
   git clone https://github.com/araray/eventwatcher.git
   cd eventwatcher
   pip install -e .
   ```

3. **Initial Configuration**:
   Create `config.toml`:
   ```toml
   [database]
   db_name = "eventwatcher.db"
   watch_groups_config = "watch_groups.yaml"

   [logging]
   log_dir = "logs"
   level = "INFO"
   ```

4. **Watch Groups Configuration**:
   Create `watch_groups.yaml`:
   ```yaml
   watch_groups:
     - name: "Critical Files"
       watch_items:
         - "/path/to/critical/*.log"
         - "/path/to/important/dir"
       sample_rate: 60
       max_samples: 5
       max_depth: 2
       pattern: "ERROR|FATAL"
       rules:
         - name: "Directory Growth Alert"
           condition: |
             file.get('type') == 'directory' and
             file.get('file_count', 0) > prev_file.get('file_count', 0) * 1.5
           severity: "WARNING"

         - name: "Critical Content Change"
           condition: |
             file.get('type') == 'file' and
             'content_changed' in differences.get('modified', {}).get(file_path, {})
           severity: "CRITICAL"
   ```

## CLI Usage

### Basic Commands
```bash
# Initialize database
eventwatcher init-db --config path/to/config.toml

# Show current configuration
eventwatcher show-config --config path/to/config.toml

# Run one monitoring cycle
eventwatcher monitor-once --config path/to/config.toml
```

### Service Management
```bash
# Start in foreground (testing)
eventwatcher start --foreground --config path/to/config.toml

# Start as daemon
eventwatcher start --config path/to/config.toml

# Check status
eventwatcher status --config path/to/config.toml

# Stop service
eventwatcher stop --config path/to/config.toml
```

### Data Access
```bash
# View events
eventwatcher show-events --watch-group "Critical Files" --format json

# Search logs
eventwatcher search_logs --term "ERROR" --config path/to/config.toml

# Execute custom query
eventwatcher query "SELECT * FROM events WHERE severity='CRITICAL'"
```

## Rule Evaluation Context

Rules have access to:
- `data`: Current sample data
- `file`: Current file/directory metrics
- `prev_file`: Previous metrics
- `differences`: Structured change information
- `now`: Current epoch time
- Helper functions:
  * `aggregate`: Metric aggregation
  * `get_previous_metric`: Historical data access

## Development

### Testing
```bash
# Install test dependencies
pip install -e ".[test]"

# Run test suite
pytest tests/

# Run specific test module
pytest tests/test_monitor.py
```

### Code Style
- Follow PEP 8
- Use type hints
- Include docstrings
- Write unit tests for new features

## Systemd Integration

Sample systemd service file (`eventwatcher.service`):
```ini
[Unit]
Description=EventWatcher Service
After=network.target

[Service]
ExecStart=/usr/local/bin/eventwatcher start
Restart=on-failure
User=eventwatcher
Environment=EVENTWATCHER_CONFIG_DIR=/etc/eventwatcher

[Install]
WantedBy=multi-user.target
```

## Performance Considerations

- Set appropriate `sample_rate` (minimum 60s)
- Use `max_depth` to limit directory scanning
- Configure `max_samples` based on storage capacity
- Use specific `watch_items` paths
- Monitor log size and rotation

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Ensure all tests pass
5. Submit a pull request with detailed description
