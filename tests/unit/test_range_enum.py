from pactum.monitoring.adherence.range_enum import check_enum, check_range


def test_check_range_passes_when_all_values_within_bounds() -> None:
    result = check_range([10.0, 20.0, 30.0], minimum=0.0, maximum=100.0)

    assert result.passed is True
    assert result.check_type == "range"


def test_check_range_fails_for_value_below_minimum() -> None:
    result = check_range([10.0, -5.0, 30.0], minimum=0.0, maximum=100.0)

    assert result.passed is False
    assert result.details["offending_values"] == [-5.0]


def test_check_range_fails_for_value_above_maximum() -> None:
    result = check_range([10.0, 200.0], minimum=0.0, maximum=100.0)

    assert result.passed is False
    assert result.details["offending_values"] == [200.0]


def test_check_range_ignores_none_values() -> None:
    result = check_range([10.0, None, 30.0], minimum=0.0, maximum=100.0)

    assert result.passed is True


def test_check_enum_passes_when_all_values_allowed() -> None:
    result = check_enum(
        ["pending", "shipped", "pending"], allowed_values={"pending", "shipped", "cancelled"}
    )

    assert result.passed is True
    assert result.check_type == "enum"


def test_check_enum_fails_for_unexpected_value() -> None:
    result = check_enum(["pending", "refunded"], allowed_values={"pending", "shipped", "cancelled"})

    assert result.passed is False
    assert result.details["offending_values"] == ["refunded"]
