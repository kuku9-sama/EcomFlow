"""两个可重复初始化、支持可控故障的虚构电商平台。"""

import asyncio
import hashlib
import json
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field


class Fault(BaseModel):
    kind: str = Field(pattern=r"^(401|429|500|timeout|invalid_json|duplicate|none)$")
    count: int = Field(default=1, ge=0, le=20)
    delay: float = Field(default=0.3, ge=0, le=5)


def create_app() -> FastAPI:
    """为每个演示和测试进程创建独立的应用状态。"""
    app = FastAPI(title="EcomFlow Fictional Marketplaces")
    app.state.listings = {}
    app.state.keys = {}
    app.state.faults = {}

    @app.get("/health")
    def health():
        return {"status": "ok", "platforms": ["platform_a", "platform_b"]}

    @app.post("/control/reset")
    def reset():
        app.state.listings.clear()
        app.state.keys.clear()
        app.state.faults.clear()
        return {"status": "reset"}

    @app.post("/control/{platform}/fault")
    def fault(platform: str, config: Fault):
        check_platform(platform)
        app.state.faults[platform] = config.model_dump()
        return {"status": "configured"}

    def check_platform(platform):
        if platform not in ("platform_a", "platform_b"):
            raise HTTPException(404, "Unknown platform")

    @app.middleware("http")
    async def failures(request: Request, call_next):
        parts = request.url.path.split("/")
        platform = parts[1] if len(parts) > 1 else ""
        config = app.state.faults.get(platform)
        if config and config["count"] > 0:
            config["count"] -= 1
            kind = config["kind"]
            if kind in ("401", "429", "500"):
                return JSONResponse(
                    {"error": f"controlled {kind}"},
                    status_code=int(kind),
                    headers={"Retry-After": "0"},
                )
            if kind == "invalid_json":
                return Response("{broken", media_type="application/json")
            if kind == "duplicate":
                return JSONResponse({"error": "duplicate request"}, status_code=409)
            if kind == "timeout":
                await asyncio.sleep(config["delay"])
        return await call_next(request)

    @app.post("/{platform}/products")
    async def publish(platform: str, request: Request):
        check_platform(platform)
        payload = await request.json()
        key = request.headers.get("Idempotency-Key")
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        if key and (platform, key) in app.state.keys:
            old_hash, result = app.state.keys[platform, key]
            if old_hash != fingerprint:
                raise HTTPException(409, "Idempotency key payload mismatch")
            return result
        sku = (
            payload.get("sku")
            if platform == "platform_a"
            else payload.get("seller_code")
        )
        try:
            amount = Decimal(
                payload["price"]
                if platform == "platform_a"
                else payload["amount"]["value"]
            )
            stock = (
                payload["stock"]
                if platform == "platform_a"
                else payload["inventory"]["available"]
            )
            title = payload["title"] if platform == "platform_a" else payload["name"]
            if (
                not sku
                or not title
                or not amount.is_finite()
                or amount < 0
                or type(stock) is not int
                or stock < 0
            ):
                raise ValueError()
        except (KeyError, ValueError, TypeError, ArithmeticError):
            raise HTTPException(422, "Invalid product payload")
        if (platform, sku) in app.state.listings:
            raise HTTPException(409, "SKU already published")
        external_id = f"{platform}:{sku}"
        result = (
            {"id": external_id, "success": True}
            if platform == "platform_a"
            else {"result": {"listing_code": external_id}, "code": "OK"}
        )
        app.state.listings[platform, sku] = payload
        if key:
            app.state.keys[platform, key] = (fingerprint, result)
        return result

    @app.get("/{platform}/products/{sku}")
    def product(platform: str, sku: str):
        check_platform(platform)
        if (platform, sku) not in app.state.listings:
            raise HTTPException(404, "Not found")
        return app.state.listings[platform, sku]

    @app.get("/{platform}/orders")
    def orders(
        platform: str, page: int = 1, page_size: int = 2, updated_since: str = ""
    ):
        check_platform(platform)
        if page < 1 or not 1 <= page_size <= 100:
            raise HTTPException(422, "Invalid pagination")
        records = []
        for i in range(1, 5):
            stamp = f"2026-01-0{i}T12:00:00+00:00"
            if stamp <= updated_since:
                continue
            sku = "SKU-001" if i % 2 else "SKU-002"
            price = "20.00" if i % 2 else "30.00"
            if platform == "platform_a":
                records.append(
                    {
                        "order_id": f"A-{i:03}",
                        "currency": "USD",
                        "total": price,
                        "state": "paid",
                        "updated_at": stamp,
                        "items": [{"sku": sku, "qty": 1, "price": price}],
                    }
                )
            else:
                records.append(
                    {
                        "number": f"B-{i:03}",
                        "money": {"currency": "USD", "gross": price},
                        "status_code": "PAYMENT_COMPLETE",
                        "modified": stamp,
                        "lines": [
                            {"seller_code": sku, "units": 1, "unit_amount": price}
                        ],
                    }
                )
        selected = records[(page - 1) * page_size : page * page_size]
        more = page * page_size < len(records)
        return (
            {"orders": selected, "has_more": more}
            if platform == "platform_a"
            else {"data": selected, "pagination": {"next": page + 1 if more else None}}
        )

    return app


app = create_app()
