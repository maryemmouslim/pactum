import re

from pactum.monitoring.adherence.violation import Violation


def check_regex(values: list[object], pattern: str) -> Violation:
    """Check that every non-null value fully matches a regex pattern."""
    compiled = re.compile(pattern)
    offending = [
        value for value in values if value is not None and not compiled.fullmatch(str(value))
    ]

    passed = not offending
    return Violation(
        passed=passed,
        check_type="regex",
        message=(
            "All values match pattern"
            if passed
            else f"{len(offending)} value(s) don't match pattern"
        ),
        details={"offending_values": offending, "pattern": pattern},
    )
