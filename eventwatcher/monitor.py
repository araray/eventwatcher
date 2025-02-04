import os
import time
import hashlib
import logging
import json
from eventwatcher import db, rules, rule_helpers

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
    """
    Collect sample data for the watch group.
    Returns a tuple: (sample dict, sample_epoch)
    """
    sample = {}
    sample_epoch = int(time.time())
    watch_items = watch_group.get("watch_items", [])
    pattern = watch_group.get("pattern")  # Optional string to search within files.
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
                metrics["mode"] =  oct(stat.st_mode & 0o777)
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
        self.watch_group = watch_group
        self.db_path = db_path
        self.log_dir = log_dir
        self.log_level = log_level
        self.logger = self.setup_logger(log_level)
        self._stop = False

    def setup_logger(self, log_level):
        from eventwatcher import logger as event_logger
        file_name = f"{self.watch_group.get('name', 'Unnamed').replace(' ', '_')}.log"
        return event_logger.setup_logger(
            f"Monitor-{self.watch_group.get('name', 'Unnamed')}",
            self.log_dir,
            file_name,
            level=getattr(logging, log_level.upper(), logging.INFO),
            console=True
        )

    def run_once(self):
        self.logger.info("Starting monitoring cycle.")
        sample, sample_epoch = collect_sample(self.watch_group, self.log_dir)
        watch_group_name = self.watch_group.get("name", "Unnamed")

        # Insert per-file records into the samples table.
        for file_path, file_data in sample.items():
            db.insert_sample_record(self.db_path, watch_group_name, sample_epoch, file_path, file_data)

        # When in DEBUG mode, log the raw JSON sample.
        if self.logger.getEffectiveLevel() <= logging.DEBUG:
            self.logger.debug(f"Raw sample JSON: {json.dumps(sample, indent=2)}")

        # If there is no previous sample, skip rule evaluation.
        if not db.has_previous_sample(self.db_path, watch_group_name):
            self.logger.info("No previous sample found; skipping rule evaluation for this cycle.")
            self.logger.info("Monitoring cycle completed.")
            return sample, []  # Return an empty list of events.

        now = int(time.time())
        context = {
            "data": sample,
            "now": now,
            "aggregate": rule_helpers.aggregate_metric,
        }

        triggered = rules.evaluate_rules(self.watch_group.get("rules", []), context)
        triggered_events = []

        # Process each triggered rule and insert one event per affected file.
        for event in triggered:
            rule_name = event.get("name")
            event_type = event.get("event_type")
            severity = event.get("severity")
            affected_files = event.get("affected_files", [])
            for file_path in affected_files:
                # Deduplication: skip if the same event was already inserted for this file.
                prev_event = db.get_last_event_for_rule(self.db_path, watch_group_name, rule_name, file_path)
                if prev_event:
                    prev_sample = db.get_sample_record(self.db_path, watch_group_name, prev_event["sample_epoch"], file_path)
                    current_metrics = sample.get(file_path, {})
                    if prev_sample and (prev_sample.get("md5") == current_metrics.get("md5") and
                                        prev_sample.get("last_modified") == current_metrics.get("last_modified")):
                        self.logger.info(f"Skipping duplicate event for {file_path} under rule '{rule_name}'.")
                        continue
                # Insert an event for this file.
                db.insert_event(self.db_path, watch_group_name, rule_name, sample_epoch,
                                event_type=event_type, severity=severity, affected_files=[file_path])
                triggered_events.append({
                    "rule": rule_name,
                    "event_type": event_type,
                    "severity": severity,
                    "affected_file": file_path,
                    "sample_epoch": sample_epoch
                })

        self.logger.info("Monitoring cycle completed.")
        return sample, triggered_events

    def run(self):
        while not self._stop:
            self.run_once()
            sample_rate = self.watch_group.get("sample_rate", 60)
            time.sleep(sample_rate)

    def stop(self):
        self._stop = True
