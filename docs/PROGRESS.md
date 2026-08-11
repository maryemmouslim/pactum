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

1. **Data models** (`pactum/models.py`) — `Contract`, `Incident`, `Hypothesis`, `Explanation`, `RefinementProposal`, `LineageEdge`. Verified: `tests/unit/test_models.py` — JSON round-trip and out-of-range/invalid-literal rejection for every model.
2. **Contract Registry** (`pactum/registry/contract_registry.py` + `migrations/versions/f822946a2735_*`) — Postgres-backed, append-only versioning, atomic version/parent allocation via a `pg_advisory_xact_lock`. Verified: `tests/integration/test_contract_registry.py`, including a real 10-thread concurrency test.
3. **Source Adapters** (`pactum/sources/`) — `protocol.py`, `duckdb_adapter.py` (CSV/Parquet), `postgres_adapter.py` (DB tables), `registry.py`, `business_context.py`. Verified: `tests/unit/test_duckdb_adapter.py` (against real `examples/data/` CSVs), `tests/integration/test_postgres_adapter.py` (against a real Postgres table — previously had zero coverage of any kind), `tests/unit/test_source_registry.py`, `tests/unit/test_business_context.py`.
4. **Profiler** (`pactum/profiler.py`) — per-column stats (null %, distinct count, min/max) via whylogs. Verified: `tests/unit/test_profiler.py`.
5. **Lineage graph** (`pactum/lineage/graph.py` + `migrations/versions/565c8114e4f5_*`) — NetworkX `DiGraph` wrapper + Postgres persistence. Verified: `tests/integration/test_lineage_graph.py` — real `save_edge` → `load_graph` round-trip against Postgres (previously only the in-memory `LineageGraph` class was exercised, always empty).

All test/throwaway data cleaned from Postgres (`contracts`, `lineage_edges` tables empty) and scratch files removed before commit.

## Phase 2 — Contract Generator Agent + Monitoring layer (complete)

**Track A — Contract Generator Agent** (`pactum/agents/contract_generator.py`, `pactum/agents/state.py`)
- 7 tools: `inspect_schema`, `profile_column`, `sample_data`, `classify_semantic_type`, `fetch_upstream_contract`, `fetch_business_context`, `write_contract` (`pactum/tools/`)
- LangGraph `StateGraph`: understand → profile → classify → draft → self-critique (max 2 revisions, conditional edge via `route_after_critique`) → write
- Output: ODCS-style YAML draft with `x-pactum:*` extensions, persisted as a new `draft` version via the Contract Registry
- Verified end-to-end with a full graph `.invoke()` smoke test (mocked LLMs, no real API calls)

**Track B — Monitoring layer** (`pactum/monitoring/`)
- Statistical drift (`monitoring/drift/`): PSI, KS (`scipy.stats.ks_2samp`), Chi-squared (`scipy.stats.chi2_contingency`), freshness delta — all registered in `drift/registry.py`
- Contract adherence checks (`monitoring/adherence/`): schema, range, enum, regex, freshness SLA, completeness SLA, referential integrity, uniqueness — each a standalone function returning a shared `Violation` shape
- Incident emission (`monitoring/incident_store.py`): `emit_incident` + `build_signature` for deduplication, backed by an `incidents` table (`migrations/versions/41b5ea924013_*`, applied)
- Dagster integration (`pactum/orchestration/definitions.py`): `source_data` and `contract` assets, plus `capture_snapshots`; adherence *and* drift checks both run generically off the contract's own rules via `monitoring/runner.py`'s `evaluate_contract` (drift detectors ended up wired in once `snapshot_store.py`'s reference-window store existed); hourly `ScheduleDefinition`s for monitoring and daily snapshots, both `DefaultScheduleStatus.RUNNING`
- The example "orders"/"customers" sources are registered at import time in `definitions.py` so the module is self-contained under `dagster dev`

65 unit tests passing (`tests/unit/`), clean `ruff format`/`ruff check`/`mypy --strict`. Added dependencies: `langgraph`, `scipy` (+ `scipy-stubs` dev), `dagster`.

Target per original roadmap: v0.1.0.

## Phase 3 — Causal Explanation Agent (complete)

**Agent** (`pactum/agents/causal_explainer.py`, `pactum/tools/causal_tools.py`) — a deliberately simplified 4-node LangGraph, not the original design's literal 8-node parallel fan-out: `investigate_incident` (calls all 7 tools) → `synthesize_hypotheses` (LLM call via `get_llm("reasoning").with_structured_output`, grounded in real tool findings, not hardcoded string matching) → `persist_explanation` → conditionally `propose_refinement` when the top hypothesis implies the contract itself is wrong. Same investigative behavior as the original design, far less code, easier to test.

All 7 investigation tools are real, not stubs:
- `get_lineage`, `diff_schema`, `compare_distributions`, `query_contract_context` — reuse existing lineage/contract/drift-detector code
- `find_similar_incidents` — real vector search (`pactum/monitoring/incident_index.py`, LanceDB + sentence-transformers `all-MiniLM-L6-v2`). Every investigated incident is embedded and indexed right after its `Explanation` is persisted. Verified it ranks semantically related incidents above unrelated ones, not just exact `(dataset_id, check_type)` matches.
- `fetch_pipeline_logs` — queries a *persistent* `DagsterInstance` (switched from `DagsterInstance.ephemeral()`; `DAGSTER_HOME` now points at `.dagster_home/`) for real, dataset-tagged `monitoring_job` run history. Only runs that went through Dagster are visible — ad-hoc "Run checks" clicks in the UI call `evaluate_contract` directly and never create a Dagster run.
- `fetch_calendar_events` — new `calendar_events` table + `pactum/monitoring/calendar_store.py`, populated manually via `pactum/scripts/add_calendar_event.py` (no external calendar source exists to integrate with).

**Feedback loop**: `RefinementProposal`s are persisted (`pactum/monitoring/refinement_store.py`) and reviewable in the Streamlit UI's "Pending refinement proposals" section — accepting one calls `create_version` + `activate_version` against the Contract Registry; rejecting requires a reason. A new "7. Investigated incidents" section shows every investigated incident's ranked hypotheses and full reasoning trace per dataset.

**Automatic triggering**: `pactum/orchestration/causal_sensor.py`'s `new_incident_sensor` polls `list_incidents_since` on a cursor and fires `causal_investigation_job` per new incident (deduped via `run_key`), `default_status=DefaultSensorStatus.RUNNING` so it starts automatically under `dagster dev` — confirmed live in the daemon log.

`Incident` gained `check_type`/`column_name` fields (previously computed by checks and discarded) since the investigation tools need them. New dependencies: `lancedb`, `sentence-transformers` — the latter pulls in `torch`, which noticeably slows `uv sync`/CI install and first-test-run time; accepted tradeoff for real embedding-based retrieval instead of another exact-match SQL lookup.

249 tests passing (up from 65 at the end of Phase 2), clean `ruff format`/`ruff check`/`mypy --strict`.

Target per original roadmap: v0.2.0 — reached.

## Phase 4 — Polish, eval, release (not started)

- Gold contracts + synthetic incidents in `evals/`, `pactum eval` script, human benchmark
- Final Streamlit UI, README demo, blog post, video
- Repo flips private → public, tag v1.0.0
