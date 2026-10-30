# 模拟平台 API

启动：`python -m uvicorn mock_platform.app:app --host 127.0.0.1 --port 8000`。仅绑定本机，所有数据虚构，控制接口没有鉴权。接口 schema 由 FastAPI 自动生成。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /health | 返回 status=ok 和两个平台名 |
| POST | /control/reset | 清空商品、幂等缓存和故障配置 |
| POST | /control/{platform}/fault | 设置故障类型、剩余触发次数及延迟 |
| POST | /{platform}/products | 发布商品，支持 Idempotency-Key |
| GET | /{platform}/products/{sku} | 查询已发布商品 |
| GET | /{platform}/orders | 分页获取虚构订单 |

## 两个平台字段差异

平台 A 商品：

```json
{"sku":"SKU-001","title":"旅行收纳袋","price":"20.00","currency":"USD","stock":100}
```

平台 A 响应：`{"id":"platform_a:SKU-001","success":true}`。

平台 B 商品：

```json
{"seller_code":"SKU-001","name":"旅行收纳袋","amount":{"value":"20.00","currency":"USD"},"inventory":{"available":100}}
```

平台 B 响应：`{"result":{"listing_code":"platform_b:SKU-001"},"code":"OK"}`。

订单查询参数：page（从 1 开始）、page_size（1—100）、updated_since（UTC ISO 时间字符串，严格大于）。每个平台固定 4 个订单，默认每页 2 条。A 返回 orders 和 has_more，B 返回 data 和 pagination.next。A 的 paid/shipped/cancelled/refunded 与 B 的 PAYMENT_COMPLETE/DISPATCHED/VOID/REFUNDED 映射到统一状态。

## 可控故障

```bash
curl -X POST http://127.0.0.1:8000/control/platform_a/fault \
  -H 'Content-Type: application/json' \
  -d '{"kind":"429","count":2}'
```

kind 支持 `401`、`429`、`500`、`timeout`、`invalid_json`、`duplicate`、`none`。count 范围 0—20，默认 1；timeout 的 delay 范围 0—5 秒，默认 0.3 秒。要触发客户端超时，客户端读取超时必须小于 delay，例如测试使用 0.03 秒。默认 CLI 读取超时为 3 秒，可设置 delay=5。

故障计数仅作用于 `/{platform}/...` 请求，不影响健康和控制接口。429 附带 Retry-After。duplicate 返回 409；此外，不带相同幂等键重复发布 SKU 也会返回 409。同一幂等键相同请求重放返回原结果，键与请求内容不一致返回 409。

示例密钥不需要真实值；401 仅用于认证失败处理测试。客户端不调用任何真实电商平台。
