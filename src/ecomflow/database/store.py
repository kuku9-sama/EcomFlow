"""SQLite persistence; monetary values are always stored as decimal text."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products(sku TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,price TEXT NOT NULL,currency TEXT NOT NULL,stock INTEGER NOT NULL CHECK(stock>=0),category TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY,source TEXT NOT NULL,row_number INTEGER NOT NULL,raw TEXT NOT NULL,sku TEXT REFERENCES products(sku),error TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS platform_listings(id INTEGER PRIMARY KEY,platform TEXT NOT NULL,sku TEXT NOT NULL REFERENCES products(sku),status TEXT NOT NULL,external_id TEXT,error TEXT,attempts INTEGER NOT NULL DEFAULT 0,UNIQUE(platform,sku));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,platform TEXT NOT NULL,platform_order_id TEXT NOT NULL,currency TEXT NOT NULL,gross_amount TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL,synced_at TEXT NOT NULL,UNIQUE(platform,platform_order_id));
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,sku TEXT NOT NULL,quantity INTEGER NOT NULL,unit_price TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY,source TEXT NOT NULL,row_number INTEGER NOT NULL,platform TEXT NOT NULL,platform_order_id TEXT NOT NULL,currency TEXT NOT NULL,gross_amount TEXT NOT NULL,refund_amount TEXT NOT NULL,fee_amount TEXT NOT NULL,settlement_amount TEXT NOT NULL,settlement_date TEXT NOT NULL,UNIQUE(source,row_number));
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,type TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','SUCCESS','FAILED')),started_at TEXT,ended_at TEXT,total INTEGER NOT NULL DEFAULT 0,success INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,error TEXT,retries INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS task_logs(id INTEGER PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),created_at TEXT NOT NULL,message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_state(platform TEXT PRIMARY KEY,cursor TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_orders_platform ON orders(platform,updated_at);
CREATE INDEX IF NOT EXISTS idx_bills_order ON bills(platform,platform_order_id);
CREATE INDEX IF NOT EXISTS idx_task_logs ON task_logs(task_id);
'''

class Store:
    """Open short-lived foreign-key-enabled transactions with automatic rollback."""
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.transaction() as db:
            return [dict(r) for r in db.execute(sql, params)]
