"""Validated canonical business models, independent of platform payloads."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator, BeforeValidator

def decimal_input(value):
    """Reject floats before all financial model conversions."""
    if isinstance(value, float):
        raise ValueError('money must be decimal text')
    return value

Money = Annotated[Decimal, BeforeValidator(decimal_input), Field(ge=0, max_digits=18, decimal_places=2)]

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Product(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ''
    price: Money
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    stock: int = Field(ge=0, le=1_000_000, strict=True)
    category: str = 'general'
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)

    @field_validator('price', mode='before')
    @classmethod
    def forbid_float(cls, value):
        if isinstance(value, float):
            raise ValueError('money must be decimal text')
        return value

class OrderItem(BaseModel):
    sku: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: Money

class Order(BaseModel):
    platform: str
    platform_order_id: str = Field(min_length=1)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    gross_amount: Money
    status: str
    updated_at: str
    items: list[OrderItem] = Field(min_length=1)

class Bill(BaseModel):
    platform: str = Field(pattern=r'^platform_[ab]$')
    platform_order_id: str = Field(min_length=1)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    gross_amount: Money
    refund_amount: Money
    fee_amount: Money
    settlement_amount: Money
    settlement_date: str
