from pactum.monitoring.adherence.violation import Violation


def check_schema(actual_schema: dict[str, str], expected_schema: dict[str, str]) -> Violation:
    """Check that live column names and types match what the contract expects.

    Extra columns (additive changes) are tolerated; missing columns or
    type mismatches are not.
    """
    missing = sorted(set(expected_schema) - set(actual_schema))
    extra = sorted(set(actual_schema) - set(expected_schema))
    type_mismatches = {
        column: {"expected": expected_schema[column], "actual": actual_schema[column]}
        for column in expected_schema
        if column in actual_schema and actual_schema[column] != expected_schema[column]
    }

    passed = not missing and not type_mismatches
    return Violation(
        passed=passed,
        check_type="schema",
        message="Schema matches contract" if passed else "Schema mismatch detected",
        details={
            "missing_columns": missing,
            "extra_columns": extra,
            "type_mismatches": type_mismatches,
        },
    )
