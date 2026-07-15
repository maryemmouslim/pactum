# Pactum tech stack

Complete inventory of the tools that make Pactum work, why each was chosen, and what alternatives were considered.

## 1. Language and development environment

| Tool | Purpose | Why |
|---|---|---|
| **Python 3.11+** | Language | Ecosystem for data + LLMs. 3.11 for performance + `Self` type hint. |
| **uv** | Package manager | 10-100x faster than pip. Handles virtualenvs, lockfiles, tool install. Replaces pip + poetry + pipx. |
| **ruff** | Formatter + linter | Replaces black + isort + flake8 + pylint in one binary. Fast. |
| **mypy** | Type checker | `--strict` on the package. Catches contract-shape bugs before runtime. |
| **pytest** | Testing | Standard. Plugins: pytest-cov, pytest-mock, pytest-postgresql. |
| **pre-commit** | Git hooks | Runs ruff + mypy on staged files. Blocks bad commits before push. |

Alternatives rejected: Poetry (slower than uv, less clean), black + isort (obsoleted by ruff).

## 2. Orchestration

| Tool | Purpose | Why |
|---|---|---|
| **Dagster** | Workflow orchestration | Asset-based paradigm fits our data-quality-first model. Asset checks are built-in. Native materialization tracking. |

Alternative rejected: **Airflow** — task-based paradigm (not asset-based). Feels dated. Weaker data-quality primitives.

## 3. Storage

| Tool | Purpose | Why |
|---|---|---|
| **PostgreSQL 14+** | Contract registry, incidents, explanations, refinements | Versioned rows, append-only, ACID. JSONB for flexible payloads. |
| **DuckDB** | Local dev, profile cache, ad-hoc queries | Zero-config embedded OLAP. Fast columnar scans. Reads Parquet natively. |
| **Docker + docker-compose** | Local Postgres | One command to spin up the dev database. |

Alternative rejected: **SQLite** — no JSONB, weaker for concurrent writes.

## 4. LLM and agents

| Tool | Purpose | Why |
|---|---|---|
| **Anthropic SDK** | LLM client | Claude for the reasoning quality. `claude-opus-4-7` for complex causal reasoning, `claude-haiku-4-5` for cheap classification. |
| **LangGraph** | Agent orchestration | Explicit state graphs. Handles parallel investigation (crucial for the causal agent). Not magic like LangChain. |
| **Pydantic** | Structured LLM outputs | Contracts, incidents, explanations all validated. |

Alternatives rejected: **LangChain** (too much implicit behavior, unstable API), **raw SDK** (too low-level for parallel state machines), **OpenAI** (fine but Claude wins on reasoning quality for this use case).

## 5. Data profiling

| Tool | Purpose | Why |
|---|---|---|
| **whylogs** | Column stats + drift baselines | Purpose-built for this. Compact profiles that persist cheaply. |
| **pandas** | Data manipulation | Standard. Well-known. |
| **polars** | Optional, for large datasets | Optional dependency. Used when pandas would OOM. |

Alternative rejected: **Great Expectations profiler** — heavier, more opinionated, harder to embed.

## 6. Statistical drift tests

| Tool | Purpose | Why |
|---|---|---|
| **scipy.stats** | KS test, Chi-squared | Standard. Fast enough. |
| **Custom PSI implementation** | Population Stability Index | ~50 lines. No good pip package exists. |
| **sentence-transformers** | Embeddings for text drift | Local, free. Model: `all-MiniLM-L6-v2` (fast) or `all-mpnet-base-v2` (better). |

Alternative considered: **Voyage AI embeddings** — higher quality, paid, worth it later when needed.

## 7. Vector store

| Tool | Purpose | Why |
|---|---|---|
| **LanceDB** | Similar-incidents retrieval | Embedded, zero-friction. Stores on disk. Perfect for POC. |

Alternatives considered: **Qdrant** (heavier, better for production serving — v1.5+), **pgvector** (works but LanceDB is cleaner for the read-heavy retrieval pattern).

## 8. Data contract format

| Tool | Purpose | Why |
|---|---|---|
| **ODCS** | Open Data Contract Standard | The emerging standard. Interop matters for a serious OS project. |
| **PyYAML + Pydantic** | Parse and validate contracts | Pydantic for schema validation, PyYAML for I/O. |

Namespace `x-pactum:*` for our own extensions (confidence, refinement history, generation trace).

## 9. Lineage

| Tool | Purpose | Why |
|---|---|---|
| **NetworkX** | Graph algorithms | Standard, pure Python, sufficient for our depth. |
| **OpenLineage adapter** | Interop with existing lineage | For teams that already use OpenLineage. |
| **dbt manifest adapter** | Interop for dbt users | dbt is everywhere. Reading its manifest is straightforward. |

## 10. UI

| Tool | Purpose | Why |
|---|---|---|
| **Streamlit** | Dashboard for v0.1 through v1.0 | Fastest way to ship a functional UI. Good enough for the demo. |
| **Plotly** | Charts inside Streamlit | Interactive drift plots, timelines. |

Later (post-v1.0): **FastAPI + Next.js** if we outgrow Streamlit. Not before.

## 11. CLI

| Tool | Purpose | Why |
|---|---|---|
| **Typer** | CLI framework | Type-hint driven. Autocompletion out of the box. |
| **Rich** | Pretty terminal output | Progress bars, tables, colored logs. Free polish. |

## 12. Source connectors

| Tool | Purpose | Why |
|---|---|---|
| **SQLAlchemy** | Postgres, MySQL, etc. | Universal SQL client. Connection pooling. |
| **DuckDB native** | Parquet, CSV, JSON | Best-in-class for columnar files. |
| **pyarrow** | Columnar interop | Standard for zero-copy data exchange. |
| **httpx** | HTTP APIs | Async-first, replaces `requests`. |

## 13. Containerization

| Tool | Purpose | Why |
|---|---|---|
| **Docker + docker-compose** | Local dev environment | One-command setup for contributors. |
| **GitHub Container Registry** | Image hosting | Free for OSS. |

## 14. CI/CD

| Tool | Purpose | Why |
|---|---|---|
| **GitHub Actions** | CI pipeline | Free for public repos. Well-known. |
| **codecov** | Coverage tracking | Free for OSS. Nice badge for the README. |

Jobs on every PR: lint (ruff), format check (ruff), types (mypy), unit tests (pytest), integration tests (pytest with Postgres service), coverage upload.

## 15. Documentation

| Tool | Purpose | Why |
|---|---|---|
| **MkDocs Material** | Documentation site | Beautiful, easy, standard. GitHub Pages hosting. |
| **Mermaid** | Diagrams in Markdown | Renders in README, ARCHITECTURE, MkDocs. Portable. |

## 16. Community infrastructure

| Tool | Purpose | Why |
|---|---|---|
| **GitHub Issues** | Bugs, features | Standard. Issue templates provided. |
| **GitHub Discussions** | Design questions, ideas | Better than Discord for early stage. |
| **GitHub Sponsors** (post-v1.0) | Optional funding | If the project gets traction. |

## When you learn what

Rough phasing so you do not need to know everything on day one:

| Week | New tools to onboard |
|---|---|
| 1 | uv, Dagster basics, Postgres via Docker, ruff/mypy/pytest workflow. |
| 2 | LangGraph fundamentals, Anthropic SDK, whylogs, ODCS spec. |
| 3-4 | scipy.stats (KS/Chi-squared), PSI implementation, Pydantic validation patterns. |
| 5-6 | Streamlit basics, DuckDB for the profile cache. |
| 7-8 | LanceDB, sentence-transformers, LangGraph parallel state pattern. |
| 9-10 | NetworkX for lineage, dbt manifest structure. |
| 11-12 | MkDocs Material, GitHub Actions polish, Docker image publishing. |

## Cost estimate

For the full 12-week dev cycle:

| Line item | Estimate |
|---|---|
| Anthropic API (contract gen + causal agent) | $50-$100 |
| Postgres, Docker, all OSS | $0 |
| GitHub (public repo) | $0 |
| MkDocs hosting (GitHub Pages) | $0 |
| **Total** | **< $150** |

The API cost breaks down roughly as: contract generator uses ~10k tokens per contract, so 100 contracts across dev ≈ $10. Causal agent uses ~30k tokens per incident due to parallel investigation, so 500 incidents across dev ≈ $75.

## What is deliberately not in the stack

Being explicit about what we are not using and why:

- **No Apache Kafka.** Batch monitoring first. Streaming is a v2+ concern.
- **No Redis.** Postgres LISTEN/NOTIFY is enough for our pub/sub needs at this scale.
- **No Kubernetes.** Docker Compose is enough for a POC and a self-hosted single-tenant tool.
- **No Terraform.** No cloud infra to provision — Pactum runs anywhere Docker runs.
- **No Ray or Dask.** Nothing needs distributed compute at v1.
- **No React or Next.js at v1.** Streamlit is sufficient. Adding a full frontend is a whole other project.
- **No Airflow, Prefect, Kestra.** Dagster picked, decision closed.
- **No custom auth or RBAC.** Single-tenant tool. If you need multi-user, put it behind SSO in your infra.

Every "no" is a hundred hours saved.

## Learning resources per tool

Only the less-obvious ones:

- **Dagster.** Read the "Software-Defined Assets" concept doc. That is the paradigm shift; the rest follows.
- **LangGraph.** The official quickstart, then the "Multi-Agent" and "Human-in-the-loop" tutorials. Skip LangChain material.
- **whylogs.** The "Getting Started" notebook explains profile merging, which is the core primitive.
- **ODCS.** Read the spec once end-to-end. It is ~40 pages, easy.
- **uv.** The `uv sync`, `uv add`, `uv run` triangle covers 95% of usage.
- **LanceDB.** The Python quickstart is enough. Skip the JavaScript client.
