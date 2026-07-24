from typing import SupportsFloat, cast

from pactum.monitoring.adherence.violation import Violation


def check_range(
    values: list[object], minimum: float | None = None, maximum: float | None = None
) -> Violation:
    """Check that every non-null value falls within [minimum, maximum]."""
    offending = []
    for value in values:
        if value is None:
            continue
        numeric = float(cast(SupportsFloat, value))
        if (minimum is not None and numeric < minimum) or (
            maximum is not None and numeric > maximum
        ):
            offending.append(value)

    passed = not offending
    return Violation(
        passed=passed,
        check_type="range",
        message="All values within range" if passed else f"{len(offending)} value(s) out of range",
        details={"offending_values": offending, "min": minimum, "max": maximum},
    )


def check_enum(values: list[object], allowed_values: set[object]) -> Violation:
    """Check that every non-null value is one of the allowed values."""
    offending = sorted(
        {value for value in values if value is not None and value not in allowed_values},
        key=str,
    )

    passed = not offending
    return Violation(
        passed=passed,
        check_type="enum",
        message=(
            "All values in allowed set" if passed else f"{len(offending)} unexpected value(s) found"
        ),
        details={
            "offending_values": offending,
            "allowed_values": sorted(allowed_values, key=str),
        },
    )
