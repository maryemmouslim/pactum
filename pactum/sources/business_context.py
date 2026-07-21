_context: dict[str, str] = {}


def register_business_context(dataset_id: str, description: str) -> None:
    """Attach a human-written description to a dataset_id."""
    _context[dataset_id] = description


def get_business_context(dataset_id: str) -> str | None:
    """Return the registered description for a dataset_id, if any."""
    return _context.get(dataset_id)
