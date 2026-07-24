from datetime import datetime, timedelta
from typing import cast

from pactum.monitoring.adherence.violation import Violation


def check_freshness_sla(timestamps: list[object], max_age: timedelta, now: datetime) -> Violation:
    """Check that the newest timestamp is no older than max_age relative to now."""
    parsed = [cast(datetime, ts) for ts in timestamps if ts is not None]
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
