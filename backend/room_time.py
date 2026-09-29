"""Shared timestamp formatting for room API payloads."""

from datetime import datetime, timedelta, timezone


def to_beijing_time(dt: datetime) -> datetime:
    """将UTC时间转换为北京时间（东八区）"""
    if dt.tzinfo is None:
        # 如果时间没有时区信息，假设是UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=8)))
