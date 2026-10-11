"""Daily reference quotes, independent from saved expense valuations."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from app.common.errors import AppError
from app.db.models.ledger import RateQuote

SHANGHAI = ZoneInfo("Asia/Shanghai")


def today():
    return datetime.now(SHANGHAI).date()


class FrankfurterProvider:
    url = "https://api.frankfurter.dev/v2/rate/usd/cny"
    source = "Frankfurter v2"

    def latest(self):
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.get(self.url)
            response.raise_for_status()
            data = json.loads(response.text, parse_float=Decimal)
        if not isinstance(data, dict) or not isinstance(data.get("date"), str):
            raise ValueError("invalid quote response")
        if data.get("base", "").upper() != "USD" or data.get("quote", "").upper() != "CNY":
            raise ValueError("currency pair mismatch")
        rate = Decimal(str(data["rate"]))
        effective = date.fromisoformat(data["date"])
        if not rate.is_finite() or not Decimal("0") < rate < Decimal("1000000") or effective > today():
            raise ValueError("invalid reference quote")
        return rate.quantize(Decimal("0.000000000001")), effective


provider = FrankfurterProvider()


def latest_quote(db, *, refresh=False):
    now = datetime.now(timezone.utc)
    if not refresh:
        cached = db.scalar(select(RateQuote).where(
            RateQuote.fetched_at >= now - timedelta(minutes=30)
        ).order_by(RateQuote.fetched_at.desc()))
        if cached:
            return cached
    try:
        rate, effective = provider.latest()
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise AppError(503, "参考汇率获取失败，可重试或手填人民币金额", "RATE_UNAVAILABLE") from exc
    quote = RateQuote(id=str(uuid.uuid4()), rate=rate, effective_date=effective,
                      fetched_at=now, source=provider.source)
    db.add(quote)
    db.commit()
    return quote
