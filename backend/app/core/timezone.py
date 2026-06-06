from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from zoneinfo._common import ZoneInfoNotFoundError


try:
    CHINA_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def china_now() -> datetime:
    return datetime.now(CHINA_TZ).replace(tzinfo=None)


def china_now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat()
