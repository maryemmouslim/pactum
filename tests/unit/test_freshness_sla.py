from datetime import UTC, date, datetime, timedelta

from pactum.monitoring.adherence.freshness_sla import check_freshness_sla


def test_check_freshness_sla_passes_when_within_max_age() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0)
    timestamps = [now - timedelta(minutes=30), now - timedelta(minutes=45)]

    result = check_freshness_sla(timestamps, max_age=timedelta(hours=1), now=now)

    assert result.passed is True
    assert result.check_type == "freshness_sla"


def test_check_freshness_sla_fails_when_newest_record_too_old() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0)
    timestamps = [now - timedelta(hours=6), now - timedelta(hours=8)]

    result = check_freshness_sla(timestamps, max_age=timedelta(hours=1), now=now)

    assert result.passed is False
    assert result.details["age_seconds"] == timedelta(hours=6).total_seconds()


def test_check_freshness_sla_fails_when_no_data() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0)

    result = check_freshness_sla([], max_age=timedelta(hours=1), now=now)

    assert result.passed is False
    assert result.message == "No data available to check freshness"


def test_check_freshness_sla_handles_plain_date_values() -> None:
    # Reproduces a real crash: a source column stored as SQL DATE (e.g. a
    # CSV "Order Date" column with no time component) comes back from the
    # adapter as a plain date, not a datetime -- `now - newest` used to raise
    # TypeError because you can't subtract a date from a tz-aware datetime.
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    timestamps = [date(2025, 12, 31), date(2025, 12, 30)]

    result = check_freshness_sla(timestamps, max_age=timedelta(days=2), now=now)

    assert result.passed is True


def test_check_freshness_sla_fails_for_stale_plain_date_values() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    timestamps = [date(2025, 1, 1)]

    result = check_freshness_sla(timestamps, max_age=timedelta(days=2), now=now)

    assert result.passed is False
