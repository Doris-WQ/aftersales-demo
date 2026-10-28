"""独立模拟订单 API 与 HTTP 客户端。"""

import re
import secrets
from decimal import Decimal

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import ValidationError

from aftersales.data import Dataset
from aftersales.models import Order

# These are public local-demo credentials, not production authentication.
DEMO_TOKENS = {"local-buyer-a": "buyer-a", "local-buyer-b": "buyer-b"}


def buyer_for_token(token: str | None) -> str:
    for expected, buyer in DEMO_TOKENS.items():
        if token and secrets.compare_digest(token, expected):
            return buyer
    raise HTTPException(401, "需要有效的本地演示身份")


def require_buyer(x_demo_token: str | None = Header(default=None)) -> str:
    return buyer_for_token(x_demo_token)


def create_order_api(dataset: Dataset) -> FastAPI:
    app = FastAPI(title="模拟订单接口", docs_url=None, redoc_url=None)

    @app.get("/orders/{order_id}")
    async def order(order_id: str, x_demo_token: str | None = Header(default=None)):
        buyer = buyer_for_token(x_demo_token)
        if order_id not in dataset.ownership.get(buyer, ()):
            raise HTTPException(404, "查不到订单，请核对单号")
        return dataset.orders[order_id]

    return app


class OrderNotFound(Exception):
    pass


class OrderUnavailable(Exception):
    pass


class OrderClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def get(self, order_id: str, token: str) -> Order:
        try:
            response = await self.client.get(
                f"/orders/{order_id}", headers={"X-Demo-Token": token}, timeout=5
            )
            if response.status_code == 404:
                raise OrderNotFound
            response.raise_for_status()
            raw = response.json(parse_float=Decimal)
            # Pydantic serializes Decimal amounts as strings on this trusted API boundary.
            amount = raw.get("amount")
            if isinstance(amount, str):
                if not re.fullmatch(r"\d{1,10}(?:\.\d{1,2})?", amount):
                    raise OrderUnavailable
                raw["amount"] = Decimal(amount)
            order = Order.model_validate(raw)
            if order.order_id != order_id:
                raise OrderUnavailable
            return order
        except (httpx.HTTPError, ValidationError, ValueError, AttributeError):
            raise OrderUnavailable from None
