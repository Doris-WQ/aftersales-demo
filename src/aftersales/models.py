"""输入数据契约；不执行退款或资格决策。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

Text = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
OrderId = Annotated[str, Field(strict=True, pattern=r"^ORD-\d{4}$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Policy(Record):
    id: Annotated[str, Field(strict=True, pattern=r"^P\d{2}$")]
    title: Text
    content: Text
    applicability: Text
    version: Text
    retrieval_aliases: tuple[Text, ...]


class Order(Record):
    order_id: OrderId
    item: Text
    category: Text
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    status: Literal["已签收", "已发货"]
    signed_date: date | None
    tags_intact: StrictBool | None
    reason_eligible: Literal["无理由", "质量问题", "未签收"]
    note: Text
    is_custom: StrictBool
    is_intimate: StrictBool
    resale_condition_ok: StrictBool | None
    evidence_status: Literal["none", "uploaded_unverified"]
    quality_issue: Text | None

    @field_validator("amount", mode="before")
    @classmethod
    def reject_inexact_amount(cls, value):
        if type(value) not in (int, Decimal):
            raise ValueError("金额必须为 JSON 数值并使用 Decimal 加载，不接受浮点或字符串")
        return value

    @field_validator("signed_date", mode="before")
    @classmethod
    def parse_date(cls, value):
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("签收日期必须为 YYYY-MM-DD 或 null")
        return date.fromisoformat(value)

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "已签收" and self.signed_date is None:
            raise ValueError("已签收订单必须包含签收日期")
        if self.status == "已发货":
            if self.signed_date is not None:
                raise ValueError("未签收订单不能包含签收日期")
            if self.tags_intact is not None or self.resale_condition_ok is not None:
                raise ValueError("在途商品状态必须保持未知")
            if self.reason_eligible != "未签收":
                raise ValueError("在途订单的场景标签应为未签收")
        elif self.reason_eligible == "未签收":
            raise ValueError("已签收订单不能标注为未签收场景")
        return self

    @property
    def paid_amount_cents(self) -> int:
        return int(self.amount * 100)


class Settings(Record):
    channel: Text
    policy_version: Text
    timezone: Literal["Asia/Shanghai"]
    demo_now: datetime
    refund_limit_cents: Annotated[int, Field(strict=True, gt=0)]
    retrieval_threshold: Annotated[Decimal, Field(ge=0, le=1)]
    no_reason_days: Annotated[int, Field(strict=True, gt=0)]
    quality_days: Annotated[int, Field(strict=True, gt=0)]
    default_buyer: Text

    @field_validator("demo_now")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("演示时钟必须带时区")
        return value
