from pactum.monitoring.adherence.referential_integrity import check_referential_integrity


def test_check_referential_integrity_passes_when_all_references_exist() -> None:
    result = check_referential_integrity(
        ["cust_1", "cust_2"], valid_references={"cust_1", "cust_2", "cust_3"}
    )

    assert result.passed is True
    assert result.check_type == "referential_integrity"


def test_check_referential_integrity_fails_for_dangling_reference() -> None:
    result = check_referential_integrity(
        ["cust_1", "cust_999"], valid_references={"cust_1", "cust_2"}
    )

    assert result.passed is False
    assert result.details["offending_values"] == ["cust_999"]


def test_check_referential_integrity_ignores_none_values() -> None:
    result = check_referential_integrity([None, "cust_1"], valid_references={"cust_1"})

    assert result.passed is True
