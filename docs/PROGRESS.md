# Pactum — Progress

Tracks what's actually built vs. what's still planned. Update this after each phase closes.

## Phase 0 — Setup (complete)

- Git repo initialized, linked to `github.com/maryemmouslim/pactum`
- `.gitignore`, `LICENSE` (Apache-2.0), `.pre-commit-config.yaml`, `.env` / `.env.example`
- Folder structure: `pactum/{agents,tools,monitoring,registry,sources,lineage,ui}/`, `tests/`, `evals/`, `examples/`, `docs/`
- `pyproject.toml`, `uv sync`, `docker-compose.yml` (Postgres 14 running locally)
- GitHub Actions CI (ruff format, ruff check, mypy --strict, pytest)
- `pactum/settings.py` — reads `.env`, fails loudly if `GROQ_API_KEY` is missing
- `pactum/llm.py` — `get_llm(role)`, currently Groq-only (`llama-3.1-8b-instant` / `llama-3.3-70b-versatile`)

**Environment notes:**
- LLM provider: **Groq** (Gemini was tried first but hit a free-tier quota=0 account issue — parked, not debugged further)
- Project pinned to **Python 3.11** (not 3.13) — required for `whylogs-sketching` to install from a prebuilt Windows wheel instead of needing a C++ compiler
- `numpy<2` and `pandas<3` pinned — `whylogs` 1.6.4 uses a NumPy API removed in NumPy 2.0

## Phase 1 — Foundation layer (complete)

1. **Data models** (`pactum/models.py`) — `Contract`, `Incident`, `Hypothesis`, `Explanation`, `RefinementProposal`, `LineageEdge`. Verified: JSON round-trip, validation rejects out-of-range values.
2. **Contract Registry** (`pactum/registry/contract_registry.py` + `migrations/versions/f822946a2735_*`) — Postgres-backed, append-only versioning. Functions: `create_version`, `get_active`, `get_version`, `list_history`. Verified end-to-end with real inserts/queries.
3. **Source Adapters** (`pactum/sources/`) — `protocol.py` (shared interface: `list_datasets`, `get_schema`, `sample`), `duckdb_adapter.py` (CSV/Parquet files), `postgres_adapter.py` (DB tables). Verified both return the same shape of data.
4. **Profiler** (`pactum/profiler.py`) — per-column stats (null %, distinct count, min/max) via whylogs. Verified against real CSV data.
5. **Lineage graph** (`pactum/lineage/graph.py` + `migrations/versions/565c8114e4f5_*`) — NetworkX `DiGraph` wrapper + Postgres persistence (`lineage_edges` table). Verified: save → reload → `upstream_of`/`downstream_of` queries correct.

All test/throwaway data cleaned from Postgres (`contracts`, `lineage_edges` tables empty) and scratch files removed before commit.

## Phase 2 — Contract Generator Agent + Monitoring layer (not started)

**Track A — Contract Generator Agent**
- 7 tools: `inspect_schema`, `profile_column`, `sample_data`, `classify_semantic_type`, `fetch_upstream_contract`, `fetch_business_context`, `write_contract`
- LangGraph state machine: understand → profile → classify → draft → self-critique (max 2 revisions) → write
- Output: ODCS-compliant YAML with `x-pactum:*` extensions

**Track B — Monitoring layer**
- Statistical drift: PSI + KS (numeric), Chi-squared (categorical), freshness delta (timestamp)
- Contract adherence checks: schema, range/enum, regex, freshness SLA, completeness SLA, referential integrity, uniqueness
- Incident emission with stable signature (for deduplication)
- Dagster integration: sources = assets, contracts = derived assets, adherence = asset_checks, incidents = materializations

Target per original roadmap: v0.1.0.

## Phase 3 — Causal Explanation Agent (not started)

- 7 investigation tools: `get_lineage`, `fetch_pipeline_logs`, `diff_schema`, `compare_distributions`, `fetch_calendar_events`, `find_similar_incidents` (LanceDB + sentence-transformers), `query_contract_context`
- LangGraph state machine: classify → parallel investigation (6 branches) → merge → synthesize hypotheses → rank by confidence → propose action → propose refinement
- `RefinementQueue` + Streamlit review UI
- Dagster sensor triggering investigation on new incidents

Target: v0.2.0.

## Phase 4 — Polish, eval, release (not started)

- Gold contracts + synthetic incidents in `evals/`, `pactum eval` script, human benchmark
- Final Streamlit UI, README demo, blog post, video
- Repo flips private → public, tag v1.0.0
