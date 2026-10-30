"""通过统一适配器接口隔离平台字段和响应协议。"""

from abc import ABC, abstractmethod
from ecomflow.core.models import Product, Order
from ecomflow.clients.api import APIClient, APIError


class PlatformAdapter(ABC):
    name: str

    def __init__(self, client: APIClient):
        self.client = client

    @abstractmethod
    def payload(self, product: Product) -> dict: ...
    @abstractmethod
    def listing_id(self, response: dict) -> str: ...
    @abstractmethod
    def parse_page(self, response: dict) -> tuple[list[Order], bool]: ...

    def publish(self, product: Product) -> str:
        """使用稳定幂等键，确保成功响应丢失后仍可安全重试。"""
        result = self.client.post(
            f"/{self.name}/products",
            json=self.payload(product),
            business_id=product.sku,
            idempotency_key=f"{self.name}:{product.sku}",
        )
        try:
            return self.listing_id(result)
        except (KeyError, TypeError) as exc:
            raise APIError("Invalid publish response contract") from exc

    def orders(self, page: int, cursor: str) -> tuple[list[Order], bool]:
        data = self.client.get(
            f"/{self.name}/orders",
            params={"page": page, "page_size": 2, "updated_since": cursor},
            business_id=f"sync:{self.name}",
        )
        try:
            return self.parse_page(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise APIError("Invalid order response contract") from exc


class PlatformAAdapter(PlatformAdapter):
    name = "platform_a"

    def payload(self, p: Product) -> dict:
        return {
            "sku": p.sku,
            "title": p.title,
            "price": str(p.price),
            "currency": p.currency,
            "stock": p.stock,
        }

    def listing_id(self, response: dict) -> str:
        if response.get("success") is not True:
            raise APIError("Platform A rejected listing")
        return response["id"]

    def parse_page(self, response: dict) -> tuple[list[Order], bool]:
        states = {
            "paid": "PAID",
            "shipped": "SHIPPED",
            "cancelled": "CANCELLED",
            "refunded": "REFUNDED",
        }
        return [
            Order(
                platform=self.name,
                platform_order_id=o["order_id"],
                currency=o["currency"],
                gross_amount=o["total"],
                status=states[o["state"]],
                updated_at=o["updated_at"],
                items=[
                    {"sku": i["sku"], "quantity": i["qty"], "unit_price": i["price"]}
                    for i in o["items"]
                ],
            )
            for o in response["orders"]
        ], response["has_more"]


class PlatformBAdapter(PlatformAdapter):
    name = "platform_b"

    def payload(self, p: Product) -> dict:
        return {
            "seller_code": p.sku,
            "name": p.title,
            "amount": {"value": str(p.price), "currency": p.currency},
            "inventory": {"available": p.stock},
        }

    def listing_id(self, response: dict) -> str:
        if response.get("code") != "OK":
            raise APIError("Platform B rejected listing")
        return response["result"]["listing_code"]

    def parse_page(self, response: dict) -> tuple[list[Order], bool]:
        states = {
            "PAYMENT_COMPLETE": "PAID",
            "DISPATCHED": "SHIPPED",
            "VOID": "CANCELLED",
            "REFUNDED": "REFUNDED",
        }
        return [
            Order(
                platform=self.name,
                platform_order_id=o["number"],
                currency=o["money"]["currency"],
                gross_amount=o["money"]["gross"],
                status=states[o["status_code"]],
                updated_at=o["modified"],
                items=[
                    {
                        "sku": i["seller_code"],
                        "quantity": i["units"],
                        "unit_price": i["unit_amount"],
                    }
                    for i in o["lines"]
                ],
            )
            for o in response["data"]
        ], bool(response["pagination"]["next"])


def adapter_for(name: str, client: APIClient) -> PlatformAdapter:
    return {"platform_a": PlatformAAdapter, "platform_b": PlatformBAdapter}[name](
        client
    )
