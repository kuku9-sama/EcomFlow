"""使用持久化游标和事务实现分页订单同步。"""

from ecomflow.core.models import now
from ecomflow.database.store import Store
from ecomflow.adapters.platforms import PlatformAdapter


def sync_orders(store: Store, adapter: PlatformAdapter, full: bool = False) -> dict:
    state = store.rows(
        "SELECT cursor FROM sync_state WHERE platform=?", (adapter.name,)
    )
    cursor = "" if full or not state else state[0]["cursor"]
    latest = cursor
    total = 0
    # 仅在所有分页均成功解析并提交后推进游标。
    with store.transaction() as db:
        page = 1
        while True:
            orders, more = adapter.orders(page, cursor)
            for order in orders:
                values = (
                    order.platform,
                    order.platform_order_id,
                    order.currency,
                    str(order.gross_amount),
                    order.status,
                    order.updated_at,
                    now(),
                )
                db.execute(
                    "INSERT INTO orders(platform,platform_order_id,currency,gross_amount,status,updated_at,synced_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(platform,platform_order_id) DO UPDATE SET currency=excluded.currency,gross_amount=excluded.gross_amount,status=excluded.status,updated_at=excluded.updated_at,synced_at=excluded.synced_at",
                    values,
                )
                order_id = db.execute(
                    "SELECT id FROM orders WHERE platform=? AND platform_order_id=?",
                    (order.platform, order.platform_order_id),
                ).fetchone()[0]
                db.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
                for item in order.items:
                    db.execute(
                        "INSERT INTO order_items(order_id,sku,quantity,unit_price) VALUES(?,?,?,?)",
                        (order_id, item.sku, item.quantity, str(item.unit_price)),
                    )
                total += 1
                latest = max(latest, order.updated_at)
            if not more:
                break
            if not orders or page >= 10000:
                raise ValueError("Invalid or excessive pagination")
            page += 1
        db.execute(
            "INSERT INTO sync_state(platform,cursor) VALUES(?,?) ON CONFLICT(platform) DO UPDATE SET cursor=excluded.cursor",
            (adapter.name, latest),
        )
    return {"total": total, "success": total, "failed": 0}
