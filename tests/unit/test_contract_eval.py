from pactum.contract_schema import ColumnRule, ParsedContract
from pactum.eval.contract_runner import compare_contracts


def _rule(name: str, **overrides: object) -> ColumnRule:
    defaults: dict[str, object] = {
        "name": name,
        "data_type": "VARCHAR",
        "semantic_type": "identifier",
        "sensitivity": False,
        "nullable": False,
        "unique": False,
    }
    defaults.update(overrides)
    return ColumnRule(**defaults)  # type: ignore[arg-type]


def test_compare_contracts_matches_every_graded_field_when_identical() -> None:
    gold = ParsedContract(dataset_id="orders", columns=[_rule("order_id", unique=True)])
    generated = ParsedContract(dataset_id="orders", columns=[_rule("order_id", unique=True)])

    result = compare_contracts(gold, generated)

    assert result.missing_columns == []
    assert result.extra_columns == []
    assert result.columns[0].mismatched_fields == []
    assert result.score == (4, 4)  # semantic_type, nullable, unique, sensitivity


def test_compare_contracts_reports_mismatched_fields() -> None:
    gold = ParsedContract(
        dataset_id="orders", columns=[_rule("email", semantic_type="pii", sensitivity=True)]
    )
    generated = ParsedContract(
        dataset_id="orders",
        columns=[_rule("email", semantic_type="categorical", sensitivity=False)],
    )

    result = compare_contracts(gold, generated)

    comparison = result.columns[0]
    assert "semantic_type" in comparison.mismatched_fields
    assert "sensitivity" in comparison.mismatched_fields
    assert result.score == (2, 4)


def test_compare_contracts_reports_missing_and_extra_columns() -> None:
    gold = ParsedContract(dataset_id="orders", columns=[_rule("order_id"), _rule("customer_id")])
    generated = ParsedContract(dataset_id="orders", columns=[_rule("order_id"), _rule("region")])

    result = compare_contracts(gold, generated)

    assert result.missing_columns == ["customer_id"]
    assert result.extra_columns == ["region"]
    # the missing column counts as a full failure across all graded fields
    missing_comparison = next(c for c in result.columns if c.column == "customer_id")
    assert missing_comparison.in_generated is False
    assert len(missing_comparison.mismatched_fields) == 4


def test_compare_contracts_does_not_score_informational_fields() -> None:
    # min_value/max_value/allowed_values/regex_pattern/references_* differ,
    # but none of those are in the graded set -- should still score perfectly.
    gold = ParsedContract(
        dataset_id="orders",
        columns=[_rule("amount", semantic_type="currency", min_value=0.0, max_value=None)],
    )
    generated = ParsedContract(
        dataset_id="orders",
        columns=[_rule("amount", semantic_type="currency", min_value=None, max_value=1000.0)],
    )

    result = compare_contracts(gold, generated)

    assert result.columns[0].mismatched_fields == []
    assert result.score == (4, 4)
