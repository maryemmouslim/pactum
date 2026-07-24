from pactum.monitoring.adherence.violation import Violation


def check_completeness_sla(values: list[object], min_completeness: float) -> Violation:
    """Check that at least min_completeness fraction of values are non-null."""
    total = len(values)
    if total == 0:
        return Violation(
            passed=False,
            check_type="completeness_sla",
            message="No data available to check completeness",
            details={},
        )

    non_null = sum(1 for value in values if value is not None)
    completeness = non_null / total
    passed = completeness >= min_completeness

    return Violation(
        passed=passed,
        check_type="completeness_sla",
        message=(
            "Completeness meets SLA"
            if passed
            else f"Completeness {completeness:.2%} below required {min_completeness:.2%}"
        ),
        details={
            "completeness": completeness,
            "min_completeness": min_completeness,
            "null_count": total - non_null,
            "total_count": total,
        },
    )
