"""导出持久化运营数据，便于检查和追溯。"""

from pathlib import Path
import pandas as pd
from ecomflow.database.store import Store


def report(store: Store, path: str = "outputs/operations.xlsx") -> dict:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for table in [
            "products",
            "platform_listings",
            "orders",
            "order_items",
            "bills",
            "tasks",
            "task_logs",
            "imports",
        ]:
            rows = store.rows(f"SELECT * FROM {table}")
            pd.DataFrame(rows).to_excel(writer, sheet_name=table, index=False)
            counts[table] = len(rows)
    return counts
