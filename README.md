# EventWatcher

EventWatcher is a simple Python library and CLI tool for monitoring files and directories
for predefined events. It supports configuration via TOML files and YAML watch group configuration.
It can run as a daemon (using `python-daemon`) or in the foreground.

## Features

- **Configuration:** Use TOML for global settings and YAML for watch group definitions.
- **Monitoring:** Monitor files/directories (supports glob patterns) and collect detailed information
  (MD5, SHA256, size, owner, timestamps, etc.).
- **Event Evaluation:** Define rules (using logical/arithmetic expressions) to trigger events.
- **Data Storage:** Logs all data to a SQLite database.
- **CLI Interface:** Manage configuration, database, and monitoring via a user-friendly CLI.
- **Daemon Support:** Run as a daemon with systemd integration.
- **Unix-friendly:** Designed with KISS, composability, and piping in mind.

## Installation

Install via pip (or setup your environment accordingly):

```bash
pip install .
```

## Usage

### Command Line

Display the current configuration:

```bash
eventwatcher show-config --config path/to/config.toml
```

Initialize the database:

```bash
eventwatcher init-db --config path/to/config.toml
```

Run one monitoring sample:

```bash
eventwatcher monitor-once --config path/to/config.toml
```

Start the service (daemon mode):

```bash
eventwatcher start --config path/to/config.toml
```

Or run in the foreground (useful for testing):

```bash
eventwatcher start --foreground --config path/to/config.toml
```

### As a Library

```python
from eventwatcher.config import load_config, load_watch_groups_config
from eventwatcher.monitor import Monitor

# Load configuration
config = load_config("path/to/config.toml")
watch_groups = load_watch_groups_config(config.get("watch_groups_config", "watch_groups.yaml"))

# Create a Monitor instance for a specific watch group:
group_config = watch_groups.get("watch_groups", [])[0]
monitor = Monitor(group_config, db_path="path/to/eventwatcher.db")
sample, events = monitor.run_once()
```

## Configuration

### Main Configuration (TOML)

Example `config.toml`:

```toml
[database]
db_name = "eventwatcher.db"

watch_groups_config = "watch_groups.yaml"

[logging]
log_dir = "logs"
```

### Watch Groups Configuration (YAML)

Example `watch_groups.yaml`:

```yaml
watch_groups:
  - name: "Example Group"
    watch_items:
      - "/path/to/watch"
      - "/another/path/*.log"
    sample_rate: 60  # seconds (minimum enforced to 60)
    max_samples: 5
    max_depth: 2
    pattern: "ERROR"
    rules:
      - name: "Error Detected"
        condition: "'pattern_found' in data.get('/path/to/watch', {}) and data['/path/to/watch']['pattern_found']"
```

## Systemd Service Example

Create a file `/etc/systemd/system/eventwatcher.service` with the following content:

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

## Running Tests

Run unit tests with:

```bash
pytest
```

## License

MIT License.
