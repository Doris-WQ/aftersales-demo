"""本阶段用可观察规则提取明确槽位，模糊表达保持未知。"""

import re

from aftersales.contracts import Intent
from aftersales.rules import requested_money

ORDER_PATTERN = re.compile(r"(?<![A-Z0-9])ORD-[0-9]{4}(?![A-Z0-9])", re.IGNORECASE)


def extract_intent(message: str, pending: str | None = None) -> Intent:
    ids = tuple(dict.fromkeys(m.upper() for m in ORDER_PATTERN.findall(message)))
    amount, invalid_amount = requested_money(message, continuation=pending == "amount")
    reason = None
    reason_text = re.sub(r"(?:不是|没有|并非|非|没)(?:质量问题|开线|破洞|色差)", "", message)
    if any(w in reason_text for w in ("开线", "破洞", "色差", "质量问题")):
        reason = "质量问题"
    elif any(w in message for w in ("尺码不合", "太大", "太小", "不合身")):
        reason = "尺码不合"
    elif any(w in message for w in ("无理由", "不喜欢", "不想要")):
        reason = "无理由"
    order_id = ids[0] if len(ids) == 1 else None
    topic = None
    for name, words in (
        ("refund_time", ("多久到账", "到账时间", "几个工作日", "什么时候到账")),
        ("shipping_fee", ("运费", "邮费", "寄回去的钱")),
        ("return_window", ("七天", "七日", "哪天算", "哪天开始", "退货期限")),
        ("tags", ("吊牌", "水洗标", "穿着痕迹")),
        ("exchange", ("换货", "换尺码", "换大一码")),
        ("amount_policy", ("高金额退款", "金额阈值", "超过500", "超过 500")),
    ):
        if any(word in message for word in words):
            topic = name
            break
    general_policy_question = any(
        word in message for word in ("取件", "分期", "优惠券", "积分", "定制", "贴身")
    )
    if (topic is not None or general_policy_question) and not ids and amount is None:
        kind = "policy"
    elif (
        amount is not None
        or invalid_amount
        or any(w in message for w in ("退货", "退款", "能退", "退一下", "退我", "退给我"))
    ):
        kind = "return"
    elif ids and any(w in message for w in ("查", "状态", "物流", "到哪")):
        kind = "order_query"
    elif pending in ("order_id", "reason") and (ids or reason):
        kind = "return"
    elif ids:
        kind = "order_query"
    elif reason and pending:
        kind = "return"
    else:
        kind = "policy" if "？" in message or "吗" in message else "unknown"
    return Intent(
        kind=kind,
        order_id=order_id,
        reason=reason,
        topic=topic,
        ambiguous=len(ids) > 1,
        requested_amount_cents=amount,
        invalid_amount=invalid_amount,
    )
