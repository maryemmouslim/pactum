from pactum.monitoring.adherence.violation import Violation


def check_referential_integrity(values: list[object], valid_references: set[object]) -> Violation:
    """Check that every non-null value exists in another dataset's actual values.

    `valid_references` is the live set of values from the referenced dataset
    (e.g. all current `customers.id` values), not a fixed rule from the
    contract -- unlike check_enum, which checks against a small fixed set.
    """
    offending = sorted(
        {value for value in values if value is not None and value not in valid_references},
        key=str,
    )
    passed = not offending

    return Violation(
        passed=passed,
        check_type="referential_integrity",
        message=(
            "All references valid"
            if passed
            else f"{len(offending)} value(s) reference non-existent records"
        ),
        details={"offending_values": offending},
    )
