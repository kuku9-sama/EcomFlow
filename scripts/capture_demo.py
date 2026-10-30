"""运行真实演示和测试，将结果生成静态报告并截取图片。"""

import html
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
LABELS = {
    "MATCHED": "正常结算",
    "AMOUNT_MISMATCH": "金额不一致",
    "DUPLICATE_BILL": "重复账单",
    "MISSING_BILL": "缺失账单",
    "CURRENCY_MISMATCH": "币种不一致",
    "ORPHAN_BILL": "孤立账单",
}


def main() -> None:
    """从全新数据库采集证据，浏览器截图不依赖外部资源。"""
    ASSETS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ecomflow-showcase-") as directory:
        db = str(Path(directory) / "demo.sqlite3")
        demo = subprocess.run(
            [sys.executable, "-m", "ecomflow.cli", "--db", db, "demo"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        counts = json.loads(demo.stdout)["counts"]
        test = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--color=no"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = next(
            line for line in reversed(test.stdout.splitlines()) if " passed" in line
        )
        bills = pd.read_excel(ROOT / "outputs/reconciliation.xlsx", dtype=str).fillna(
            ""
        )
        cards = "".join(
            f'<div class="card"><span>{label}</span><b>{counts[key]}</b></div>'
            for key, label in [
                ("products", "合法商品"),
                ("platform_listings", "双平台发布"),
                ("orders", "同步订单"),
                ("bills", "导入账单"),
            ]
        )
        rows = ""
        for _, row in bills.iterrows():
            status = row["status"]
            cells = [
                row["platform"]
                .replace("platform_a", "平台 A")
                .replace("platform_b", "平台 B"),
                row["platform_order_id"],
                row["expected_settlement"] or "—",
                row["actual_settlement"] or "—",
                row["difference"] or "—",
            ]
            rows += (
                "<tr>"
                + "".join("<td>" + html.escape(v) + "</td>" for v in cells)
                + f'<td><span class="tag {"ok" if status == "MATCHED" else "warn"}">{html.escape(LABELS.get(status, status))}</span></td></tr>'
            )
        style = """*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#182638;font-family:"Noto Sans CJK SC","Noto Sans",sans-serif;padding:48px}main{max-width:1180px;margin:auto}.eyebrow{color:#0f766e;letter-spacing:2px;font-size:14px;font-weight:700}h1{font-size:38px;margin:10px 0}p{color:#536478;font-size:16px;line-height:1.8}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0}.card{background:white;border:1px solid #dbe4ed;border-radius:12px;padding:20px}.card span{display:block;color:#536478;font-size:14px}.card b{display:block;font-size:38px;margin-top:8px}.panel{background:white;border:1px solid #dbe4ed;border-radius:14px;padding:24px}h2{font-size:21px;margin:0 0 8px}table{width:100%;border-collapse:collapse;margin-top:18px;font-size:14px}th{text-align:left;background:#f8fafc;color:#536478}td,th{padding:12px 14px;border-bottom:1px solid #edf1f5}.tag{padding:5px 9px;border-radius:5px;font-size:12px}.ok{background:#dff5eb;color:#166344}.warn{background:#fff0dc;color:#945617}.footer{margin-top:20px;display:flex;justify-content:space-between;font-size:13px;color:#536478}pre{white-space:pre-wrap;word-break:break-word;font-family:"DejaVu Sans Mono","Noto Sans CJK SC",monospace;font-size:16px;line-height:1.8}.terminal{background:#111c2e;color:#e3edf9;border-radius:14px;padding:28px}.terminal h2{color:#5ee0bd}.muted{color:#97acc5}"""
        report = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>EcomFlow 演示报告</title><style>{style}</style><main><div class="eyebrow">ECOMFLOW / 业务演示报告</div><h1>从商品入库，到结算核对</h1><p>真实本地模拟 API · SQLite 持久化 · Decimal 精确金额<br>商品清洗 → 双平台发布 → 分页订单同步 → 账单核对 → Excel 导出</p><div class="cards">{cards}</div><section class="panel"><h2>账单核对 · 10 条结果，6 类状态</h2><p style="margin:0">A-002 应结算 27.00，实际到账 26.00，自动识别 -1.00 差异。</p><table><thead><tr><th>平台</th><th>订单号</th><th>应结算</th><th>实际结算</th><th>差额</th><th>核对结果</th></tr></thead><tbody>{rows}</tbody></table></section><div class="footer"><span>所有数据均为虚构演示数据 · 此页面为只读静态报告</span><span>{html.escape(result.split(" in ")[0])}</span></div></main></html>"""
        (ASSETS / "demo-report.html").write_text(report, encoding="utf-8")
        terminal = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>{style}</style><main><div class="eyebrow">ECOMFLOW / 真实命令输出</div><h1>一条命令，跑通业务闭环</h1><p>以下内容来自本次实际运行的标准输出；错误商品按设计保留失败任务。</p><section class="terminal"><h2>$ ecomflow demo</h2><pre>{html.escape(demo.stdout)}</pre><h2>$ python -m pytest -q</h2><pre>{html.escape(result)}</pre><p class="muted">测试覆盖：导入校验 / 幂等发布 / 重复同步 / 对账差异 / 事务回滚 / 可控 HTTP 故障</p></section></main></html>"""
        (ASSETS / "run-evidence.txt").write_text(
            "命令：ecomflow demo\n"
            + demo.stdout
            + "\n命令：python -m pytest -q\n"
            + test.stdout,
            encoding="utf-8",
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=shutil.which("chromium")
                or shutil.which("google-chrome"),
                args=["--no-sandbox"],
            )
            page = browser.new_page(
                viewport={"width": 1280, "height": 1000}, device_scale_factor=1
            )
            for content, name in [
                (report, "demo-report.png"),
                (terminal, "demo-run.png"),
            ]:
                page.set_content(content)
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(ASSETS / name), full_page=True)
            browser.close()
        print(result)
        print("截图已生成：docs/assets/demo-report.png、demo-run.png")


if __name__ == "__main__":
    main()
