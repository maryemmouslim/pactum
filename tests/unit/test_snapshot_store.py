from datetime import UTC, date, datetime

from pactum.monitoring.snapshot_store import _from_json_safe, _to_json_safe


def test_to_json_safe_leaves_plain_values_untouched() -> None:
    assert _to_json_safe(10.0) == 10.0
    assert _to_json_safe("pending") == "pending"
    assert _to_json_safe(None) is None


def test_to_json_safe_tags_datetime_values() -> None:
    value = datetime(2026, 7, 24, 11, 45, 0, tzinfo=UTC)

    tagged = _to_json_safe(value)

    assert tagged == {"__pactum_type__": "datetime", "value": value.isoformat()}


def test_to_json_safe_tags_date_values() -> None:
    value = date(2017, 11, 8)

    tagged = _to_json_safe(value)

    assert tagged == {"__pactum_type__": "date", "value": "2017-11-08"}


def test_from_json_safe_round_trips_datetime() -> None:
    value = datetime(2026, 7, 24, 11, 45, 0, tzinfo=UTC)

    assert _from_json_safe(_to_json_safe(value)) == value


def test_from_json_safe_round_trips_date() -> None:
    value = date(2017, 11, 8)

    assert _from_json_safe(_to_json_safe(value)) == value


def test_from_json_safe_leaves_plain_values_untouched() -> None:
    assert _from_json_safe(10.0) == 10.0
    assert _from_json_safe("pending") == "pending"
