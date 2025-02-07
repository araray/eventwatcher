import json
import os
import sqlite3
import uuid


def get_db_connection(db_path):
    """
    Get a SQLite3 connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_db_schema(db_path: str):
    """
    Migrate database schema to support new directory fields.
    Should be called from init_db() for new databases and can be
    run manually for existing ones.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # Check if columns exist first
        cur.execute("PRAGMA table_info(samples)")
        columns = {col[1] for col in cur.fetchall()}

        # Add new columns if they don't exist
        if "is_dir" not in columns:
            cur.execute("ALTER TABLE samples ADD COLUMN is_dir BOOLEAN")
        if "files_count" not in columns:
            cur.execute("ALTER TABLE samples ADD COLUMN files_count INTEGER")
        if "subdirs_count" not in columns:
            cur.execute("ALTER TABLE samples ADD COLUMN subdirs_count INTEGER")

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()


def init_db(db_path: str):
    """
    Initialize the SQLite database with the required tables.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create events table
    cur.execute(
        """
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
    """
    )

    # Create samples table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_group TEXT NOT NULL,
            sample_epoch INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            type TEXT NOT NULL,
            size INTEGER,
            user_id INTEGER,
            group_id INTEGER,
            mode INTEGER,
            last_modified REAL,
            creation_time REAL,
            md5 TEXT,
            sha256 TEXT,
            pattern_found BOOLEAN,
            is_dir BOOLEAN,
            files_count INTEGER,
            subdirs_count INTEGER
        )
    """
    )

    conn.commit()
    conn.close()


def insert_event(
    db_path,
    watch_group,
    event,
    sample_epoch,
    event_type=None,
    severity=None,
    affected_files=None,
):
    """
    Insert an event record into the events table.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    event_uid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO events (event_uid, watch_group, event, event_type, severity, affected_files, sample_epoch)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            event_uid,
            watch_group,
            event,
            event_type,
            severity,
            json.dumps(affected_files),
            sample_epoch,
        ),
    )
    conn.commit()
    conn.close()


def insert_sample_record(
    db_path: str, watch_group: str, sample_epoch: int, file_path: str, file_data: dict
):
    """
    Insert a sample record with full metrics support.

    Args:
        db_path: Path to the SQLite database
        watch_group: Name of the watch group
        sample_epoch: Timestamp of the sample
        file_path: Path to the file/directory
        file_data: Dictionary containing file/directory metrics
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO samples (
                watch_group, sample_epoch, file_path, type,
                size, user_id, group_id, mode,
                last_modified, creation_time, md5, sha256,
                pattern_found, is_dir, files_count, subdirs_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                watch_group,
                sample_epoch,
                file_path,
                file_data.get("type"),
                file_data.get("size"),
                file_data.get("user_id"),
                file_data.get("group_id"),
                file_data.get("mode"),
                file_data.get("last_modified"),
                file_data.get("creation_time"),
                file_data.get("md5"),
                file_data.get("sha256"),
                file_data.get("pattern_found"),
                file_data.get("is_dir", False),
                file_data.get("files_count"),
                file_data.get("subdirs_count"),
            ),
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()


def get_last_event_for_rule(db_path, watch_group, rule_name, file_path):
    """
    Retrieve the most recent event for a given watch_group, rule and file.
    Returns a dict with event data or None if not found.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    query = """
        SELECT * FROM events
        WHERE watch_group = ? AND event = ?
        ORDER BY sample_epoch DESC LIMIT 1
    """
    cur.execute(query, (watch_group, rule_name))
    row = cur.fetchone()
    conn.close()
    if row:
        affected_files = json.loads(row["affected_files"])
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
    query = """
        SELECT * FROM samples
        WHERE watch_group = ? AND sample_epoch = ? AND file_path = ?
        LIMIT 1
    """
    cur.execute(query, (watch_group, sample_epoch, file_path))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_last_n_sample_epochs(db_path, watch_group, n_samples=1):
    """
    Retrieve the last N sample epochs for a given watch_group.
    Returns a list of sample_epoch values.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    query = """
        SELECT DISTINCT sample_epoch FROM samples
        WHERE watch_group = ?
        ORDER BY sample_epoch DESC
        LIMIT ?
    """
    cur.execute(query, (watch_group, n_samples))
    rows = cur.fetchall()
    conn.close()
    return [row["sample_epoch"] for row in rows]


def get_last_n_samples(db_path, watch_group, file_path=None, n_samples=1):
    """
    Retrieve the sample record for a given watch_group, sample_epoch, and file_path.
    Returns a dict with sample data or None if not found.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    epochs = get_last_n_sample_epochs(db_path, watch_group, n_samples)
    if not epochs:
        return []

    epochs_str = ", ".join(map(str, epochs))

    if file_path is None:
        query = """
            SELECT * FROM samples
            WHERE watch_group = ?
            AND sample_epoch IN (?)
            ORDER BY sample_epoch DESC
        """
        cur.execute(query, (watch_group, epochs_str))
    else:
        query = """
            SELECT * FROM samples
            WHERE watch_group = ?
            AND file_path = ?
            AND sample_epoch IN (?)
            ORDER BY sample_epoch DESC
        """
        cur.execute(query, (watch_group, file_path, epochs_str))

    rows = cur.fetchall()
    conn.close()
    if rows:
        samples = {}
        for row in rows:
            metrics = {}
            metrics["size"] = row["size"]
            metrics["user_id"] = row["user_id"]
            metrics["group_id"] = row["group_id"]
            metrics["mode"] = row["mode"]
            metrics["last_modified"] = row["last_modified"]
            metrics["creation_time"] = row["creation_time"]
            metrics["md5"] = row["md5"]
            metrics["sha256"] = row["sha256"]
            metrics["pattern_found"] = row["pattern_found"]
            metrics["sample_epoch"] = row["sample_epoch"]
            samples[row["file_path"]] = metrics
        return samples
    return None


def has_previous_sample(db_path, watch_group):
    """
    Check if there is any previous sample data for the given watch group.
    Returns True if at least one record exists; otherwise False.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM samples WHERE watch_group = ?", (watch_group,))
    count = cur.fetchone()[0]
    conn.close()
    return count > 1


def remove_old_samples(db_path, watch_group, retain_samples=1):
    """
    Remove old samples from the samples table for the given watch_group.
    """
    # Get the sample_epoch of the Nth last sample
    samples = get_last_n_sample_epochs(db_path, watch_group, retain_samples)
    if not samples:
        return
    epoch = min(samples)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM samples
        WHERE watch_group = ? AND sample_epoch < ?
    """,
        (watch_group, epoch),
    )
    conn.commit()
    conn.close()


def count_samples(db_path, watch_group):
    """
    Count the number of samples for the given watch_group.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM samples WHERE watch_group = ?", (watch_group,))
    count = cur.fetchone()[0]
    conn.close()
    return count


def count_sample_epochs(db_path, watch_group):
    """
    Count the number of unique sample epochs for the given watch_group.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT sample_epoch) FROM samples WHERE watch_group = ?",
        (watch_group,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count
