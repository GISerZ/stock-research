"""Beijing market phases; completed dates require actual available trade dates."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

BJ_TZ = timezone(timedelta(hours=8))
MARKET_PHASES = {"premarket", "intraday", "lunch_break", "closing_auction",
                 "postmarket", "non_trading", "unknown"}


def normalize_market_phase(value: str | None) -> str:
    if not isinstance(value, str):
        return "unknown"
    value = {"continuous": "intraday", "post_close": "postmarket"}.get(value, value)
    # Historical auction does not distinguish opening from closing auction.
    return value if value in MARKET_PHASES else "unknown"


def classify_market_phase(now: datetime, *, is_trading_day: bool | None,
                          quote_time: datetime | None = None) -> str:
    if is_trading_day is None or now.tzinfo is None or (quote_time is not None and quote_time.tzinfo is None):
        return "unknown"
    local = now.astimezone(BJ_TZ)
    if not is_trading_day:
        return "non_trading"
    if quote_time is not None and quote_time.astimezone(BJ_TZ) > local + timedelta(minutes=5):
        return "unknown"
    clock = local.time()
    if clock < time(9, 30):
        return "premarket"
    if clock < time(11, 30):
        return "intraday"
    if clock < time(13):
        return "lunch_break"
    if clock < time(14, 57):
        return "intraday"
    if clock < time(15):
        return "closing_auction"
    return "postmarket"


def effective_daily_bar_date(now: datetime, *, latest_available: date | None = None) -> date | None:
    """Do not infer holidays from weekdays or invent an unavailable bar."""
    if now.tzinfo is None:
        raise ValueError("now needs a timezone")
    if latest_available is None:
        return None
    local = now.astimezone(BJ_TZ)
    if latest_available > local.date() or (latest_available == local.date() and local.time() < time(15)):
        return None
    return latest_available
