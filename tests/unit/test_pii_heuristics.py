from pactum.tools.pii_heuristics import detect_pii


def test_detect_pii_returns_none_for_ordinary_categorical_column() -> None:
    assert detect_pii("status", ["pending", "shipped"]) is None


def test_detect_pii_returns_none_for_empty_generic_column() -> None:
    assert detect_pii("field_7", []) is None


def test_detect_pii_highest_confidence_when_name_and_values_agree() -> None:
    name_and_value_match = detect_pii("email", ["a@example.com", "b@example.com"])
    value_only_match = detect_pii("field_7", ["a@example.com", "b@example.com"])

    assert name_and_value_match is not None
    assert value_only_match is not None
    assert name_and_value_match > value_only_match


def test_detect_pii_catches_phone_numbers_by_value() -> None:
    assert detect_pii("contact", ["555-123-4567", "555-987-6543"]) is not None


def test_detect_pii_catches_ssn_by_value() -> None:
    assert detect_pii("id_field", ["123-45-6789", "987-65-4321"]) is not None


def test_detect_pii_catches_credit_card_by_value() -> None:
    assert detect_pii("number", ["4111111111111111", "4222222222222"]) is not None


def test_detect_pii_catches_pii_by_column_name_alone() -> None:
    assert detect_pii("ssn", []) is not None
    assert detect_pii("social_security_number", []) is not None
    assert detect_pii("customer_phone", []) is not None


def test_detect_pii_requires_majority_of_values_to_match_pattern() -> None:
    # Only 1 of 4 values looks like an email -- not enough to call it PII by shape alone.
    mostly_non_email = detect_pii("field_7", ["a@example.com", "hello", "world", "42"])
    assert mostly_non_email is None
