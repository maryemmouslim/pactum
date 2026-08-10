"""Explicit, one-time setup for a real deployment -- NOT run automatically.

Restores any durably-registered sources from a previous run, then registers
the example dataset and persists it for next time. Run this once before
starting Dagster (`dagster dev`), e.g.:

    uv run python -m pactum.orchestration.bootstrap

This is deliberately a separate, explicitly-invoked script rather than
module-level code in `definitions.py` -- that file gets imported by unit
tests too, and importing must never require a real database connection.
"""

from pathlib import Path

from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import load_persisted_registrations, register_source

EXAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "examples" / "data"


def main() -> None:
    restored = load_persisted_registrations()
    print(f"Restored {restored} previously-persisted source registration(s).")

    register_source(DuckDBAdapter(str(EXAMPLE_DATA_DIR)), persist=True)
    print(f"Registered and persisted the example dataset at {EXAMPLE_DATA_DIR}.")


if __name__ == "__main__":
    main()
