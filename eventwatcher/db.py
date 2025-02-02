import sqlite3
import os
import json
import uuid

def get_db_connection(db_path):
    """
    Get a SQLite3 connection.

    Args:
        db_path (str): The path to the database file.

    Returns:
        sqlite3.Connection: A database connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """
    Initialize the SQLite database with the required tables.

    This function creates the 'events' and 'samples' tables if they do not exist.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uid TEXT NOT NULL,
            watch_group TEXT NOT NULL,
            event TEXT NOT NULL,
            event_type TEXT,
            severity TEXT,
            affected_files TEXT,
            timestamp_diff TEXT,
            sample_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_uid)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_group TEXT NOT NULL,
            sample TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def init_exploded_samples(db_path):
    """
    Initialize the 'exploded_samples' table for storing individual file metrics.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS exploded_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_group TEXT NOT NULL,
            sample_epoch INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            size INTEGER,
            last_modified REAL,
            creation_time REAL,
            md5 TEXT,
            sha256 TEXT,
            pattern_found BOOLEAN
        )
    ''')
    conn.commit()
    conn.close()

def insert_event(db_path, watch_group, event, sample_data,
                 event_type=None, severity=None, affected_files=None, timestamp_diff=None):
    """
    Insert an event record into the database with structured metadata.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        event (str): Event name/description.
        sample_data (dict): The sample data triggering the event.
        event_type (str): Type of event (e.g., created, modified, deleted, pattern_match).
        severity (str): Severity level (e.g., INFO, WARNING, CRITICAL).
        affected_files (list): List of file paths that triggered the event.
        timestamp_diff (dict): Differences in timestamp (e.g., modification delta) for affected files.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    event_uid = str(uuid.uuid4())
    cur.execute('''
        INSERT INTO events (event_uid, watch_group, event, event_type, severity, affected_files, timestamp_diff, sample_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_uid,
        watch_group,
        event,
        event_type,
        severity,
        json.dumps(affected_files),
        json.dumps(timestamp_diff),
        json.dumps(sample_data)
    ))
    conn.commit()
    conn.close()

def insert_sample(db_path, watch_group, sample):
    """
    Insert a sample record into the database.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        sample (dict): The collected sample data.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO samples (watch_group, sample)
        VALUES (?, ?)
    ''', (watch_group, json.dumps(sample)))
    conn.commit()
    conn.close()

def insert_exploded_sample(db_path, watch_group, sample_epoch, file_path, file_data):
    """
    Insert an individual file's data into the exploded_samples table.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        sample_epoch (int): The epoch timestamp representing this sample cycle.
        file_path (str): The file or directory path.
        file_data (dict): The metrics collected for the file.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO exploded_samples (
            watch_group, sample_epoch, file_path, size, last_modified,
            creation_time, md5, sha256, pattern_found
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        watch_group,
        sample_epoch,
        file_path,
        file_data.get("size"),
        file_data.get("last_modified"),
        file_data.get("creation_time"),
        file_data.get("md5"),
        file_data.get("sha256"),
        file_data.get("pattern_found")
    ))
    conn.commit()
    conn.close()

def get_last_sample(db_path, watch_group):
    """
    Retrieve the most recent sample for a given watch group.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.

    Returns:
        tuple: (sample (dict), timestamp (str)) if found; otherwise (None, None)
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT sample, timestamp FROM samples WHERE watch_group = ? ORDER BY timestamp DESC LIMIT 1", (watch_group,))
    row = cur.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), row[1]
    return None, None
