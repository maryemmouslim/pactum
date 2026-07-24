from pactum.monitoring.adherence.schema import check_schema


def test_check_schema_passes_for_identical_schema() -> None:
    expected = {"order_id": "TEXT", "amount": "DOUBLE"}
    actual = {"order_id": "TEXT", "amount": "DOUBLE"}

    result = check_schema(actual, expected)

    assert result.passed is True
    assert result.check_type == "schema"


def test_check_schema_tolerates_extra_column() -> None:
    expected = {"order_id": "TEXT"}
    actual = {"order_id": "TEXT", "new_column": "TEXT"}

    result = check_schema(actual, expected)

    assert result.passed is True
    assert result.details["extra_columns"] == ["new_column"]


def test_check_schema_fails_for_missing_column() -> None:
    expected = {"order_id": "TEXT", "amount": "DOUBLE"}
    actual = {"order_id": "TEXT"}

    result = check_schema(actual, expected)

    assert result.passed is False
    assert result.details["missing_columns"] == ["amount"]


def test_check_schema_fails_for_type_mismatch() -> None:
    expected = {"amount": "DOUBLE"}
    actual = {"amount": "TEXT"}

    result = check_schema(actual, expected)

    assert result.passed is False
    assert result.details["type_mismatches"] == {"amount": {"expected": "DOUBLE", "actual": "TEXT"}}
