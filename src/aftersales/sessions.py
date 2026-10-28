"""单进程内存会话；调用方不得从用户文本设置身份。"""

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from aftersales.contracts import ChatResponse


class SessionNotFound(Exception):
    pass


@dataclass
class Session:
    session_id: str
    buyer: str
    order_id: str | None = None
    reason: str | None = None
    pending: str | None = None
    requested_amount_cents: int | None = None
    unanswered_count: int = 0
    last_unanswered_message: str | None = None
    policy_issue_key: str | None = None
    policy_issue_topic: str | None = None
    issue_keys: dict[str, str] = field(default_factory=dict)
    history: list[ChatResponse] = field(default_factory=list)
    last_answer_question: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def switch_order(self, order_id: str):
        if order_id != self.order_id:
            self.order_id = order_id
            self.reason = None
            self.pending = None
            self.requested_amount_cents = None
            self.unanswered_count = 0
            self.last_unanswered_message = None
            self.policy_issue_key = None
            self.policy_issue_topic = None


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None, buyer: str) -> Session:
        if session_id is None:
            session = Session(uuid4().hex, buyer)
            self._sessions[session.session_id] = session
            return session
        session = self._sessions.get(session_id)
        if session is None or session.buyer != buyer:
            raise SessionNotFound
        return session
