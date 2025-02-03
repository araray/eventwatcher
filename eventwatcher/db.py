import sqlite3
import os
import json
import uuid

def get_db_connection(db_path):
    """
    Get a SQLite3 connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """
    Initialize the SQLite database with the required tables.
    Creates the 'events' table and the 'samples' table (formerly exploded_samples).
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Create events table (storing only key information)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
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
        )
    ''')

    # Create samples table (per-file detailed records)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS samples (
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

def insert_event(db_path, watch_group, event, sample_epoch,
                 event_type=None, severity=None, affected_files=None):
    """
    Insert an event record into the events table.
    Instead of storing raw sample data, we store the sample_epoch and affected files.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    event_uid = str(uuid.uuid4())
    cur.execute('''
        INSERT INTO events (event_uid, watch_group, event, event_type, severity, affected_files, sample_epoch)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_uid,
        watch_group,
        event,
        event_type,
        severity,
        json.dumps(affected_files),
        sample_epoch
    ))
    conn.commit()
    conn.close()

def insert_sample_record(db_path, watch_group, sample_epoch, file_path, file_data):
    """
    Insert an individual file's data into the samples table.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO samples (
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

def get_last_event_for_rule(db_path, watch_group, rule_name, file_path):
    """
    Retrieve the most recent event for a given watch_group, rule (event description), and file.
    Returns a dict with event data or None if not found.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    query = '''
        SELECT * FROM events
        WHERE watch_group = ? AND event = ?
        ORDER BY sample_epoch DESC LIMIT 1
    '''
    cur.execute(query, (watch_group, rule_name))
    row = cur.fetchone()
    conn.close()
    if row:
        # Check if the file_path is in affected_files
        affected_files = json.loads(row['affected_files'])
        if file_path in affected_files:
            return dict(row)
    return None

def get_sample_record(db_path, watch_group, sample_epoch, file_path):
    """
    Retrieve the sample record for a given watch_group, sample_epoch, and file_path.
    Returns a dict with sample data or None if not found.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    query = '''
        SELECT * FROM samples
        WHERE watch_group = ? AND sample_epoch = ? AND file_path = ?
        LIMIT 1
    '''
    cur.execute(query, (watch_group, sample_epoch, file_path))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
