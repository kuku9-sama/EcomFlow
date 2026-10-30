# 测试验证记录

验证日期：2026-10-30。环境：Linux、Python 3.12.14，仓库独立 `.venv`，依赖按 requirements.lock 全新安装，项目以 editable 模式安装。

## 全量测试

执行命令：

```bash
.venv/bin/python -m pytest -q --junitxml=outputs/pytest-results.xml
```

真实结果：**29 passed，0 failed，0 skipped，2 warnings，5.35 秒**。

| 测试文件 | 数量 | 验证内容 |
| --- | ---: | --- |
| test_database.py | 1 | schema、外键、事务异常回滚 |
| test_ingestion.py | 2 | CSV/Excel 正常导入、缺少 SKU、重复 SKU、负价格、异常库存、来源记录 |
| test_api.py | 7 | 429/500 重试、Retry-After、401、超时、非法 JSON、非幂等 POST 不重试、模拟故障控制 |
| test_publishing.py | 3 | 双平台字段映射、成功发布、防重复发布、失败记录与恢复 |
| test_orders.py | 3 | 重复同步、增量游标、分页失败回滚、双平台状态映射 |
| test_reconciliation.py | 2 | CSV/Excel 账单、重导幂等、正常对账、金额差异、缺失、重复、孤立、币种差异 |
| test_tasks.py | 2 | 失败数据库和日志记录、重试关联、部分失败统计 |
| test_demo.py | 1 | 真实 HTTP 完整业务连续两次运行，稳定业务计数 |
| test_http_integration.py | 8 | 真实 HTTP 的 6 类故障、幂等重放与冲突、所有财务模型拒绝 float |

两条告警来自依赖：AnyIO 的 Pytest 插件使用即将弃用的 CallSpec2 名称；Starlette 提示后续测试客户端迁移到 httpx2。当前用例均已执行并通过，没有屏蔽告警或跳过故障测试。

## 命令行验收

在同一个全新数据库上执行：

```bash
.venv/bin/ecomflow init-db
.venv/bin/ecomflow init-demo
.venv/bin/ecomflow --db outputs/clean-demo.sqlite3 demo
.venv/bin/ecomflow --db outputs/clean-demo.sqlite3 demo
.venv/bin/ecomflow report
```

两次 demo 退出码均为 0。第二次 products=2、platform_listings=4、orders=8、order_items=8、bills=8、tasks=12、task_logs=24、imports=10。审计累积，业务数据无重复增长。样例三行错误商品形成两次真实 FAILED 导入任务，其余演示任务成功。

生成结果：

- outputs/product_errors.xlsx：3 行商品错误及原因。
- outputs/reconciliation.xlsx：10 行结果，包含 3 条正常记录、金额差异、重复、缺失、孤立及币种不一致。
- outputs/operations.xlsx：8 个业务和审计工作表。
- outputs/pytest-results.xml：本次全量测试 JUnit 报告。
- outputs/clean-demo-result.json 和 clean-demo-repeat-result.json：实际命令结果。
- logs/ecomflow.log：请求业务 ID、任务结果和异常堆栈。

## 阶段验证

1. 项目骨架与数据库：1 passed。
2. 商品 ETL：2 passed。
3. 模拟平台和客户端：7 passed。
4. 商品发布：3 passed。
5. 订单同步：3 passed。
6. 账单核对：2 passed。
7. 任务与日志：2 passed。
8. 完整 demo 和集成：首轮全量 21 passed；增加真实 HTTP 故障、幂等冲突及浮点防护后 29 passed。
9. 文档和独立安装：锁定依赖安装成功，独立虚拟环境再次 29 passed，并完成两次 CLI demo。

## 限制

未声称测试 Python 3.11、Windows、真实电商服务、高并发或进程崩溃自动恢复。模拟 API 只在回环地址运行；执行集成测试需要允许本地端口通信。详细产品边界见 README。
