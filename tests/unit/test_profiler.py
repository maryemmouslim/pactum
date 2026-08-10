import pytest

from pactum.profiler import profile_columns


def test_profile_columns_computes_null_percent() -> None:
    rows = [("a", 1.0), ("b", 2.0), ("a", None), ("c", 4.0)]
    result = profile_columns(rows, ["cat", "num"])

    assert result["num"]["null_percent"] == 0.25
    assert result["cat"]["null_percent"] == 0.0


def test_profile_columns_computes_distinct_count() -> None:
    rows = [("a", 1.0), ("b", 2.0), ("a", None), ("c", 4.0)]
    result = profile_columns(rows, ["cat", "num"])

    # whylogs estimates cardinality (HyperLogLog), so it's not always an exact integer.
    assert result["cat"]["distinct_count"] == pytest.approx(3, abs=0.01)
    assert result["num"]["distinct_count"] == pytest.approx(3, abs=0.01)


def test_profile_columns_computes_min_max_for_numeric_column() -> None:
    rows = [("a", 1.0), ("b", 2.0), ("a", None), ("c", 4.0)]
    result = profile_columns(rows, ["cat", "num"])

    assert result["num"]["min"] == 1.0
    assert result["num"]["max"] == 4.0


def test_profile_columns_no_nulls_gives_zero_percent() -> None:
    rows = [(1.0,), (2.0,), (3.0,)]
    result = profile_columns(rows, ["num"])

    assert result["num"]["null_percent"] == 0.0


def test_profile_columns_all_nulls_gives_full_percent() -> None:
    rows = [(None,), (None,)]
    result = profile_columns(rows, ["num"])

    assert result["num"]["null_percent"] == 1.0
