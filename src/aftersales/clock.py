"""可注入的固定时钟；时限按上海日历日计算。"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DemoClock:
    instant: datetime

    def __post_init__(self):
        if self.instant.tzinfo is None or self.instant.utcoffset() is None:
            raise ValueError("时钟必须带时区")

    def now(self) -> datetime:
        return self.instant.astimezone(SHANGHAI)

    def today(self) -> date:
        return self.now().date()


def window_end(signed_date: date, days: int) -> datetime:
    """签收日为第 0 天，截止到第 days 天的最后一微秒。"""
    if type(days) is not int or days <= 0:
        raise ValueError("天数必须为正整数")
    return datetime.combine(signed_date + timedelta(days=days), time.max, SHANGHAI)


def within_window(signed_date: date, days: int, clock: DemoClock) -> bool:
    return signed_date <= clock.today() and clock.now() <= window_end(signed_date, days)
