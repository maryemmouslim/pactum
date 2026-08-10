from datetime import UTC, date, datetime, time, timedelta

from pactum.monitoring.adherence.violation import Violation


def _as_datetime(value: object) -> datetime:
    """Normalize a column value to a datetime.

    A source column stored as DATE (no time component -- e.g. "Order Date"
    with values like 08/11/2017) comes back from the adapter as a plain
    date, not a datetime. date can't be subtracted from a tz-aware datetime
    directly, so treat it as UTC midnight on that day.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise TypeError(f"Expected a date or datetime value, got {type(value)!r}")


def check_freshness_sla(timestamps: list[object], max_age: timedelta, now: datetime) -> Violation:
    """Check that the newest timestamp is no older than max_age relative to now."""
    parsed = [_as_datetime(ts) for ts in timestamps if ts is not None]
    if not parsed:
        return Violation(
            passed=False,
            check_type="freshness_sla",
            message="No data available to check freshness",
            details={},
        )

    newest = max(parsed)
    age = now - newest
    passed = age <= max_age

    return Violation(
        passed=passed,
        check_type="freshness_sla",
        message=(
            "Data is fresh" if passed else f"Newest record is {age} old, exceeds SLA of {max_age}"
        ),
        details={
            "newest_timestamp": newest.isoformat(),
            "age_seconds": age.total_seconds(),
            "max_age_seconds": max_age.total_seconds(),
        },
    )
