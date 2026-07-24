from pactum.monitoring.adherence.regex import check_regex

EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"


def test_check_regex_passes_when_all_values_match() -> None:
    result = check_regex(["a@example.com", "b@example.com"], EMAIL_PATTERN)

    assert result.passed is True
    assert result.check_type == "regex"


def test_check_regex_fails_for_non_matching_value() -> None:
    result = check_regex(["a@example.com", "not-an-email"], EMAIL_PATTERN)

    assert result.passed is False
    assert result.details["offending_values"] == ["not-an-email"]


def test_check_regex_requires_full_match_not_partial() -> None:
    # A valid email embedded in a larger string should NOT pass -- the whole
    # value must match, not just a substring somewhere inside it.
    result = check_regex(["prefix text a@example.com"], EMAIL_PATTERN)

    assert result.passed is False


def test_check_regex_ignores_none_values() -> None:
    result = check_regex(["a@example.com", None], EMAIL_PATTERN)

    assert result.passed is True
