"""硬边界：仅由服务端事实、配置和用户明确请求触发，不接受模型覆盖。"""

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation

COMPLAINT_WORDS = ("投诉", "曝光", "消协", "律师")
HUMAN_REQUESTS = ("转人工", "找人工", "人工客服", "我要人工", "联系人工", "人工处理")


def normalized_input(message: str) -> str:
    return unicodedata.normalize("NFKC", message).replace("\u200b", "").strip()


def requests_human(message: str) -> bool:
    if any(word in message for word in COMPLAINT_WORDS):
        return True
    affirmative = re.sub(
        r"(?:不要|别|不想|无需|不用|不|禁止)(?:给我|说|提)?"
        r"(?:转人工|找人工|人工客服|我要人工|联系人工|人工处理)",
        "",
        message,
    )
    if any(word in affirmative for word in HUMAN_REQUESTS):
        # Explaining the audit policy is different from requesting a human agent.
        return not any(word in message for word in ("为什么", "什么情况", "是否需要"))
    return False


def mentions_other_order(message: str) -> bool:
    return bool(re.search(r"(?:别人|他人|朋友|同事|别人家)的?订单", message))


def _chinese_integer(text: str) -> int:
    digits = dict(
        zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9), strict=True)
    )
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    if all(char in digits for char in text):
        return int("".join(str(digits[char]) for char in text))
    total = section = number = 0
    for char in text:
        if char in digits:
            number = digits[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                total += (section + number) * unit
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            raise ValueError("无法解析中文金额")
    return total + section + number


def requested_money(message: str, *, continuation: bool = False) -> tuple[int | None, bool]:
    """只识别明确退款金额；非法或模糊表达不默认为零。"""
    # Ordinary return verbs contain 一 but do not specify a monetary amount.
    message = re.sub(r"退一下|退一退", "退货", message)
    pattern = re.compile(
        r"(?:退(?:款金额|款|给我|我|回|还)?|索赔|赔偿)\s*(?:为|是|要)?\s*(?:人民币|[¥￥])?\s*"
        r"([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*[万千]?|[零〇一二两三四五六七八九十百千万]+)"
    )
    matches = list(pattern.finditer(message))
    if any(
        re.match(r"[eE点.些多余来左右上下共]|(?:元|块)(?:左右|上下|多|余)", message[match.end() :])
        for match in matches
    ):
        return None, True
    values = [match.group(1) for match in matches]
    reverse = re.findall(
        r"(?:要|要求|申请|希望)\s*([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*[万千]?)"
        r"\s*元?(?:退款|赔偿|退回)",
        message,
    )
    values.extend(reverse)
    if continuation:
        bare = re.fullmatch(r"\s*([+-]?[\d,]+(?:\.\d+)?\s*[万千]?)\s*元?\s*", message)
        if bare:
            values.append(bare.group(1))
    if not values:
        unclear = bool(re.search(r"(?:退我|退给我|退款金额|索赔)", message))
        return None, unclear
    cents = []
    try:
        for text in values:
            text = text.replace(" ", "")
            if re.fullmatch(r"[零〇一二两三四五六七八九十百千万]+", text):
                amount = Decimal(_chinese_integer(text))
            else:
                if "," in text and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", text):
                    return None, True
                multiplier = {"万": 10000, "千": 1000}.get(text[-1], 1)
                numeric = text[:-1] if multiplier != 1 else text
                amount = Decimal(numeric.replace(",", "")) * multiplier
            if (
                amount <= 0
                or not amount.is_finite()
                or amount * 100 != (amount * 100).to_integral_value()
            ):
                return None, True
            cents.append(int(amount * 100))
    except (ValueError, InvalidOperation):
        return None, True
    return max(cents), False


def refund_gate_amount(paid_cents: int | None, requested_cents: int | None) -> int | None:
    amounts = [amount for amount in (paid_cents, requested_cents) if amount is not None]
    if any(type(amount) is not int or amount < 0 for amount in amounts):
        raise ValueError("退款门控仅接受非负整数分")
    return max(amounts) if amounts else None


def exceeds_refund_limit(amount_cents: int | None, limit_cents: int) -> bool:
    return amount_cents is not None and amount_cents > limit_cents


def sufficient_evidence(score: float, threshold: float) -> bool:
    return math.isfinite(score) and 0 <= score <= 1 and score >= threshold


def policy_questions(message: str) -> tuple[str, ...]:
    """每个明确子问题分别检索，避免只回答其中有依据的一半。"""
    parts = re.split(r"[，,；;？?]+|以及|另外|同时|并且|和", message)
    return tuple(part.strip() for part in parts if part.strip()) or (message,)


def uncovered_aspects(message: str) -> tuple[str, ...]:
    """本套政策未覆盖的显式主题也必须独立检索，不被已知主题掩盖。"""
    return tuple(word for word in ("取件", "花呗", "分期") if word in message)
