"""与 ORM 无关的小工具，避免 db 与 models 循环导入。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    """统一存 UTC naive 时间，接口层再补时区标记。"""
    return datetime.now(UTC).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=UTC).isoformat() if value else None
