import os
import hashlib
import pwd
import grp
import time
import glob
import logging
from . import db
from . import logger
from eventwatcher.rule_helpers import aggregate_metric, get_previous_metric



def collect_dir_files_info(dir_path, max_depth=None, pattern=None):
    """
    Recursively traverse a directory up to max_depth and collect file metrics individually.

    Args:
        dir_path (str): Directory to traverse.
        max_depth (int, optional): Maximum depth to traverse.
        pattern (str, optional): Pattern to search for in files.

    Returns:
        dict: Mapping file paths to their collected information.
    """
    files_info = {}

    def _traverse(current_path, current_depth):
        if max_depth is not None and current_depth > max_depth:
            return
        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    full_path = entry.path
                    if entry.is_file():
                        files_info[full_path] = collect_file_info(full_path, pattern)
                    elif entry.is_dir():
                        _traverse(full_path, current_depth + 1)
        except Exception as e:
            files_info[current_path] = {"error": str(e)}

    _traverse(dir_path, 0)
    return files_info

def compute_diff(prev_sample, curr_sample):
    """
    Compute differences between previous and current samples.

    Returns a dict with keys:
      - "created": files present in current sample but not in previous.
      - "deleted": files present in previous sample but missing in current.
      - "modified": files present in both but with differences.
    For modified files, if 'last_modified' changed, the delta is computed.

    Args:
        prev_sample (dict): Previous sample data.
        curr_sample (dict): Current sample data.

    Returns:
        dict: Diff results.
    """
    diff = {"created": {}, "deleted": {}, "modified": {}}
    prev_files = set(prev_sample.keys()) if prev_sample else set()
    curr_files = set(curr_sample.keys())

    # Files created:
    for file in curr_files - prev_files:
        diff["created"][file] = curr_sample[file]

    # Files deleted:
    for file in prev_files - curr_files:
        diff["deleted"][file] = prev_sample[file]

    # Files modified:
    for file in prev_files & curr_files:
        prev_info = prev_sample.get(file, {})
        curr_info = curr_sample.get(file, {})
        changes = {}
        for key in ["size", "last_modified", "creation_time", "md5", "sha256", "pattern_found"]:
            if prev_info.get(key) != curr_info.get(key):
                # For timestamps, we show the delta.
                if key == "last_modified" and prev_info.get(key) and curr_info.get(key):
                    changes[key] = curr_info.get(key) - prev_info.get(key)
                else:
                    changes[key] = {"from": prev_info.get(key), "to": curr_info.get(key)}
        if changes:
            diff["modified"][file] = changes

    # Remove empty categories
    diff = {k: v for k, v in diff.items() if v}
    return diff

def compute_hashes(file_path):
    """
    Compute the MD5 and SHA256 hashes for a file.

    Args:
        file_path (str): Path to the file.

    Returns:
        tuple: (md5_hash, sha256_hash) as hexadecimal strings.
    """
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
            sha256_hash.update(chunk)
    return md5_hash.hexdigest(), sha256_hash.hexdigest()

def collect_file_info(file_path, pattern=None):
    """
    Collect information for a given file.
    """
    info = {}
    try:
        stats = os.stat(file_path)
        info['size'] = stats.st_size
        info['owner'] = pwd.getpwuid(stats.st_uid).pw_name
        info['group'] = grp.getgrgid(stats.st_gid).gr_name
        info['last_modified'] = stats.st_mtime
        info['creation_time'] = stats.st_ctime
        md5, sha256 = compute_hashes(file_path)
        info['md5'] = md5
        info['sha256'] = sha256

        if pattern:
            info['pattern_found'] = False
            with open(file_path, "r", errors="ignore") as f:
                for line in f:
                    if pattern in line:
                        info['pattern_found'] = True
                        break
    except Exception as e:
        info['error'] = str(e)
    return info

def collect_dir_info(dir_path, max_depth=None):
    """
    Collect aggregated information for a directory (without per‑file details).
    """
    info = {
        'file_count': 0,
        'directory_count': 0,
        'files': [],
        'directories': []
    }

    def _traverse(current_path, current_depth):
        if max_depth is not None and current_depth > max_depth:
            return
        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    if entry.is_file():
                        info['file_count'] += 1
                        info['files'].append(entry.path)
                    elif entry.is_dir():
                        info['directory_count'] += 1
                        info['directories'].append(entry.path)
                        _traverse(entry.path, current_depth + 1)
        except Exception as e:
            info.setdefault('errors', []).append({current_path: str(e)})
    _traverse(dir_path, 0)
    return info

class Monitor:
    """
    Monitor class to watch directories/files based on a given configuration.
    """
    def __init__(self, watch_group, db_path, log_dir, log_level="INFO"):
        """
        Initialize the Monitor.
        """
        self.watch_group = watch_group
        self.db_path = db_path
        self.sample_rate = max(watch_group.get('sample_rate', 60), 60)
        self.max_samples = watch_group.get('max_samples', 5)
        self.max_depth = watch_group.get('max_depth', None)
        self.pattern = watch_group.get('pattern', None)
        self.explode_directories = watch_group.get("explode_directories", False)
        self.watch_items = watch_group.get('watch_items', [])
        self.running = False
        # Set up a logger for this watch group
        log_filename = f"{self.watch_group.get('name', 'Unnamed').replace(' ', '_')}.log"
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger = logger.setup_logger(self.watch_group.get('name', 'Unnamed'), log_dir, log_filename, level=numeric_level)

    def take_sample(self):
        """
        Take a single sample for all watch items.
        """
        sample = {}
        for item in self.watch_items:
            resolved_paths = glob.glob(item)
            if not resolved_paths:
                sample[item] = {'error': 'No matching file or directory found'}
            for path in resolved_paths:
                if os.path.isfile(path):
                    sample[path] = collect_file_info(path, self.pattern)
                elif os.path.isdir(path):
                    if self.explode_directories:
                        # Use per‑file granularity
                        dir_files = collect_dir_files_info(path, self.max_depth, self.pattern)
                        sample.update(dir_files)
                    else:
                        sample[path] = collect_dir_info(path, self.max_depth)
                else:
                    sample[path] = {'error': 'Not a file or directory'}
        return sample

    def evaluate_rules(self, sample, diff_result):
        """
        Evaluate rules defined in the watch group against the collected sample.
        The evaluation context includes the current sample, previous sample differences,
        and helper functions so that rules can compare against historical data.

        Returns:
            list: A list of triggered event dictionaries with extra metadata.
        """
        triggered = []
        rules = self.watch_group.get('rules', [])
        current_time = time.time()
        eval_context = {
            "data": sample,
            "diff": diff_result,
            "now": current_time,
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "aggregate": aggregate_metric,
            "get_previous_metric": lambda pattern, metric: get_previous_metric(
                self.db_path,
                self.watch_group.get('name', 'Unnamed'),
                pattern,
                metric
            ),
            "compute_diff": compute_diff
        }
        for rule in rules:
            condition = rule.get('condition')
            event_name = rule.get('name', 'Unnamed Event')
            try:
                self.logger.debug(f"Evaluating rule '{event_name}': now={current_time}, "
                                  f"min_last_modified={aggregate_metric(sample, '*', 'last_modified', min)}")
                condition_result = eval(condition, {"__builtins__": {}}, eval_context)
                self.logger.debug(f"Condition '{condition}' evaluated to {condition_result}")
                if condition and condition_result:
                    triggered.append({"rule": rule, "diff": diff_result})

            except Exception as e:
                self.logger.error(f"Error evaluating rule '{event_name}': {e}")
        return triggered

    def run_once(self):
        """
        Perform one monitoring cycle:
          - Retrieve the previous sample.
          - Collect the current sample.
          - Compute the diff.
          - Evaluate rules with access to the diff.
          - Log the sample and triggered events.
          - Store the sample and each triggered event with structured metadata.

        Returns:
            tuple: (sample, list_of_triggered_events)
        """
        watch_group_name = self.watch_group.get('name', 'Unnamed')
        prev_sample, _ = db.get_last_sample(self.db_path, watch_group_name)
        current_sample = self.take_sample()
        diff_result = compute_diff(prev_sample, current_sample) if prev_sample else {}
        events = self.evaluate_rules(current_sample, diff_result)
        self.logger.info(f"Sample: {current_sample}")
        if events:
            self.logger.info(f"Triggered events: {events}")
        else:
            self.logger.info("No events triggered.")

        # Store the full JSON sample in the samples table.
        db.insert_sample(self.db_path, watch_group_name, current_sample)

        # Store exploded sample entries for each file (if available).
        sample_epoch = int(time.time())
        for file_path, file_data in current_sample.items():
            if isinstance(file_data, dict) and "error" not in file_data:
                db.insert_exploded_sample(
                    self.db_path,
                    watch_group_name,
                    sample_epoch,
                    file_path,
                    file_data
                )

        # Process and store events with enhanced metadata.
        for event in events:
            rule = event["rule"]
            # Determine event type from rule config or from diff analysis.
            event_type = rule.get("event_type")
            if not event_type:
                if diff_result.get("created"):
                    event_type = "created"
                elif diff_result.get("deleted"):
                    event_type = "deleted"
                elif diff_result.get("modified"):
                    event_type = "modified"
                else:
                    event_type = "pattern_match"
            severity = rule.get("severity", "INFO")
            affected_files = []
            timestamp_diff = {}
            if diff_result:
                for change_type in ["created", "deleted", "modified"]:
                    if change_type in diff_result:
                        for file, diff_values in diff_result[change_type].items():
                            affected_files.append(file)
                            if change_type == "modified" and "last_modified" in diff_values:
                                timestamp_diff[file] = diff_values["last_modified"]
            # Insert the event with all structured metadata.
            db.insert_event(
                self.db_path,
                watch_group_name,
                rule.get("name", "Unnamed Event"),
                current_sample,
                event_type,
                severity,
                affected_files,
                timestamp_diff
            )
        return current_sample, events

    def run(self):
        """
        Run the monitoring loop indefinitely based on the sample rate.
        """
        self.running = True
        self.logger.info(f"Starting monitor for group '{self.watch_group.get('name', 'Unnamed')}' with sample rate {self.sample_rate} seconds.")
        while self.running:
            self.run_once()
            time.sleep(self.sample_rate)

    def stop(self):
        """
        Stop the monitoring loop.
        """
        self.running = False
        self.logger.info(f"Stopping monitor for group '{self.watch_group.get('name', 'Unnamed')}'.")
