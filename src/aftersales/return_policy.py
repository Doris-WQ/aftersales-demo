"""根据订单事实选择待检索政策；结论在证据门控后才可输出。"""

from dataclasses import dataclass
from typing import Literal

from aftersales.clock import DemoClock, within_window
from aftersales.models import Order, Settings


@dataclass(frozen=True)
class ReturnPlan:
    queries: tuple[tuple[str, str], ...]
    text: str
    action: Literal["answer", "clarify", "handoff"] = "answer"
    reason: str = "evidence_answer"
    missing: tuple[str, ...] = ()
    pending: str | None = None
    manual_available: bool = False


def plan_return(
    order: Order, reason: str | None, message: str, settings: Settings, clock: DemoClock
) -> ReturnPlan:
    if order.status == "已发货":
        return ReturnPlan((("已发货未签收", "P07"),), f"订单 {order.order_id} 已发货、未签收。")
    if reason == "质量问题":
        if not within_window(order.signed_date, settings.quality_days, clock):
            return ReturnPlan(
                (),
                "当前无法确认该个案，已超出质量问题的自动政策判断范围，请人工核实。",
                action="clarify",
                reason="policy_out_of_range",
                manual_available=True,
            )
        if order.evidence_status == "none":
            return ReturnPlan(
                (("质量问题退货", "P06"),),
                "请提供质量问题图片凭证；当前未收到凭证，不能确认核验结果。",
                action="clarify",
                reason="missing_evidence",
                missing=("evidence",),
                pending="evidence",
                manual_available=True,
            )
        return ReturnPlan(
            (("质量问题退货", "P06"),),
            "质量问题在政策适用范围内，图片已上传但尚未核验，需人工核实退货条件。",
            action="handoff",
            reason="quality_review",
        )
    if not within_window(order.signed_date, settings.no_reason_days, clock):
        return ReturnPlan(
            (("超过七天的处理", "P05"),),
            f"订单 {order.order_id} 已超七天，原则上不支持无理由退货，需人工判断。"
            + ("请说明是否属于质量问题。" if reason is None else ""),
            action="clarify" if reason is None else "answer",
            reason="expired_order",
            missing=("reason",) if reason is None else (),
            pending="reason" if reason is None else None,
            manual_available=True,
        )
    if reason is None and "能退" not in message:
        return ReturnPlan(
            (),
            "已查到订单，请说明退货原因，例如尺码不合或质量问题。",
            action="clarify",
            reason="missing_reason",
            missing=("reason",),
            pending="reason",
        )
    if order.is_custom:
        return ReturnPlan((("定制类商品", "P10"),), "定制商品不支持无理由退货。")
    if order.is_intimate:
        return ReturnPlan((("贴身类商品", "P09"),), "贴身类商品签收后不支持无理由退货。")
    if order.tags_intact is None or order.resale_condition_ok is None:
        return ReturnPlan(
            (),
            "请确认吊牌是否完好、商品是否影响二次销售。",
            action="clarify",
            reason="missing_condition",
            missing=("condition",),
            pending="condition",
            manual_available=True,
        )
    queries = (("七天无理由退货", "P01"), ("吊牌与包装要求", "P02"))
    if not order.tags_intact or not order.resale_condition_ok:
        return ReturnPlan(
            queries,
            "当前商品条件不符合无理由退货要求；质量争议可由人工核实。",
            manual_available=True,
        )
    text = "按当前订单信息符合无理由退货条件，可退；吊牌完好且不影响二次销售。"
    if reason is None:
        text += "请补充退货原因；这不表示已受理退货。"
    return ReturnPlan(queries, text, pending="reason" if reason is None else None)
