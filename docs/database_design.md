# 数据库设计

初始化：`ecomflow init-db`。DDL 位于 `src/ecomflow/database/store.py`，执行 CREATE TABLE/INDEX IF NOT EXISTS。SQLite 连接逐次启用 `PRAGMA foreign_keys=ON`，10 秒锁等待，成功提交、异常回滚。当前版本没有 schema 迁移功能。

| 表 | 主键 / 唯一键 | 主要数据与关联 |
| --- | --- | --- |
| products | sku | title、description、price TEXT、currency、stock、category、created_at、updated_at |
| imports | id | source、row_number、raw JSON、sku 外键、error、created_at |
| platform_listings | id；UNIQUE(platform,sku) | sku 外键、status、external_id、error、attempts |
| orders | id；UNIQUE(platform,platform_order_id) | currency、gross_amount TEXT、status、updated_at、synced_at |
| order_items | id | order_id 外键并级联删除、sku、quantity、unit_price TEXT |
| bills | id；UNIQUE(source,row_number) | platform、platform_order_id、currency、gross/refund/fee/settlement_amount TEXT、settlement_date |
| tasks | UUID id | type、status、started_at、ended_at、total、success、failed、error、retries |
| task_logs | id | task_id 外键、created_at、message |
| sync_state | platform | cursor |

索引：订单的 platform+updated_at、账单的 platform+platform_order_id、任务日志的 task_id；唯一约束同时提供对应唯一索引。

## 金额与数据来源

财务字段均以十进制字符串存储，计算前恢复 Decimal；不使用 SQLite REAL 或 Pandas 浮点计算。Pandas 读取时使用 dtype=str，Excel 数值读取后以字符串进入验证。两位以上小数及非有限金额不能进入标准模型。

商品原始行保存于 imports.raw，清洗成功后通过 sku 关联 products；created_at 首次创建保留，updated_at 随新导入刷新。重复导入会追加审计，不重复创建商品。

账单允许同一订单出现多条记录，不能以订单 ID 做账单唯一键，否则会丢失重复账单证据。来源文件绝对路径和行号用于重导幂等；同一来源重导采用原子替换，因此账单内部 ID 可能改变。每次 Excel 报告包含当次源账单与源订单快照，可独立核查；尚未提供跨报告的稳定账单版本 ID。

## 事务边界

- 商品：一批文件一个事务，校验错误逐行保留，不抛出并中止合法商品。
- 发布：HTTP 操作完成后逐商品保存结果，成功与失败都记录。
- 同步：全部分页、订单与明细 upsert、最终游标一起提交。
- 账单：先验证所有行，再事务替换指定来源，输入错误不会删除旧账单。
- 任务：PENDING、RUNNING、最终状态分别提交，业务回滚不影响失败审计。
