"""主流程的输入输出契约，供后续三栏页面使用。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from aftersales.models import Order, OrderId, Policy, Record, Text


class ChatRequest(Record):
    session_id: str | None = None
    message: Annotated[str, Field(strict=True, min_length=1, max_length=2000, pattern=r"\S")]


class Intent(Record):
    kind: Literal["policy", "order_query", "return", "unknown"]
    order_id: OrderId | None = None
    reason: Literal["无理由", "尺码不合", "质量问题"] | None = None
    topic: str | None = None
    ambiguous: bool = False
    requested_amount_cents: int | None = None
    invalid_amount: bool = False


class TraceEvent(Record):
    event_id: str
    step: str
    status: Literal["ok", "skipped", "blocked", "error"]
    summary: str
    duration_ms: float
    data: dict = Field(default_factory=dict)


class ChatResponse(Record):
    session_id: str
    action: Literal["answer", "query_result", "clarify", "handoff", "refuse"]
    message: str
    business_answer: str | None = None
    policy_ids: tuple[str, ...] = ()
    retrieval_score: float | None = None
    reason_code: str
    missing_fields: tuple[str, ...] = ()
    handoff_available: bool = False
    handoff_id: str | None = None
    trace_id: str
    order: Order | None = None
    policy_cards: tuple[Policy, ...] = ()
    trace_events: tuple[TraceEvent, ...]
    mode: Literal["offline", "live"]
    triggered_rules: tuple[Literal["R1", "R2", "R3", "R4"], ...] = ()
    development_stage: int = 5

    @model_validator(mode="after")
    def action_contract(self):
        if self.action not in ("answer", "query_result") and self.business_answer is not None:
            raise ValueError("追问、拒绝或转人工不得包含业务答案")
        if self.action == "handoff" and not self.handoff_id:
            raise ValueError("转人工必须对应已创建的工单")
        return self


class HandoffRequest(Record):
    session_id: Text
    trace_id: Text


class HandoffTicket(Record):
    handoff_id: str
    session_id: str
    source_trace_id: str
    order_id: str | None
    reason_code: str
    summary: str
    created_at: str
    status: Literal["simulated_created"] = "simulated_created"


class HandoffResult(Record):
    ticket: HandoffTicket
    reused: bool
    trace_events: tuple[TraceEvent, ...] = ()


class GeneratedAnswer(Record):
    """模型只能选择证据，最终业务文本由服务端重建。"""

    policy_ids: tuple[Text, ...]
    evidence_quotes: tuple[Text, ...]
