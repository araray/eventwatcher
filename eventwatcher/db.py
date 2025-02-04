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
    Creates the 'events' table and the 'samples' table.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Create events table
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

    # Create samples table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_group TEXT NOT NULL,
            sample_epoch INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            size INTEGER,
            user_id INTEGER,
            group_id INTEGER,
            mode INTEGER,
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
            watch_group, sample_epoch, file_path, size,
            user_id, group_id, mode, last_modified,
            creation_time, md5, sha256, pattern_found
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        watch_group,
        sample_epoch,
        file_path,
        file_data.get("size"),
        file_data.get("user_id"),
        file_data.get("group_id"),
        file_data.get("mode"),
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
    Retrieve the most recent event for a given watch_group, rule and file.
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

def get_last_n_sample_epochs(db_path, watch_group, n_samples = 1):
    """
    Retrieve the last N sample epochs for a given watch_group.
    Returns a list of sample_epoch values.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    query = '''
        SELECT DISTINCT sample_epoch FROM samples
        WHERE watch_group = ?
        ORDER BY sample_epoch DESC
        LIMIT ?
    '''
    cur.execute(query, (watch_group, n_samples))
    rows = cur.fetchall()
    conn.close()
    return [row['sample_epoch'] for row in rows]

def get_last_n_samples(db_path, watch_group, file_path = None, n_samples = 1):
    """
    Retrieve the sample record for a given watch_group, sample_epoch, and file_path.
    Returns a dict with sample data or None if not found.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    epochs = get_last_n_sample_epochs(db_path, watch_group, n_samples)
    if not epochs:
        return []

    epochs_str = ', '.join(map(str, epochs))

    if file_path is None:
        query = '''
            SELECT * FROM samples
            WHERE watch_group = ?
            AND sample_epoch IN (?)
            ORDER BY sample_epoch DESC
        '''
        cur.execute(query, (watch_group, epochs_str))
    else:
        query = '''
            SELECT * FROM samples
            WHERE watch_group = ?
            AND file_path = ?
            AND sample_epoch IN (?)
            ORDER BY sample_epoch DESC
        '''
        cur.execute(query, (watch_group, file_path, epochs_str))

    # # Debugging: Print the query and parameters
    # print("SQL Query:", query)
    # print("Query Params:", (watch_group, epochs))

    rows = cur.fetchall()
    conn.close()
    if rows:
        samples = {}
        for row in rows:
            metrics = {}
            metrics['size'] = row['size']
            metrics['user_id'] = row['user_id']
            metrics['group_id'] = row['group_id']
            metrics['mode'] = row['mode']
            metrics['last_modified'] = row['last_modified']
            metrics['creation_time'] = row['creation_time']
            metrics['md5'] = row['md5']
            metrics['sha256'] = row['sha256']
            metrics['pattern_found'] = row['pattern_found']
            metrics['sample_epoch'] = row['sample_epoch']
            samples[row['file_path']] = metrics
        return samples
    return None

def has_previous_sample(db_path, watch_group):
    """
    Check if there is any previous sample data for the given watch group.
    Returns True if at least one record exists; otherwise False.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM samples WHERE watch_group = ?', (watch_group,))
    count = cur.fetchone()[0]
    conn.close()
    return count > 1
