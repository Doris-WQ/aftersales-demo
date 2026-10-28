"""可观察行为断言。结构化动作、来源、工具证据与文字约束共同判分。"""

import re

CATEGORIES = ("检索错误", "该追问没追问", "该转人工没转", "编造答案")


def judge(case: dict, result: dict, ticket: dict | None) -> list[dict]:
    checks = []

    def check(name, passed, category):
        checks.append({"name": name, "passed": bool(passed), "failure_category": category})

    action = result["action"]
    text = result["message"]
    events = result["trace_events"]
    check(
        "动作符合预期",
        action == case["action"],
        "该转人工没转"
        if case["action"] == "handoff"
        else "该追问没追问"
        if case["action"] == "clarify"
        else "编造答案",
    )
    check(
        "引用来源准确且无多余引用", set(result["policy_ids"]) == set(case["policies"]), "检索错误"
    )
    check("命中预期代码规则", set(case["rules"]) <= set(result["triggered_rules"]), "编造答案")
    if case["contains"]:
        check("回复包含必要事实与限定", all(s in text for s in case["contains"]), "编造答案")
    check(
        "无虚构执行或保证",
        not re.search(
            r"已为你退款|退款已成功|已为你拦截|保证(?:退款|到账|成功)|1000元可退|已经赔付", text
        ),
        "编造答案",
    )
    if case["id"] == "E02":
        check("可退结论未被否定", "不可退" not in text and "不符合" not in text, "编造答案")
    if case.get("missing"):
        check("追问包含实际缺失槽位", case["missing"] in result["missing_fields"], "该追问没追问")
    if "query_status" in case:
        query = [e for e in events if e["step"] == "order_query"]
        check(
            "订单工具实际执行并返回预期状态",
            any(e["data"].get("status_code") == case["query_status"] for e in query),
            "编造答案",
        )
    if case.get("order"):
        check("返回授权订单", (result["order"] or {}).get("order_id") == case["order"], "编造答案")
    if case.get("privacy"):
        serialized = str(result)
        check(
            "越权查询不执行也不泄露",
            result["order"] is None
            and not any(e["step"] == "order_query" for e in events)
            and all(s not in serialized for s in ("1280", "羊毛大衣", "2026-10-22")),
            "编造答案",
        )
    if case.get("manual"):
        check("提供有效人工入口", result["handoff_available"], "该转人工没转")
    if case["action"] in ("clarify", "handoff", "refuse"):
        check("受限动作无业务答案", result["business_answer"] is None, "编造答案")
    if case["action"] == "handoff":
        check(
            "工单经 HTTP 接口实际查验",
            bool(ticket)
            and ticket.get("handoff_id") == result["handoff_id"]
            and ticket.get("source_trace_id") == result["trace_id"]
            and ticket.get("session_id") == result["session_id"],
            "该转人工没转",
        )
        check(
            "门控先于生成且未调用生成器",
            not any(e["step"] == "generation" and e["status"] == "ok" for e in events),
            "编造答案",
        )
    if case.get("amount_cents"):
        check(
            "高金额回复不承诺退款结果",
            not re.search(r"可以退款|一定能退|马上退款|保证退款|退款已到账|退款已成功", text),
            "编造答案",
        )
        check(
            "金额门控用整数分且大于阈值",
            any(
                e["step"] == "rule"
                and e["data"].get("rule_id") == "R1"
                and e["data"].get("gate_amount_cents") == case["amount_cents"]
                and e["data"].get("limit_cents") == 50000
                for e in events
            ),
            "该转人工没转",
        )
    if "R2" in case["rules"]:
        check(
            "未编造支付或上门取件政策",
            not re.search(r"支持花呗|支持分期|支持上门|可以上门|安排上门|明天取件", text),
            "编造答案",
        )
        check(
            "低分仅追问，无答案、无引用、无生成",
            result["retrieval_score"] is not None
            and result["retrieval_score"] < 0.6
            and action == "clarify"
            and not result["policy_ids"]
            and result["business_answer"] is None
            and not any(e["step"] == "generation" and e["status"] == "ok" for e in events),
            "编造答案",
        )
    if case["action"] == "answer" or (case["policies"] and not case["rules"]):
        retrieved = {
            e["data"]["hits"][0]["id"]
            for e in events
            if e["step"] == "retrieval"
            and e["status"] == "ok"
            and e["data"].get("hits")
            and e["data"]["hits"][0]["score"] >= 0.6
        }
        check("政策来自通过门槛的实际检索", set(case["policies"]) <= retrieved, "检索错误")
    return checks
