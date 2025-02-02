import os
import hashlib
import pwd
import grp
import time
import glob

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

    Information includes size, owner, group, timestamps, and file hashes.
    Optionally, check if the file contains a specific pattern.

    Args:
        file_path (str): The file path.
        pattern (str, optional): A substring to search for within the file.

    Returns:
        dict: Collected file information.
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
            # Check if file contains a line matching the pattern.
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
    Collect information for a directory by traversing its contents.

    Recursively counts files and directories up to an optional maximum depth.

    Args:
        dir_path (str): Path to the directory.
        max_depth (int, optional): Maximum levels to traverse. If None, traverse indefinitely.

    Returns:
        dict: Directory statistics and list of contained files/directories.
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

def collect_sample(watch_item, max_depth=None, pattern=None):
    """
    Collect a sample from a watch item. The watch item can be a file path, a directory path, or a glob pattern.

    Args:
        watch_item (str): The file/directory or glob pattern.
        max_depth (int, optional): Maximum directory depth for directory scanning.
        pattern (str, optional): Pattern to search for in files.

    Returns:
        dict: A mapping from each resolved path to its collected information.
    """
    sample = {}
    # Resolve glob patterns.
    paths = glob.glob(watch_item)
    if not paths:
        sample[watch_item] = {'error': 'No matching file or directory found'}
        return sample

    for path in paths:
        if os.path.isfile(path):
            sample[path] = collect_file_info(path, pattern)
        elif os.path.isdir(path):
            sample[path] = collect_dir_info(path, max_depth)
        else:
            sample[path] = {'error': 'Not a file or directory'}
    return sample

import threading

class Monitor:
    """
    Monitor class to watch directories/files based on a given configuration.

    This class periodically collects samples, evaluates rules,
    logs the results, and records data to a SQLite database.
    """
    def __init__(self, watch_group, db_path, log_func=print):
        """
        Initialize the Monitor.

        Args:
            watch_group (dict): Configuration for the watch group.
            db_path (str): Path to the SQLite database.
            log_func (callable): Function used for logging output.
        """
        self.watch_group = watch_group
        self.db_path = db_path
        self.log = log_func
        # Enforce a minimum sample rate of 60 seconds.
        self.sample_rate = max(watch_group.get('sample_rate', 60), 60)
        self.max_samples = watch_group.get('max_samples', 5)
        self.max_depth = watch_group.get('max_depth', None)
        self.pattern = watch_group.get('pattern', None)
        self.watch_items = watch_group.get('watch_items', [])
        self.running = False

    def evaluate_rules(self, sample):
        """
        Evaluate rules defined in the watch group against the collected sample.

        Each rule is a dictionary with:
         - name: Event name.
         - condition: A Python expression as a string that is evaluated against 'data' (the sample).

        Returns:
            list: Names of events that are triggered.
        """
        triggered = []
        rules = self.watch_group.get('rules', [])
        for rule in rules:
            condition = rule.get('condition')
            event_name = rule.get('name', 'Unnamed Event')
            try:
                # For security, use a restricted eval context.
                if condition:
                    # 'data' holds the sample information.
                    if eval(condition, {"__builtins__": {}}, {"data": sample}):
                        triggered.append(event_name)
            except Exception as e:
                self.log(f"Error evaluating rule '{event_name}': {e}")
        return triggered

    def take_sample(self):
        """
        Take a single sample for all watch items.

        Returns:
            dict: Aggregated sample data.
        """
        sample = {}
        for item in self.watch_items:
            sample.update(collect_sample(item, self.max_depth, self.pattern))
        return sample

    def run_once(self):
        """
        Perform one monitoring cycle: take a sample, evaluate rules, log events, and store data in the DB.

        Returns:
            tuple: (sample, list_of_triggered_events)
        """
        sample = self.take_sample()
        events = self.evaluate_rules(sample)
        self.log(f"Sample for group '{self.watch_group.get('name', 'Unnamed')}': {sample}")
        if events:
            self.log(f"Triggered events: {events}")
        # Store sample and events in the database.
        from . import db
        db.insert_sample(self.db_path, self.watch_group.get('name', 'Unnamed'), sample)
        for event in events:
            db.insert_event(self.db_path, self.watch_group.get('name', 'Unnamed'), event, sample)
        return sample, events

    def run(self):
        """
        Run the monitoring loop indefinitely based on the sample rate.
        """
        self.running = True
        self.log(f"Starting monitor for group '{self.watch_group.get('name', 'Unnamed')}' with sample rate {self.sample_rate} seconds.")
        while self.running:
            self.run_once()
            time.sleep(self.sample_rate)

    def stop(self):
        """
        Stop the monitoring loop.
        """
        self.running = False
