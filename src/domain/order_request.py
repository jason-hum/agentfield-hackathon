from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator


class OrderRequest(BaseModel):
    """Minimal structured order request for basic stock orders."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["BUY", "SELL"]
    symbol: str = Field(min_length=1)
    sec_type: Literal["STK"] = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    quantity: PositiveFloat
    order_type: Literal["MKT", "LMT"]
    tif: Literal["DAY", "GTC"] = "DAY"

    limit_price: PositiveFloat | None = None
    primary_exch: str | None = None
    transmit: bool = False
    client_tag: str | None = None
    order_ref: str | None = None

    @field_validator(
        "action",
        "symbol",
        "sec_type",
        "exchange",
        "currency",
        "order_type",
        "tif",
        mode="before",
    )
    @classmethod
    def _normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("client_tag", "order_ref", "primary_exch", mode="before")
    @classmethod
    def _normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("limit_price")
    @classmethod
    def _check_limit_price_precision(cls, value: float | None) -> float | None:
        # Keep a simple precision guard for accidental huge decimals in manual CLI input.
        if value is None:
            return None
        return round(value, 8)

    @model_validator(mode="after")
    def _validate_order_type_fields(self) -> "OrderRequest":
        if self.order_type == "LMT" and self.limit_price is None:
            raise ValueError("limit_price is required when order_type=LMT")

        if self.order_type == "MKT" and self.limit_price is not None:
            raise ValueError("limit_price must be omitted when order_type=MKT")

        if self.client_tag and self.order_ref and self.client_tag != self.order_ref:
            raise ValueError("client_tag and order_ref must match when both are provided")

        return self

    @property
    def effective_order_ref(self) -> str | None:
        return self.order_ref or self.client_tag

    @classmethod
    def from_json(cls, payload: str) -> "OrderRequest":
        return cls.model_validate_json(payload)
