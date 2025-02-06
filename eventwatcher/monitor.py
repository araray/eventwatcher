import concurrent.futures
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Set

from eventwatcher import db, rule_helpers


@dataclass
class DirectoryMetrics:
    """Container for directory metrics with timeout handling."""
    total_size: int = -1
    files_count: int = -1
    subdirs_count: int = -1
    timed_out: bool = False
    children: Set[str] = None

    def __post_init__(self):
        if self.children is None:
            self.children = set()


def get_dir_metrics(path: str, timeout_seconds: float, explode: bool = False) -> DirectoryMetrics:
    """
    Calculate directory metrics with timeout handling.

    Args:
        path: Directory path to analyze
        timeout_seconds: Maximum time to spend analyzing
        explode: Whether to collect child paths for directory explosion

    Returns:
        DirectoryMetrics object with collected metrics
    """
    metrics = DirectoryMetrics()

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_collect_dir_metrics, path, explode)
            result = future.result(timeout=timeout_seconds)
            if result:
                metrics.total_size = result[0]
                metrics.files_count = result[1]
                metrics.subdirs_count = result[2]
                if explode and len(result) > 3:
                    metrics.children = result[3]
    except concurrent.futures.TimeoutError:
        logging.warning(f"Directory metrics collection timed out for {path}")
        metrics.timed_out = True
    except Exception as e:
        logging.error(f"Error collecting directory metrics for {path}: {e}")

    return metrics


def _collect_dir_metrics(path: str, collect_children: bool = False) -> Optional[tuple]:
    """
    Helper function to collect directory metrics.
    Returns (total_size, files_count, subdirs_count, children_paths) or None on error.
    """
    try:
        total_size = 0
        files_count = 0
        subdirs_count = 0
        children = set() if collect_children else None

        for entry in os.scandir(path):
            try:
                if collect_children:
                    children.add(entry.path)

                if entry.is_file(follow_symlinks=False):
                    files_count += 1
                    total_size += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    subdirs_count += 1
                    # Recursively get subdirectory size
                    subdir_metrics = _collect_dir_metrics(entry.path)
                    if subdir_metrics:
                        total_size += subdir_metrics[0]
                        files_count += subdir_metrics[1]
                        subdirs_count += subdir_metrics[2]
            except (OSError, PermissionError) as e:
                logging.warning(f"Error accessing {entry.path}: {e}")
                continue

        if collect_children:
            return total_size, files_count, subdirs_count, children
        return total_size, files_count, subdirs_count
    except Exception as e:
        logging.error(f"Error in _collect_dir_metrics for {path}: {e}")
        return None


def compare_samples(current: dict, previous: dict) -> dict:
    """
    Compare two samples with improved change detection.

    Args:
        current: Current sample data
        previous: Previous sample data

    Returns:
        Dict containing differences categorized by type
    """
    differences = {
        'new': [],
        'removed': [],
        'modified': {}
    }

    # Find new and modified items
    for path, curr_metrics in current.items():
        if path not in previous:
            differences['new'].append(path)
        else:
            prev_metrics = previous[path]
            changes = {}

            # Compare all metrics except sample-specific ones
            skip_fields = {'sample_epoch'}
            for key, curr_value in curr_metrics.items():
                if key not in skip_fields:
                    prev_value = prev_metrics.get(key)
                    if curr_value != prev_value:
                        changes[key] = {
                            'old': prev_value,
                            'new': curr_value
                        }

            if changes:
                differences['modified'][path] = changes

    # Find removed items
    for path in previous:
        if path not in current:
            differences['removed'].append(path)

    return differences


def get_event_type(changes, item_type="file"):
    """
    Determine specific event type based on the changes detected.

    Args:
        changes (dict): Changes detected for the item
        item_type (str): Either "file" or "directory"

    Args:
        changes (dict): Changes detected for a specific file/directory

    Returns:
        str: Detailed event type description
    """
    event_types = []

    for field, change in changes.items():
        if item_type == "file":
            if field == "size":
                event_types.append("size_changed")
            elif field == "last_modified":
                event_types.append("content_modified")
            elif field == "pattern_found":
                old_val = change.get("old", False)
                new_val = change.get("new", False)
                if not old_val and new_val:
                    event_types.append("pattern_found")
                elif old_val and not new_val:
                    event_types.append("pattern_removed")
            elif field in ("md5", "sha256"):
                event_types.append("content_changed")
        else:  # directory
            if field == "file_count":
                event_types.append("files_changed")
            elif field == "dir_count":
                event_types.append("subdirs_changed")
            elif field == "total_size":
                event_types.append("dir_size_changed")

    if not event_types:
        return "unknown_modification"

    return ",".join(sorted(set(event_types)))


def evaluate_rule_for_file(rule, context, file_path, sample, previous_sample):
    """
    Evaluate a rule for a specific file, checking if it actually changed.

    Args:
        rule (dict): Rule configuration
        context (dict): Evaluation context
        file_path (str): Path to the file being evaluated
        sample (dict): Current sample data
        previous_sample (dict): Previous sample data

    Returns:
        tuple: (triggered, event_type)
    """
    # First check if the file actually changed
    if file_path not in sample or (
        previous_sample
        and file_path in previous_sample
        and all(
            sample[file_path].get(k) == previous_sample[file_path].get(k)
            for k in sample[file_path]
            if k != "sample_epoch"
        )
    ):
        return False, None

    # Now evaluate the rule condition
    file_context = context.copy()
    file_context["file"] = sample.get(file_path, {})
    file_context["prev_file"] = (
        previous_sample.get(file_path, {}) if previous_sample else {}
    )

    try:
        triggered = eval(
            rule["condition"], rule_helpers.build_safe_eval_context(), file_context
        )
    except Exception as e:
        logging.error(f"Error evaluating rule for file {file_path}: {e}")
        return False, None

    if not triggered:
        return False, None

    # Determine the specific type of change
    changes = {}
    if previous_sample and file_path in previous_sample:
        for key, value in sample[file_path].items():
            if key != "sample_epoch" and value != previous_sample[file_path].get(key):
                changes[key] = {
                    "old": previous_sample[file_path].get(key),
                    "new": value,
                }

    event_type = get_event_type(changes) if changes else "created"
    return True, event_type


def compute_file_md5(file_path, block_size=65536):
    """Compute MD5 hash of a file."""
    md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(block_size), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return None


def compute_file_sha256(file_path, block_size=65536):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(block_size), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


def collect_sample(watch_group: dict, log_dir: str) -> Tuple[dict, int]:
    """
    Collect sample data for the watch group with improved directory handling
    and directory explosion support.

    Args:
        watch_group: Watch group configuration
        log_dir: Directory for logs

    Returns:
        Tuple of (sample_data, sample_epoch)
    """
    sample = {}
    sample_epoch = int(time.time())

    # Get configuration
    sample_rate = watch_group.get("sample_rate", 60)
    timeout_fraction = watch_group.get("dir_scan_timeout_fraction", 0.5)
    timeout_seconds = max(1, sample_rate * timeout_fraction)
    max_depth = watch_group.get("max_depth", 1)
    explode_dirs = watch_group.get("explode_directories", False)

    def scan_path(base_path: str, current_depth: int) -> None:
        try:
            # Handle glob patterns
            if any(c in base_path for c in ["*", "?", "["]):
                import glob
                paths = glob.glob(base_path)
            else:
                paths = [base_path]

            for path in paths:
                try:
                    if not os.path.exists(path):
                        continue

                    stat = os.stat(path)
                    is_directory = os.path.isdir(path)

                    # Base metrics for both files and directories
                    metrics = {
                        "type": "directory" if is_directory else "file",
                        "last_modified": stat.st_mtime,
                        "creation_time": stat.st_ctime,
                        "user_id": stat.st_uid,
                        "group_id": stat.st_gid,
                        "mode": stat.st_mode,
                        "is_dir": is_directory
                    }

                    if is_directory:
                        # Collect directory metrics with explosion if configured
                        dir_metrics = get_dir_metrics(path, timeout_seconds, explode_dirs)
                        metrics.update({
                            "size": dir_metrics.total_size,
                            "files_count": dir_metrics.files_count,
                            "subdirs_count": dir_metrics.subdirs_count
                        })

                        # Add the directory entry to samples
                        sample[path] = metrics

                        # Handle directory explosion
                        if explode_dirs and dir_metrics.children and current_depth < max_depth:
                            for child_path in dir_metrics.children:
                                scan_path(child_path, current_depth + 1)
                    else:
                        # File-specific metrics
                        metrics.update({
                            "size": stat.st_size,
                            "md5": compute_file_md5(path),
                            "sha256": compute_file_sha256(path),
                            "pattern_found": check_pattern(path, watch_group.get("pattern"))
                        })
                        sample[path] = metrics

                except OSError as e:
                    logging.error(f"Error accessing path {path}: {e}")

        except Exception as e:
            logging.error(f"Error processing path {base_path}: {e}")

    # Process each watch item
    for item in watch_group.get("watch_items", []):
        scan_path(item, 1)

    return sample, sample_epoch


def check_pattern(file_path: str, pattern: Optional[str]) -> Optional[bool]:
    """Check if a pattern exists in a file."""
    if not pattern:
        return None

    try:
        with open(file_path, "r", errors="ignore") as f:
            content = f.read()
            return pattern in content
    except Exception as e:
        logging.error(f"Error checking pattern in {file_path}: {e}")
        return None


class Monitor:
    def __init__(self, watch_group, db_path, log_dir, log_level="INFO"):
        """
        Initialize a monitor instance.

        Args:
            watch_group (dict): Watch group configuration
            db_path (str): Path to the database file
            log_dir (str): Base directory for logs
            log_level (str): Logging level
        """
        self.watch_group = watch_group
        self.db_path = db_path
        self.log_dir = os.path.abspath(log_dir)
        self.log_level = log_level
        self._stop = False

        # Print debug info before setting up logger
        print(f"Monitor init - Watch group: {watch_group.get('name')}")
        print(f"Monitor init - Log dir: {self.log_dir}")
        print(f"Monitor init - Log level: {self.log_level}")

        self.logger = self.setup_logger()

    def setup_logger(self):
        """Set up logging for this monitor instance."""
        try:
            from eventwatcher import logger as event_logger

            # Create watch group specific log directory if using subdirectories
            wg_name = self.watch_group.get("name", "Unnamed")
            print(f"Setting up logger for watch group: {wg_name}")

            # Ensure log directory exists
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Ensured log directory exists: {self.log_dir}")

            # Create log filename from watch group name
            log_filename = f"{wg_name.replace(' ', '_').replace('/', '_')}.log"
            print(f"Log filename: {log_filename}")

            # Test write permissions
            test_file = os.path.join(self.log_dir, ".test_write")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                print("Successfully tested write permissions")
            except Exception as e:
                print(f"Warning: Write permission test failed: {e}")

            # Set up the logger
            monitor_logger = event_logger.setup_logger(
                f"Monitor-{wg_name}",
                self.log_dir,
                log_filename,
                level=getattr(logging, self.log_level.upper(), logging.INFO),
                console=True,  # Enable console output for debugging
            )

            # Log initial setup
            monitor_logger.info(f"Initialized monitor for watch group: {wg_name}")
            monitor_logger.info(f"Log directory: {self.log_dir}")
            monitor_logger.info(f"Log file: {log_filename}")

            return monitor_logger

        except Exception as e:
            # Print the full error
            import traceback

            print(f"Failed to setup monitor logger: {e}")
            print("Full traceback:")
            traceback.print_exc()

            # Fallback to basic logging if setup fails
            basic_logger = logging.getLogger(
                f"Monitor-{self.watch_group.get('name', 'Unnamed')}"
            )
            basic_logger.setLevel(
                getattr(logging, self.log_level.upper(), logging.INFO)
            )
            return basic_logger

    def run_once(self):
        """Run one monitoring cycle."""
        try:
            self.logger.info("Starting monitoring cycle.")
            sample, sample_epoch = collect_sample(self.watch_group, self.log_dir)
            watch_group_name = self.watch_group.get("name", "Unnamed")

            # Get previous sample
            previous_sample = db.get_last_n_samples(self.db_path, watch_group_name)

            # Compare samples and get detailed differences
            if previous_sample:
                differences = compare_samples(sample, previous_sample)
                if (
                    differences["new"]
                    or differences["removed"]
                    or differences["modified"]
                ):
                    self.logger.debug(
                        f"Found differences: {json.dumps(differences, indent=2)}"
                    )

                    # Log removals specifically
                    if differences["removed"]:
                        self.logger.info(
                            f"Detected removed files: {differences['removed']}"
                        )
                else:
                    self.logger.info("No differences found.")
            else:
                differences = {"new": [], "removed": [], "modified": {}}
                self.logger.info("No previous sample found.")

            # Insert current sample records
            for file_path, file_data in sample.items():
                try:
                    db.insert_sample_record(
                        self.db_path,
                        watch_group_name,
                        sample_epoch,
                        file_path,
                        file_data,
                    )
                except Exception as e:
                    self.logger.error(f"Error inserting sample record: {e}")

            if not previous_sample:
                self.logger.info("No previous sample found; skipping rule evaluation.")
                return sample, []

            # Compare samples and get detailed differences
            differences = compare_samples(sample, previous_sample)
            if differences["new"] or differences["removed"] or differences["modified"]:
                self.logger.debug(
                    f"Found differences: {json.dumps(differences, indent=2)}"
                )
            else:
                self.logger.info("No differences found.")

            # Evaluate rules
            now = int(time.time())
            context = {
                "data": sample,
                "now": now,
                "aggregate": rule_helpers.aggregate_metric,
                "differences": differences,
            }

            triggered_events = []

            # Process each rule
            for rule in self.watch_group.get("rules", []):
                affected_files = set()

                # Check new files
                for file_path in differences["new"]:
                    triggered, event_type = evaluate_rule_for_file(
                        rule, context, file_path, sample, previous_sample
                    )
                    if triggered:
                        affected_files.add((file_path, event_type or "created"))

                # Check modified files
                for file_path in differences["modified"]:
                    triggered, event_type = evaluate_rule_for_file(
                        rule, context, file_path, sample, previous_sample
                    )
                    if triggered:
                        affected_files.add((file_path, event_type or "modified"))

                # Check removed files
                for file_path in differences["removed"]:
                    # Special handling for removed files since they're not in current sample
                    file_context = context.copy()
                    file_context["file"] = previous_sample.get(file_path, {})
                    try:
                        triggered = eval(
                            rule["condition"],
                            rule_helpers.build_safe_eval_context(),
                            file_context,
                        )
                        if triggered:
                            affected_files.add((file_path, "removed"))
                    except Exception as e:
                        self.logger.error(
                            f"Error evaluating rule for removed file {file_path}: {e}"
                        )

                # Create events for affected files
                for file_path, event_type in affected_files:
                    try:
                        # Insert event with specific event type
                        db.insert_event(
                            self.db_path,
                            watch_group_name,
                            rule["name"],
                            sample_epoch,
                            event_type=event_type,
                            severity=rule.get("severity"),
                            affected_files=[file_path],
                        )

                        triggered_events.append(
                            {
                                "rule": rule["name"],
                                "event_type": event_type,
                                "severity": rule.get("severity"),
                                "affected_file": file_path,
                                "sample_epoch": sample_epoch,
                            }
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error creating event for {file_path} under rule '{rule.get('name')}': {e}"
                        )

            self.logger.info("Monitoring cycle completed.")
            return sample, triggered_events

        except Exception as e:
            self.logger.error(f"Error in run_once: {str(e)}", exc_info=True)
            raise

    def run(self):
        """Run the monitor continuously."""
        while not self._stop:
            try:
                self.run_once()
                sample_rate = max(
                    self.watch_group.get("sample_rate", 60), 60
                )  # Minimum 60 seconds
                time.sleep(sample_rate)
            except Exception as e:
                self.logger.error(f"Error in monitor run loop: {e}")
                time.sleep(60)  # Wait before retrying

    def stop(self):
        """Stop the monitor."""
        self._stop = True
        self.logger.info("Monitor stopping.")
