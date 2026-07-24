from collections import Counter

from pactum.monitoring.adherence.violation import Violation


def check_uniqueness(values: list[object]) -> Violation:
    """Check that no non-null value appears more than once."""
    non_null = [value for value in values if value is not None]
    counts = Counter(non_null)
    duplicates = sorted({value for value, count in counts.items() if count > 1}, key=str)

    passed = not duplicates
    return Violation(
        passed=passed,
        check_type="uniqueness",
        message="All values unique" if passed else f"{len(duplicates)} duplicate value(s) found",
        details={"duplicate_values": duplicates},
    )
