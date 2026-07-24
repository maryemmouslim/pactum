

# Contributing to Pactum

Thanks for considering a contribution. Pactum is a young project — every contribution shapes what it becomes. This document explains how to get involved.

## What we welcome

Big or small, everything helps:

- **Bug reports** with a reproducer.
- **Feature ideas** — open a discussion first if you are not sure whether it fits.
- **Documentation improvements** — typos, clarifications, translations.
- **New gold-standard contracts** in [`evals/gold_contracts/`](./evals/gold_contracts/). This is one of the highest-leverage contributions.
- **New agent tools.** See [Adding a tool](#adding-a-tool).
- **New drift detection methods.** See [Adding a drift detector](#adding-a-drift-detector).
- **New source adapters.** See [Adding a source](#adding-a-source).
- **Real-world case studies** — anonymized incidents where Pactum helped, or did not.

## Principles

Three things guide reviews:

1. **Small over ambitious.** A tight PR that does one thing well beats a sprawling PR that does five things partially.
2. **Tests over docstrings.** If it is not tested, it is not merged. See [Testing](#testing).
3. **Evidence over opinion.** Design changes should reference evals, benchmarks, or prior discussions. "I think this is better" is not enough by itself.

## Development setup

Pactum uses `uv` for dependency management and virtual environments.

```bash
# Clone
git clone https://github.com/[YOU]/pactum.git
cd pactum

# Setup
uv sync
uv run pre-commit install

# Run tests
uv run pytest

# Run the demo pipeline
uv run pactum demo nyc_taxi
```

Requirements:

- Python 3.11 or newer.
- PostgreSQL 14+ for the contract registry. A local Postgres via Docker works: `docker compose up postgres`.
- An Anthropic API key for the agents: `export ANTHROPIC_API_KEY=...`.

## Project layout

```
pactum/
├── pactum/                Package source
│   ├── agents/            Contract Generator, Causal Explainer
│   ├── tools/             Agent tools (shared and specific)
│   ├── monitoring/        Drift detectors, adherence checks
│   ├── registry/          Postgres contract registry
│   ├── sources/           Source adapters (Postgres, DuckDB, CSV, ...)
│   ├── lineage/           Lineage graph and backends
│   └── ui/                Streamlit dashboard
├── tests/                 Unit and integration tests
├── evals/                 Gold contracts and injected incidents
├── examples/              End-to-end example pipelines
└── docs/                  Long-form docs
```

## Code style

- **Formatter:** `ruff format` (runs on pre-commit).
- **Linter:** `ruff check` with the project's `pyproject.toml` config.
- **Types:** `mypy --strict` on `pactum/`. Tests are exempt from strict typing.
- **Docstrings:** Google style. Public functions and classes must have one.
- **Imports:** `ruff` sorts them. Don't fight it.

## Testing

We use `pytest`. Two test tiers:

- **Unit tests** in `tests/unit/` — fast, no external services.
- **Integration tests** in `tests/integration/` — use a Postgres container and hit the Anthropic API. Require `ANTHROPIC_API_KEY`.

Run unit tests only:

```bash
uv run pytest tests/unit
```

Run everything:

```bash
uv run pytest
```

New features need tests. Bug fixes need a regression test that fails before the fix and passes after.

## Adding a tool

Agent tools live in `pactum/tools/`. A tool is a Python function decorated with `@tool`.

```python
from pactum.tools import tool

@tool
def fetch_recent_git_commits(dataset_id: str, hours: int = 24) -> list[dict]:
    """Return recent git commits touching pipelines that produce this dataset.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        hours: How far back to look. Default 24.

    Returns:
        List of dicts with fields: sha, author, timestamp, message, files.
    """
    ...
```

Requirements for a new tool:

1. Pure function of its inputs. No hidden state.
2. Deterministic given the same inputs and world state.
3. Docstring that could reasonably be used as an LLM tool description.
4. Unit test with mocked I/O.
5. Registration in the appropriate agent's tool list.

Bind the tool to an agent in `pactum/agents/<agent>.py`:

```python
from pactum.tools import fetch_recent_git_commits

CAUSAL_TOOLS = [
    get_lineage,
    fetch_pipeline_logs,
    fetch_recent_git_commits,  # new
    # ...
]
```

## Adding a drift detector

Subclass `DriftDetector` in `pactum/monitoring/drift/`:

```python
from pactum.monitoring.drift import DriftDetector, DriftResult

class MyDetector(DriftDetector):
    supported_types = {"continuous"}

    def detect(self, reference, current) -> DriftResult:
        ...
```

Register it in `pactum/monitoring/drift/registry.py`.

## Adding a source

Sources implement the `SourceAdapter` protocol:

```python
class SourceAdapter(Protocol):
    def list_datasets(self) -> list[str]: ...
    def get_schema(self, dataset: str) -> Schema: ...
    def sample(self, dataset: str, n: int) -> list[dict]: ...
    def query(self, dataset: str, sql: str) -> list[dict]: ...
```

Register the adapter class in `pactum/sources/registry.py`.

## Adding a gold-standard contract

This is one of the most valuable contributions. Every gold contract improves our benchmark.

1. Pick a dataset — public data strongly preferred.
2. Write a contract by hand at `evals/gold_contracts/<domain>/<dataset>.yaml`.
3. Document your reasoning in a companion `<dataset>.md`.
4. Open a PR titled `Gold contract: <domain>/<dataset>`.

## Adding an eval scenario

Injected incidents live in `evals/injected_incidents/`. A scenario is a directory containing:

- `setup.py` — generates the "before" state.
- `inject.py` — applies the drift or violation.
- `expected.yaml` — the ground-truth cause and any expected hypotheses.

Run the benchmark:

```bash
uv run pactum eval --scenarios evals/injected_incidents/
```

## Pull request process

1. **Fork and branch.** Branch names: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`.
2. **Small commits, clear messages.** Conventional commits preferred but not required.
3. **Open a draft PR early** if the change is non-trivial. Early feedback saves rewrites.
4. **Fill in the PR template.** Explain what changes, why, and how you tested.
5. **Green CI.** Tests, format, lint, and types must pass.
6. **One reviewer approval** before merge. Two for changes to the agent architecture or the public API.

## Communication

- **Bugs and small features:** GitHub Issues.
- **Design discussions:** GitHub Discussions.
- **Security issues:** email <security@example.com> — do not open a public issue.

Be kind. Assume the other person is trying to help. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## License

By contributing, you agree that your contributions will be licensed under the same Apache-2.0 license that covers the project.
