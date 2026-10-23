"""Calendar dates use the business timezone; audit/session instants stay UTC."""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def business_timezone() -> ZoneInfo:
    name = os.getenv("APP_TIMEZONE", "Europe/Moscow")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise RuntimeError("APP_TIMEZONE must be an installed IANA timezone") from error


def business_today(instant: datetime | None = None) -> date:
    """Date of an aware instant (or now), independent of the host timezone."""
    zone = business_timezone()
    if instant is None:
        return datetime.now(zone).date()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Business clock requires a timezone-aware instant")
    return instant.astimezone(zone).date()
