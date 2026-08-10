import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_CREDIT_CARD_RE = re.compile(r"^(?:\d[ -]?){13,19}$")

_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "ssn": _SSN_RE,
    "credit_card": _CREDIT_CARD_RE,
}

_NAME_KEYWORDS: dict[str, str] = {
    "email": "email",
    "e_mail": "email",
    "phone": "phone",
    "telephone": "phone",
    "mobile": "phone",
    "ssn": "ssn",
    "social_security": "ssn",
    "credit_card": "credit_card",
    "card_number": "credit_card",
    "cc_number": "credit_card",
}


def detect_pii(column_name: str, samples: list[object]) -> float | None:
    """Locally detect obvious PII before any sample values ever reach an LLM prompt.

    Runs a cheap, local regex/keyword check first. If it's confident a column
    holds PII (by name, by value shape, or both), the caller can classify it
    as "pii" immediately and skip the LLM call entirely -- so real emails,
    phone numbers, SSNs, or card numbers are never sent to an external model
    just to find out they're sensitive. Returns None when the heuristic can't
    tell, so the caller should fall back to LLM classification.
    """
    lowered = column_name.lower()
    name_kind = next((kind for keyword, kind in _NAME_KEYWORDS.items() if keyword in lowered), None)

    values = [str(sample).strip() for sample in samples if sample is not None]
    value_kind = None
    if values:
        for kind, pattern in _VALUE_PATTERNS.items():
            match_ratio = sum(1 for value in values if pattern.match(value)) / len(values)
            if match_ratio >= 0.5:
                value_kind = kind
                break

    if name_kind and value_kind and name_kind == value_kind:
        return 0.98
    if value_kind:
        return 0.9
    if name_kind:
        return 0.85
    return None
