import sqlite3
import os
import json

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

    Args:
        db_path (str): Path to the SQLite database file.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_group TEXT NOT NULL,
            event TEXT NOT NULL,
            sample_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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

def insert_event(db_path, watch_group, event, sample_data):
    """
    Insert an event record into the database.

    Args:
        db_path (str): Path to the database.
        watch_group (str): Name of the watch group.
        event (str): Event name/description.
        sample_data (dict): The sample data triggering the event.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO events (watch_group, event, sample_data)
        VALUES (?, ?, ?)
    ''', (watch_group, event, json.dumps(sample_data)))
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
