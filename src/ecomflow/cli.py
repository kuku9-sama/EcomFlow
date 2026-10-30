"""命令行入口与可重复执行的完整业务演示。"""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import requests
from ecomflow.database.store import Store
from ecomflow.core.models import Product
from ecomflow.clients.api import APIClient
from ecomflow.adapters.platforms import adapter_for
from ecomflow.ingestion.products import import_products, read_table
from ecomflow.services.publishing import publish_products
from ecomflow.services.orders import sync_orders
from ecomflow.services.reconciliation import import_bills, reconcile
from ecomflow.jobs.tasks import TaskRunner, TaskFailed, configure_logging
from ecomflow.reports.summary import report


def init_demo() -> dict:
    """生成 Excel 样例，不覆盖已有输入文件。"""
    for name in ["sample_products", "sample_bills"]:
        target = Path("data") / f"{name}.xlsx"
        if not target.exists():
            read_table(str(Path("data") / f"{name}.csv")).to_excel(target, index=False)
    return {"status": "演示输入已初始化，所有记录均为虚构"}


def run_demo(store: Store, output: str = "outputs") -> dict:
    """运行独立本地模拟服务，结束后关闭本次启动的进程。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    Path(output).mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    with open(Path(output) / "mock-server.log", "w") as logfile:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mock_platform.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=logfile,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Mock server exited; inspect mock-server.log")
                try:
                    response = session.get(url + "/health", timeout=0.2)
                    if (
                        response.status_code == 200
                        and response.json()["status"] == "ok"
                    ):
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.05)
            else:
                raise RuntimeError("Mock server readiness timeout")
            runner = TaskRunner(store)
            # 样例有意包含错误行，必须保留真实失败的导入任务。
            try:
                runner.run(
                    "import-products",
                    lambda: import_products(store, "data/sample_products.csv", output),
                )
            except TaskFailed:
                pass
            client = APIClient(url, session=session)
            for platform in ["platform_a", "platform_b"]:
                adapter = adapter_for(platform, client)
                # 在新启动的内存模拟平台中恢复已有成功商品。
                for row in store.rows(
                    "SELECT p.* FROM products p JOIN platform_listings l ON p.sku=l.sku WHERE l.platform=? AND l.status='SUCCESS'",
                    (platform,),
                ):
                    adapter.publish(Product.model_validate(row))
                runner.run(
                    f"publish-products:{platform}",
                    lambda a=adapter: publish_products(store, a),
                )
                for row in store.rows("SELECT sku FROM products"):
                    remote = client.get(f"/{platform}/products/{row['sku']}")
                    if not remote:
                        raise RuntimeError("Published listing missing from mock")
                # 全量刷新保持幂等，支持每次演示使用全新模拟服务。
                runner.run(
                    f"sync-orders:{platform}",
                    lambda a=adapter: sync_orders(store, a, full=True),
                )

            def reconcile_operation():
                import_bills(store, "data/sample_bills.csv")
                rows = reconcile(store, str(Path(output) / "reconciliation.xlsx"))
                return dict(total=len(rows), success=len(rows), failed=0)

            runner.run("reconcile", reconcile_operation)
            counts = report(store, str(Path(output) / "operations.xlsx"))
            return {
                "status": "演示完成",
                "counts": counts,
                "reports": [
                    str(Path(output) / "reconciliation.xlsx"),
                    str(Path(output) / "operations.xlsx"),
                ],
                "note": "样例错误商品行已记录为一个失败导入任务",
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EcomFlow：虚构多平台电商自动化系统"
    )
    parser.add_argument(
        "--db", default=os.getenv("ECOMFLOW_DB", "outputs/ecomflow.sqlite3")
    )
    parser.add_argument(
        "--api-url", default=os.getenv("ECOMFLOW_API_URL", "http://127.0.0.1:8000")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["init-db", "init-demo", "demo", "report"]:
        commands.add_parser(name)
    for name in ["import-products", "reconcile"]:
        sub = commands.add_parser(name)
        sub.add_argument("--file", required=True)
        sub.add_argument("--retry-of")
    for name in ["publish-products", "sync-orders"]:
        sub = commands.add_parser(name)
        sub.add_argument(
            "--platform", required=True, choices=["platform_a", "platform_b"]
        )
        sub.add_argument("--retry-of")
        if name == "publish-products":
            sub.add_argument("--sku")
        else:
            sub.add_argument("--full", action="store_true")
    sub = commands.add_parser("listings")
    sub.add_argument("--platform", required=True, choices=["platform_a", "platform_b"])
    sub.add_argument("--sku")
    commands.add_parser("tasks")
    args = parser.parse_args()
    configure_logging()
    store = Store(args.db)
    runner = TaskRunner(store)
    try:
        if args.command == "init-db":
            result = {"status": "数据库已初始化", "path": args.db}
        elif args.command == "init-demo":
            result = init_demo()
        elif args.command == "demo":
            result = run_demo(store)
        elif args.command == "report":
            result = report(store)
        elif args.command == "tasks":
            result = store.rows("SELECT * FROM tasks ORDER BY started_at")
        elif args.command == "listings":
            result = store.rows(
                "SELECT * FROM platform_listings WHERE platform=?"
                + (" AND sku=?" if args.sku else ""),
                (args.platform, args.sku) if args.sku else (args.platform,),
            )
        elif args.command == "import-products":
            result = runner.run(
                "import-products",
                lambda: import_products(store, args.file),
                args.retry_of,
            )
        elif args.command == "reconcile":

            def operation():
                import_bills(store, args.file)
                rows = reconcile(store)
                return dict(total=len(rows), success=len(rows), failed=0)

            result = runner.run("reconcile", operation, args.retry_of)
        else:
            client = APIClient(args.api_url)
            # 客户端仅接受本地回环地址。
            client.session.trust_env = False
            adapter = adapter_for(args.platform, client)
            operation = (
                (lambda: publish_products(store, adapter, args.sku))
                if args.command == "publish-products"
                else (lambda: sync_orders(store, adapter, args.full))
            )
            try:
                result = runner.run(
                    f"{args.command}:{args.platform}", operation, args.retry_of
                )
            finally:
                client.session.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("command failed: %s", args.command)
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
