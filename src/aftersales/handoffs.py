"""本地模拟工单；仅存内存，不声称真实客服接入。"""

from threading import Lock

from aftersales.clock import DemoClock
from aftersales.contracts import HandoffResult, HandoffTicket


class TicketNotFound(Exception):
    pass


class HandoffUnavailable(Exception):
    pass


class HandoffService:
    def __init__(self, clock: DemoClock):
        self.clock = clock
        self._entries: dict[str, tuple[str, HandoffTicket]] = {}
        self._keys: dict[tuple[str, str, str], str] = {}
        self._counter = 0
        self._lock = Lock()

    def create(
        self,
        *,
        buyer: str,
        session_id: str,
        issue_key: str,
        source_trace_id: str,
        order_id: str | None,
        reason_code: str,
        summary: str,
    ) -> HandoffResult:
        key = (buyer, session_id, issue_key)
        with self._lock:
            existing = self._keys.get(key)
            if existing:
                return HandoffResult(ticket=self._entries[existing][1], reused=True)
            self._counter += 1
            handoff_id = f"TK-{self.clock.today():%Y%m%d}-{self._counter:04d}"
            ticket = HandoffTicket(
                handoff_id=handoff_id,
                session_id=session_id,
                source_trace_id=source_trace_id,
                order_id=order_id,
                reason_code=reason_code,
                summary=summary,
                created_at=self.clock.now().isoformat(),
            )
            self._entries[handoff_id] = (buyer, ticket)
            self._keys[key] = handoff_id
            return HandoffResult(ticket=ticket, reused=False)

    def get(self, handoff_id: str, buyer: str, session_id: str) -> HandoffTicket:
        entry = self._entries.get(handoff_id)
        if entry is None or entry[0] != buyer or entry[1].session_id != session_id:
            raise TicketNotFound
        return entry[1]
