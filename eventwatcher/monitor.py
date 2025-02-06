import hashlib
import json
import logging
import os
import time

from eventwatcher import db, rule_helpers, rules


def compare_samples(sample1, sample2):
    """
    Compare two samples and return a list of differences.
    """
    differences = []
    for item in sample1.items():
        path, metrics = item
        if path not in sample2:
            differences.append((path, "new file"))
        else:
            for key, value in metrics.items():
                if key not in sample2[path]:
                    differences.append((path, f"missing {key}"))
                elif sample2[path][key] != value:
                    differences.append((path, f"different {key}"))

    return differences

def compute_file_md5(file_path, block_size=65536):
    """Compute MD5 hash of a file."""
    md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return None

def compute_file_sha256(file_path, block_size=65536):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None

def collect_sample(watch_group, log_dir):
    """Collect sample data for the watch group."""
    sample = {}
    sample_epoch = int(time.time())
    watch_items = watch_group.get("watch_items", [])
    pattern = watch_group.get("pattern")
    max_depth = watch_group.get("max_depth", 1)

    def scan_path(path, current_depth):
        if os.path.isfile(path):
            metrics = {}
            try:
                stat = os.stat(path)
                metrics["size"] = stat.st_size
                metrics["last_modified"] = stat.st_mtime
                metrics["creation_time"] = stat.st_ctime
                metrics["md5"] = compute_file_md5(path)
                metrics["sha256"] = compute_file_sha256(path)
                metrics["user_id"] = stat.st_uid
                metrics["group_id"] = stat.st_gid
                metrics["mode"] = oct(stat.st_mode & 0o777)
                if pattern:
                    with open(path, "r", errors="ignore") as f:
                        content = f.read()
                    metrics["pattern_found"] = pattern in content
                else:
                    metrics["pattern_found"] = False
                sample[path] = metrics
            except Exception as e:
                logging.error(f"Error collecting sample for {path}: {e}")
        elif os.path.isdir(path) and current_depth <= max_depth:
            try:
                for entry in os.listdir(path):
                    full_path = os.path.join(path, entry)
                    scan_path(full_path, current_depth + 1)
            except Exception as e:
                logging.error(f"Error scanning directory {path}: {e}")

    for item in watch_items:
        if "*" in item or "?" in item:
            import glob
            for path in glob.glob(item):
                scan_path(path, 1)
        else:
            scan_path(item, 1)

    return sample, sample_epoch


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
            wg_name = self.watch_group.get('name', 'Unnamed')
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
                with open(test_file, 'w') as f:
                    f.write('test')
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
                console=True  # Enable console output for debugging
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
            basic_logger = logging.getLogger(f"Monitor-{self.watch_group.get('name', 'Unnamed')}")
            basic_logger.setLevel(getattr(logging, self.log_level.upper(), logging.INFO))
            return basic_logger

    def run_once(self):
        """Run one monitoring cycle."""
        try:
            self.logger.info("Starting monitoring cycle.")
            sample, sample_epoch = collect_sample(self.watch_group, self.log_dir)
            watch_group_name = self.watch_group.get("name", "Unnamed")

            # Get previous sample
            previous_sample = db.get_last_n_samples(self.db_path, watch_group_name)

            # Insert current sample records
            for file_path, file_data in sample.items():
                try:
                    db.insert_sample_record(
                        self.db_path,
                        watch_group_name,
                        sample_epoch,
                        file_path,
                        file_data
                    )
                except Exception as e:
                    self.logger.error(f"Error inserting sample record: {e}")

            # Log raw sample in DEBUG mode
            if self.logger.getEffectiveLevel() <= logging.DEBUG:
                self.logger.debug(f"Raw sample JSON: {json.dumps(sample, indent=2)}")

            if not previous_sample:
                self.logger.info("No previous sample found; skipping rule evaluation.")
                return sample, []

            # Compare samples
            diff = compare_samples(sample, previous_sample)
            if diff:
                self.logger.debug(f"Found differences: {diff}")
            else:
                self.logger.info("No differences found.")

            # Evaluate rules
            now = int(time.time())
            context = {
                "data": sample,
                "now": now,
                "aggregate": rule_helpers.aggregate_metric,
            }

            triggered = rules.evaluate_rules(self.watch_group.get("rules", []), context)
            triggered_events = []

            # Process triggered rules
            for event in triggered:
                try:
                    rule_name = event.get("name")
                    event_type = event.get("event_type")
                    severity = event.get("severity")
                    affected_files = event.get("affected_files", [])

                    for file_path in affected_files:
                        # Check for duplicate events
                        prev_event = db.get_last_event_for_rule(
                            self.db_path,
                            watch_group_name,
                            rule_name,
                            file_path
                        )

                        if prev_event:
                            prev_sample = db.get_sample_record(
                                self.db_path,
                                watch_group_name,
                                prev_event["sample_epoch"],
                                file_path
                            )
                            current_metrics = sample.get(file_path, {})

                            if prev_sample and (
                                prev_sample.get("md5") == current_metrics.get("md5") and
                                prev_sample.get("last_modified") == current_metrics.get("last_modified")
                            ):
                                self.logger.info(f"Skipping duplicate event for {file_path} under rule '{rule_name}'")
                                continue

                        # Insert event
                        db.insert_event(
                            self.db_path,
                            watch_group_name,
                            rule_name,
                            sample_epoch,
                            event_type=event_type,
                            severity=severity,
                            affected_files=[file_path]
                        )

                        triggered_events.append({
                            "rule": rule_name,
                            "event_type": event_type,
                            "severity": severity,
                            "affected_file": file_path,
                            "sample_epoch": sample_epoch
                        })

                except Exception as e:
                    self.logger.error(f"Error processing rule {event.get('name', 'unknown')}: {e}")

            self.logger.info("Monitoring cycle completed.")
            return sample, triggered_events
        except Exception as e:
            print(f"Error in run_once: {e}")
            import traceback
            traceback.print_exc()
            raise

    def run(self):
        """Run the monitor continuously."""
        while not self._stop:
            try:
                self.run_once()
                sample_rate = max(self.watch_group.get("sample_rate", 60), 60)  # Minimum 60 seconds
                time.sleep(sample_rate)
            except Exception as e:
                self.logger.error(f"Error in monitor run loop: {e}")
                time.sleep(60)  # Wait before retrying

    def stop(self):
        """Stop the monitor."""
        self._stop = True
        self.logger.info("Monitor stopping.")
