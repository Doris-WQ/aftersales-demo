"""可观察的售后编排：代码门控先于模型，工单仅为本地模拟记录。"""

import hashlib
import math
from time import perf_counter
from uuid import uuid4

from aftersales.clock import within_window
from aftersales.contracts import (
    ChatRequest,
    ChatResponse,
    HandoffRequest,
    HandoffResult,
    TraceEvent,
)
from aftersales.data import Dataset
from aftersales.generation import (
    SAFE_GENERATION_ERRORS,
    GenerationError,
    Generator,
    validate_evidence,
)
from aftersales.handoffs import HandoffService, HandoffUnavailable
from aftersales.orders import OrderClient, OrderNotFound, OrderUnavailable
from aftersales.parsing import extract_intent
from aftersales.reply import policy_reply
from aftersales.retrieval import PolicyRetriever
from aftersales.return_policy import plan_return
from aftersales.rules import (
    exceeds_refund_limit,
    mentions_other_order,
    normalized_input,
    policy_questions,
    refund_gate_amount,
    requests_human,
    sufficient_evidence,
    uncovered_aspects,
)
from aftersales.sessions import Session, SessionStore


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class Agent:
    def __init__(
        self,
        dataset: Dataset,
        orders: OrderClient,
        generator: Generator,
        retriever: PolicyRetriever | None = None,
    ):
        self.dataset = dataset
        self.orders = orders
        self.generator = generator
        self.retriever = retriever or PolicyRetriever(dataset.policies)
        self.sessions = SessionStore()
        self.handoffs = HandoffService(dataset.clock)
        self.policies = {p.id: p for p in dataset.policies}

    async def chat(self, request: ChatRequest, buyer: str, token: str) -> ChatResponse:
        session = self.sessions.get_or_create(request.session_id, buyer)
        async with session.lock:
            response = await self._turn(normalized_input(request.message), session, token)
            session.history.append(response)
            return response

    async def request_handoff(self, request: HandoffRequest, buyer: str) -> HandoffResult:
        started = perf_counter()
        session = self.sessions.get_or_create(request.session_id, buyer)
        async with session.lock:
            # Reject stale buttons after a new turn or an order change.
            if not session.history or session.history[-1].trace_id != request.trace_id:
                raise HandoffUnavailable
            response = session.history[-1]
            if response.handoff_id:
                ticket = self.handoffs.get(response.handoff_id, buyer, session.session_id)
                return HandoffResult(ticket=ticket, reused=True)
            if not response.handoff_available:
                raise HandoffUnavailable
            result = self.handoffs.create(
                buyer=buyer,
                session_id=session.session_id,
                issue_key=session.issue_keys[request.trace_id],
                source_trace_id=request.trace_id,
                order_id=response.order.order_id if response.order else None,
                reason_code=f"manual_{response.reason_code}",
                summary="用户通过已授权的当前事项入口请求人工核实；不承诺处理结果。",
            )
            events = (
                TraceEvent(
                    event_id=uuid4().hex,
                    step="handoff",
                    status="ok",
                    summary="已创建模拟转人工记录" if not result.reused else "复用已有模拟工单",
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    data={
                        "handoff_id": result.ticket.handoff_id,
                        "reused": result.reused,
                        "source": "manual_entry",
                    },
                ),
            )
            return result.model_copy(update={"trace_events": events})

    async def _turn(self, message: str, session: Session, token: str) -> ChatResponse:
        events = []
        triggered = []
        trace_id = uuid4().hex
        started = perf_counter()
        intent = extract_intent(message, session.pending)
        order = None

        def event(step, summary, data=None, status="ok", since=None):
            events.append(
                TraceEvent(
                    event_id=uuid4().hex,
                    step=step,
                    status=status,
                    summary=summary,
                    duration_ms=round((perf_counter() - (since or started)) * 1000, 3),
                    data=data or {},
                )
            )

        def rule(rule_id, summary, data=None):
            if rule_id not in triggered:
                triggered.append(rule_id)
            event("rule", summary, {"rule_id": rule_id, **(data or {})}, "blocked")

        event("intent", "识别意图与明确槽位", intent.model_dump())

        def finish(
            action,
            text,
            reason,
            *,
            missing=(),
            policies=(),
            score=None,
            available=False,
            ticket=None,
            issue_key=None,
        ):
            if action == "answer":
                session.last_answer_question = message
            event("action", text, {"action": action, "reason_code": reason})
            session.issue_keys[trace_id] = issue_key or (
                f"manual:{order.order_id}:{reason}"
                if order
                else session.policy_issue_key or f"manual:{reason}:{_key(message)}"
            )
            return ChatResponse(
                session_id=session.session_id,
                action=action,
                message=text,
                business_answer=text if action in ("answer", "query_result") else None,
                policy_ids=tuple(p.id for p in policies),
                retrieval_score=score,
                reason_code=reason,
                missing_fields=missing,
                handoff_available=available,
                handoff_id=ticket.handoff_id if ticket else None,
                trace_id=trace_id,
                order=order,
                policy_cards=policies,
                trace_events=tuple(events),
                mode=self.generator.mode,
                triggered_rules=tuple(triggered),
            )

        def auto_handoff(
            reason, text, *, policies=(), issue_key=None, ticket_order_id=None, score=None
        ):
            identity = ticket_order_id or (order.order_id if order else None)
            issue_key = issue_key or f"{reason}:{identity or 'unbound'}"
            result = self.handoffs.create(
                buyer=session.buyer,
                session_id=session.session_id,
                issue_key=issue_key,
                source_trace_id=trace_id,
                order_id=identity,
                reason_code=reason,
                summary=text,
            )
            event(
                "handoff",
                "复用已有模拟工单" if result.reused else "已创建模拟转人工记录",
                {"handoff_id": result.ticket.handoff_id, "reused": result.reused},
            )
            return finish(
                "handoff",
                text
                + (
                    " 已有模拟工单会继续用于这件事，不需要重复提交；目前尚未接入真实客服。"
                    if result.reused
                    else " 已为你创建模拟转人工工单，方便后续核实；目前尚未接入真实客服。"
                ),
                reason,
                policies=policies,
                ticket=result.ticket,
                issue_key=issue_key,
                score=score,
            )

        def amount_handoff(gate_amount):
            rule(
                "R1",
                "退款金额超过阈值，强制人工审核",
                {
                    "gate_amount_cents": gate_amount,
                    "paid_amount_cents": order.paid_amount_cents if order else None,
                    "requested_amount_cents": session.requested_amount_cents,
                    "limit_cents": self.dataset.settings.refund_limit_cents,
                },
            )
            policies = (self.policies["P12"],)
            amount = f"{gate_amount / 100:g}"
            text = (
                f"[P12] 这次涉及的退款金额为{amount}元，超过500元，需要人工审核后才能确认退款结果。"
            )
            if (
                order
                and session.reason == "质量问题"
                and order.signed_date
                and within_window(
                    order.signed_date, self.dataset.settings.quality_days, self.dataset.clock
                )
            ):
                policies += (self.policies["P06"],)
                text += " [P06] 该质量问题在政策适用范围内，凭证仍需核验。"
            event(
                "retrieval",
                "检索未执行；规则直接引用政策",
                {"source": "code_rule", "policy_ids": [p.id for p in policies]},
                "skipped",
            )
            return auto_handoff("amount_limit", text, policies=policies)

        # R3 is evaluated before missing slots and retrieval, without fetching foreign orders.
        if requests_human(message):
            rule("R3", "投诉或明确人工请求，直接转人工")
            safe_id = intent.order_id or session.order_id
            if (
                mentions_other_order(message)
                or safe_id not in self.dataset.ownership[session.buyer]
            ):
                safe_id = None
            return auto_handoff(
                "complaint"
                if any(w in message for w in ("投诉", "曝光", "消协", "律师"))
                else "human_requested",
                "已收到你的诉求，需要人工核实处理。",
                issue_key=f"R3:{_key(message)}",
                ticket_order_id=safe_id,
            )
        if mentions_other_order(message):
            event("scope", "停止查询他人订单，未调用订单工具", status="blocked")
            return finish("refuse", "只能查询当前演示身份自己的订单。", "other_order")
        if intent.ambiguous:
            if exceeds_refund_limit(
                intent.requested_amount_cents, self.dataset.settings.refund_limit_cents
            ):
                session.requested_amount_cents = intent.requested_amount_cents
                return amount_handoff(intent.requested_amount_cents)
            return finish(
                "clarify",
                "请一次提供一个需要处理的订单号。",
                "multiple_orders",
                missing=("order_id",),
            )
        if intent.order_id:
            session.switch_order(intent.order_id)
        if intent.reason and intent.kind == "return":
            session.reason = intent.reason
        if intent.requested_amount_cents is not None and intent.kind == "return":
            session.requested_amount_cents = max(
                session.requested_amount_cents or 0, intent.requested_amount_cents
            )

        if not intent.order_id and any(w in message for w in ("去年", "前年", "多年前")):
            rule("R4", "个案超出当前自动政策判断范围")
            return finish(
                "clarify",
                "当前无法确认该个案，请通过转人工入口进一步核实。",
                "policy_out_of_range",
                available=True,
                issue_key=f"out_of_range:{_key(message)}",
            )

        plan = None
        if intent.kind in ("return", "order_query"):
            if session.order_id is None:
                if intent.kind == "return" and exceeds_refund_limit(
                    session.requested_amount_cents, self.dataset.settings.refund_limit_cents
                ):
                    return amount_handoff(session.requested_amount_cents)
                session.pending = "order_id"
                event("slots", "缺少订单号，未执行订单查询或政策检索", {"missing": ["order_id"]})
                return finish(
                    "clarify",
                    (
                        "退货原因已记下了，请再提供订单号，我才能查看这件商品的情况。"
                        if session.reason
                        else "可以先帮你看看。请发一下订单号，再说说为什么想退，"
                        "比如尺码不合或商品有问题。"
                    ),
                    "missing_order_id",
                    missing=("order_id",) if session.reason else ("order_id", "reason"),
                )
            query_started = perf_counter()
            try:
                order = await self.orders.get(session.order_id, token)
                event(
                    "order_query",
                    "已调用模拟订单 HTTP 接口",
                    {
                        "path": f"/api/mock/orders/{session.order_id}",
                        "transport": "in_process_asgi",
                        "status_code": 200,
                        "order_id": order.order_id,
                        "paid_amount_cents": order.paid_amount_cents,
                    },
                    since=query_started,
                )
            except OrderNotFound:
                event(
                    "order_query",
                    "接口返回 404",
                    {"status_code": 404},
                    "blocked",
                    since=query_started,
                )
                session.order_id = session.reason = session.requested_amount_cents = None
                session.pending = "order_id"
                if intent.kind == "return" and exceeds_refund_limit(
                    intent.requested_amount_cents, self.dataset.settings.refund_limit_cents
                ):
                    session.requested_amount_cents = intent.requested_amount_cents
                    return amount_handoff(intent.requested_amount_cents)
                return finish(
                    "clarify",
                    "查不到订单，请核对单号或当前演示身份。",
                    "order_not_found",
                    missing=("order_id",),
                )
            except OrderUnavailable:
                event("order_query", "订单接口暂时不可用", status="error", since=query_started)
                return finish(
                    "clarify", "暂时无法查询订单，请稍后重试。", "order_unavailable", available=True
                )
            if intent.kind == "order_query":
                session.pending = None
                text = (
                    f"订单 {order.order_id}：{order.item}，"
                    f"实付 ¥{order.amount:.2f}，{order.status}。"
                )
                return finish("query_result", text, "order_found")
            gate_amount = refund_gate_amount(
                order.paid_amount_cents, session.requested_amount_cents
            )
            event(
                "amount_check",
                "按实付金额与请求金额较大值检查",
                {
                    "paid_amount_cents": order.paid_amount_cents,
                    "requested_amount_cents": session.requested_amount_cents,
                    "gate_amount_cents": gate_amount,
                    "limit_cents": self.dataset.settings.refund_limit_cents,
                },
            )
            if exceeds_refund_limit(gate_amount, self.dataset.settings.refund_limit_cents):
                return amount_handoff(gate_amount)
            if intent.invalid_amount:
                session.pending = "amount"
                return finish(
                    "clarify",
                    "请明确希望申请的退款金额，最多保留两位小数。",
                    "invalid_requested_amount",
                    missing=("amount",),
                    available=True,
                )
            plan = plan_return(
                order, session.reason, message, self.dataset.settings, self.dataset.clock
            )
            session.pending = plan.pending
            if not plan.queries:
                if plan.reason == "policy_out_of_range":
                    rule("R4", "超出政策自动判断范围，不编造结论")
                return finish(
                    plan.action,
                    plan.text,
                    plan.reason,
                    missing=plan.missing,
                    available=plan.manual_available,
                )
            queries = plan.queries
        else:
            queries = tuple((query, None) for query in policy_questions(message))

        queries += tuple((query, None) for query in uncovered_aspects(message))

        selected = {}
        scores = []
        for query, required_id in queries:
            retrieval_started = perf_counter()
            hits = self.retriever.search(query)
            raw_score = hits[0].score if hits else 0.0
            score = raw_score if math.isfinite(raw_score) else 0.0
            scores.append(score)
            event(
                "retrieval",
                "政策库真实检索",
                {
                    "query": query,
                    "required_policy_id": required_id,
                    "hits": [
                        {
                            "id": h.policy.id,
                            "score": h.score if math.isfinite(h.score) else None,
                            "matched_field": h.matched_field,
                        }
                        for h in hits
                    ],
                    "threshold": float(self.dataset.settings.retrieval_threshold),
                },
                since=retrieval_started,
            )
            if not sufficient_evidence(score, float(self.dataset.settings.retrieval_threshold)):
                topic = (
                    "pickup"
                    if "取件" in message
                    else "payment"
                    if any(w in message for w in ("花呗", "分期"))
                    else intent.topic
                )
                if topic and session.policy_issue_topic and topic != session.policy_issue_topic:
                    session.policy_issue_key = None
                    session.unanswered_count = 0
                    session.last_unanswered_message = None
                session.policy_issue_topic = topic or session.policy_issue_topic
                rule(
                    "R2",
                    "top1 低于门槛或分数无效，只追问、不生成政策答案",
                    {"score": score, "threshold": float(self.dataset.settings.retrieval_threshold)},
                )
                if session.last_unanswered_message != message:
                    session.unanswered_count += 1
                    session.last_unanswered_message = message
                session.policy_issue_key = session.policy_issue_key or f"policy:{_key(message)}"
                session.pending = "question"
                rule(
                    "R4",
                    "当前无法确认，提供转人工入口，不自动创建工单",
                    {"clarification_turns": session.unanswered_count},
                )
                event("generation", "证据不足，未调用答案生成器", status="skipped")
                return finish(
                    "clarify",
                    "当前无法确认，请补充具体问题或订单号，也可通过入口转人工。",
                    "low_confidence",
                    missing=("question",),
                    score=score,
                    available=True,
                )
            if required_id and hits[0].policy.id != required_id:
                rule("R4", "匹配来源与所需政策不一致，不输出资格结论")
                return finish(
                    "clarify",
                    "当前无法确认适用政策，请补充问题或通过入口转人工。",
                    "policy_source_mismatch",
                    score=score,
                    available=True,
                )
            selected[hits[0].policy.id] = hits[0].policy
        policies = tuple(selected.values())
        score = min(scores)
        if plan and plan.action == "handoff":
            event(
                "policy_check",
                "已通过证据门控，质量与凭证需人工核验",
                {"policy_ids": [p.id for p in policies]},
            )
            return auto_handoff(plan.reason, plan.text, policies=policies, score=score)
        if plan and plan.action == "clarify":
            text = plan.text
            event("generation", "追问使用已检索政策与固定文本，未调用答案生成器", status="skipped")
            return finish(
                "clarify",
                text,
                plan.reason,
                policies=policies,
                score=score,
                missing=plan.missing,
                available=plan.manual_available,
            )

        generation_started = perf_counter()
        try:
            result = await self.generator.generate(message, policies)
            validate_evidence(result, policies)
        except GenerationError as error:
            rule("R4", "模型不可用或证据校验失败，不能确认答案")
            event(
                "generation",
                "未输出未经验证的模型结果",
                {
                    "error_code": str(error)
                    if str(error) in SAFE_GENERATION_ERRORS
                    else "generation_failed",
                    "provider_code": error.provider_code,
                },
                status="error",
                since=generation_started,
            )
            return finish(
                "clarify",
                "当前无法确认，请补充具体问题或通过入口转人工。",
                "generation_failed",
                score=score,
                available=True,
            )
        event(
            "generation",
            "证据引用已校验；业务文本由服务端呈现",
            {
                "mode": self.generator.mode,
                "policy_ids": list(result.policy_ids),
                "model": getattr(getattr(self.generator, "config", None), "model", None),
                "transport": getattr(
                    getattr(self.generator, "config", None), "transport", "offline"
                ),
            },
            since=generation_started,
        )
        session.policy_issue_key = None
        session.policy_issue_topic = None
        session.unanswered_count = 0
        session.last_unanswered_message = None
        if session.pending == "question":
            session.pending = None
        # Order plans already explain the decision. Do not repeat the same constraints
        # by appending complete policy paragraphs to every customer reply.
        text = plan.text if plan else policy_reply(policies)
        if plan and "P07" in selected:
            text += " " + policy_reply(policies)
        if session.history:
            previous = session.history[-1]
            if (
                previous.action == "answer"
                and session.last_answer_question == message
                and previous.policy_ids == tuple(p.id for p in policies)
                and previous.order == order
                and previous.reason_code == (plan.reason if plan else "evidence_answer")
            ):
                text = (
                    "重新核对后，结论没有变化。"
                    "你还想确认哪一点？可以具体说说条件、运费或退款时间，我再接着帮你看。"
                )
        return finish(
            "answer",
            text,
            plan.reason if plan else "evidence_answer",
            policies=policies,
            score=score,
            available=plan.manual_available if plan else False,
        )
