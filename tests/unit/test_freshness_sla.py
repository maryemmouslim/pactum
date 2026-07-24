from datetime import datetime, timedelta

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
