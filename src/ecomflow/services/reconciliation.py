"""使用精确十进制计算匹配订单和账单，输出差异原因。"""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import pandas as pd
from ecomflow.core.models import Bill
from ecomflow.database.store import Store
from ecomflow.ingestion.products import read_table

COLUMNS = [
    "order_id",
    "bill_id",
    "platform",
    "platform_order_id",
    "status",
    "reason",
    "expected_settlement",
    "actual_settlement",
    "difference",
]


def import_bills(store: Store, path: str) -> int:
    """先验证全部输入，再以事务替换同一来源的账单。"""
    records = [Bill.model_validate(r) for r in read_table(path).to_dict("records")]
    source = str(Path(path).resolve())
    with store.transaction() as db:
        db.execute("DELETE FROM bills WHERE source=?", (source,))
        for row_number, bill in enumerate(records, 2):
            values = bill.model_dump(mode="json")
            db.execute(
                f"INSERT INTO bills(source,row_number,{','.join(values)}) VALUES({','.join('?' for _ in range(len(values) + 2))})",
                (source, row_number, *values.values()),
            )
    return len(records)


def reconcile(store: Store, output: str = "outputs/reconciliation.xlsx") -> list[dict]:
    """每条账单生成一行报告，另为缺失账单的订单生成报告行。"""
    orders = {
        (o["platform"], o["platform_order_id"]): o
        for o in store.rows("SELECT * FROM orders")
    }
    grouped = defaultdict(list)
    for bill in store.rows("SELECT * FROM bills ORDER BY id"):
        grouped[bill["platform"], bill["platform_order_id"]].append(bill)
    results = []
    for key in sorted(set(orders) | set(grouped)):
        order = orders.get(key)
        bills = grouped.get(key, [])
        if not bills:
            results.append(
                dict(
                    order_id=order["id"],
                    bill_id="",
                    platform=key[0],
                    platform_order_id=key[1],
                    status="MISSING_BILL",
                    reason="订单缺少平台账单",
                    expected_settlement="",
                    actual_settlement="",
                    difference="",
                )
            )
        for bill in bills:
            reasons = []
            if order is None:
                reasons.append("ORPHAN_BILL")
            if len(bills) > 1:
                reasons.append("DUPLICATE_BILL")
            expected = (
                Decimal(bill["gross_amount"])
                - Decimal(bill["refund_amount"])
                - Decimal(bill["fee_amount"])
            )
            actual = Decimal(bill["settlement_amount"])
            difference = actual - expected
            if order and order["currency"] != bill["currency"]:
                reasons.append("CURRENCY_MISMATCH")
            if order and Decimal(order["gross_amount"]) != Decimal(
                bill["gross_amount"]
            ):
                reasons.append("GROSS_MISMATCH")
            if difference:
                reasons.append("AMOUNT_MISMATCH")
            results.append(
                dict(
                    order_id=order["id"] if order else "",
                    bill_id=bill["id"],
                    platform=key[0],
                    platform_order_id=key[1],
                    status="|".join(reasons) or "MATCHED",
                    reason="; ".join(reasons) or "订单金额、币种与结算金额一致",
                    expected_settlement=str(expected),
                    actual_settlement=str(actual),
                    difference=str(difference),
                )
            )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(results, columns=COLUMNS).to_excel(
            writer, sheet_name="reconciliation", index=False
        )
        pd.DataFrame(store.rows("SELECT * FROM bills")).to_excel(
            writer, sheet_name="source_bills", index=False
        )
        pd.DataFrame(list(orders.values())).to_excel(
            writer, sheet_name="source_orders", index=False
        )
    return results
