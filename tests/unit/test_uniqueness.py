from pactum.monitoring.adherence.uniqueness import check_uniqueness


def test_check_uniqueness_passes_when_all_values_distinct() -> None:
    result = check_uniqueness(["order_1", "order_2", "order_3"])

    assert result.passed is True
    assert result.check_type == "uniqueness"


def test_check_uniqueness_fails_for_duplicate_value() -> None:
    result = check_uniqueness(["order_1", "order_2", "order_1"])

    assert result.passed is False
    assert result.details["duplicate_values"] == ["order_1"]


def test_check_uniqueness_ignores_none_values() -> None:
    result = check_uniqueness(["order_1", None, None])

    assert result.passed is True
