import os
import sqlite3
import tempfile
import json
import pytest
from eventwatcher import db

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(str(db_path))
    return str(db_path)

def test_db_init_and_insert(temp_db):
    # Insert a sample event and sample record, then verify their existence.
    db.insert_event(temp_db, "TestGroup", "TestEvent", {"key": "value"})
    db.insert_sample(temp_db, "TestGroup", {"sample": 123})

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT * FROM events")
    events = cur.fetchall()
    assert len(events) == 1
    cur.execute("SELECT * FROM samples")
    samples = cur.fetchall()
    assert len(samples) == 1
    conn.close()
