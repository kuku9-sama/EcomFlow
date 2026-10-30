import sqlite3
import pytest
from ecomflow.database.store import Store

def test_schema_and_rollback(tmp_path):
    store = Store(str(tmp_path/'db.sqlite'))
    with pytest.raises(RuntimeError):
        with store.transaction() as db:
            db.execute("INSERT INTO sync_state VALUES('platform_a','x')")
            raise RuntimeError('rollback')
    assert store.rows('SELECT * FROM sync_state') == []
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute("INSERT INTO task_logs(task_id,created_at,message) VALUES('missing','now','error')")
