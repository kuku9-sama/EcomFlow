# 开发与验证记录

## 阶段 1：骨架和数据库

新增 pyproject.toml、.gitignore、.env.example、database/store.py、test_database.py。建立标准 src 包结构、金额 TEXT 存储、外键、唯一约束、索引与事务。数据库测试 1 passed。

## 阶段 2：商品 ETL

新增 core/models.py、ingestion/products.py、商品 CSV 和测试。按字符串读取，清洗字段，校验库存和金额，保存合法行与原始输入关系，导出错误 Excel。CSV/Excel 测试 2 passed。

## 阶段 3：平台与 HTTP 客户端

新增 mock_platform/app.py、clients/api.py、test_api.py。实现两平台商品和分页订单接口、故障控制、有限重试、Retry-After 和认证异常。测试 7 passed。受限沙箱无法完成本地异步通信，使用允许本地通信的执行方式验证。

## 阶段 4：商品发布

新增 adapters/platforms.py、services/publishing.py、test_publishing.py。实现标准接口、平台字段映射、稳定幂等键、成功跳过、失败记录和重跑。测试 3 passed。

## 阶段 5：订单同步

新增 services/orders.py、test_orders.py。实现分页、统一状态、订单及明细更新、整批事务与成功游标。重复同步和失败回滚测试 3 passed。

## 阶段 6：账单核对

新增 services/reconciliation.py、账单样例和测试。保留重复账单证据，精确计算结算差异，报告关联原始订单和账单工作表。CSV/Excel 测试 2 passed。

## 阶段 7：任务管理

新增 jobs/tasks.py、test_tasks.py。实现持久化状态转换、执行计数、重试关联与上限、数据库和文件错误日志。测试 2 passed。

## 阶段 8：完整演示

新增 cli.py、reports/summary.py、test_demo.py、test_http_integration.py、Excel 样例及 requirements.lock。首次完整测试 21 passed。复查发现临时模拟服务重启后商品内存状态与已有发布记录不同，增加成功商品恢复与远端查询。补充真实 HTTP 故障、幂等请求冲突和全财务模型 float 防护，全量测试 29 passed。

## 阶段 9：文档与交付

新增中文 README、架构、数据库、API、业务流程、面试问答、测试记录和本记录。关键注释和用户输出改为中文。在独立 .venv 中按锁定版本重新安装，测试 29 passed，命令行 demo 连续两次完成。未解决事项为 README 已列出的产品边界和两条第三方弃用告警，不影响本次单机开发演示。

## 仓库首页展示优化

将长篇操作说明移至 usage.md，README 保留核心亮点、两张演示截图和最短启动步骤。参考 Best-README-Template 的展示组织方式，记录来源及许可证；未引入后台依赖或占位按钮。新增 capture_demo.py，从全新数据库运行 demo、读取 Excel、执行 Pytest，再通过浏览器截取静态报告和原始输出。此次真实测试 29 passed、2 warnings。截图不宣称存在交互管理后台。
