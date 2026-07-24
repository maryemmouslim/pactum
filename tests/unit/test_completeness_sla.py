from pactum.monitoring.adherence.completeness_sla import check_completeness_sla


def test_check_completeness_sla_passes_when_above_threshold() -> None:
    values = ["a"] * 99 + [None]

    result = check_completeness_sla(values, min_completeness=0.95)

    assert result.passed is True
    assert result.check_type == "completeness_sla"


def test_check_completeness_sla_fails_when_below_threshold() -> None:
    values = ["a"] * 80 + [None] * 20

    result = check_completeness_sla(values, min_completeness=0.95)

    assert result.passed is False
    assert result.details["completeness"] == 0.8
    assert result.details["null_count"] == 20


def test_check_completeness_sla_fails_when_no_data() -> None:
    result = check_completeness_sla([], min_completeness=0.95)

    assert result.passed is False
    assert result.message == "No data available to check completeness"
