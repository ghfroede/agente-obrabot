from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def today_iso() -> str:
    return utc_now().date().isoformat()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)
