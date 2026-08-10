from pactum.contract_schema import (
    ColumnRule,
    ParsedContract,
    parse_contract_yaml,
    render_contract_yaml,
)


def test_render_and_parse_round_trip() -> None:
    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="amount",
                data_type="DOUBLE",
                semantic_type="currency",
                min_value=0.0,
                max_value=10000.0,
            ),
            ColumnRule(
                name="email",
                data_type="TEXT",
                semantic_type="pii",
                sensitivity=True,
                regex_pattern=r"[^@]+@[^@]+",
            ),
        ],
        freshness_sla_seconds=3600,
        completeness_sla=0.95,
    )

    yaml_text = render_contract_yaml(contract)
    restored = parse_contract_yaml(yaml_text)

    assert restored == contract


def test_render_contract_yaml_produces_readable_text() -> None:
    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier")],
    )

    yaml_text = render_contract_yaml(contract)

    assert "dataset_id: orders" in yaml_text
    assert "order_id" in yaml_text


def test_get_column_returns_matching_rule() -> None:
    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier"),
            ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency"),
        ],
    )

    rule = contract.get_column("amount")

    assert rule is not None
    assert rule.semantic_type == "currency"


def test_get_column_returns_none_for_unknown_column() -> None:
    contract = ParsedContract(dataset_id="orders", columns=[])

    assert contract.get_column("nonexistent") is None
