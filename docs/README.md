<div align="center">

# Pactum

**Living data contracts that explain themselves.**

*Auto-inferred contracts. Semantic drift detection. Causal incident explanation. One system, one loop, one source of truth.*

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)]()
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

![Pactum demo](docs/assets/pactum-demo.gif)

</div>

---

## What it does in 30 seconds

Pactum reads your data, writes a contract for it, watches it for you, and — when something breaks — tells you *why*, not just *what*.

- **Contract Generator Agent** infers a full ODCS-compliant contract from any source (schema + samples + docs). No more hand-written YAML that goes stale the day it's written.
- **Monitoring layer** watches for both statistical drift *and* contract violations, in the same place, at the same time.
- **Causal Explanation Agent** doesn't stop at "your table drifted." It investigates the lineage, the logs, the calendar, and past incidents — then hands you a ranked list of hypotheses with confidence scores and a concrete proposed action.
- **Feedback loop** turns every incident into a contract refinement. The system gets smarter every time it fires.

## Why Pactum exists

Existing data quality tools tell you *what* broke. Pactum tells you *why*.

The state of data observability in 2026 is embarrassing. You wire up Monte Carlo or Bigeye. You get a Slack alert at 2 a.m.: "distribution shift detected in `orders.total_amount`." Congratulations. Now you spend the next three hours pulling up dbt runs, checking upstream Kafka topics, asking product if anything shipped this week, and diffing yesterday's samples against today's. The tool gave you the symptom. The diagnosis is still your problem.

Data contracts were supposed to fix this. Instead they became one more chore. Nobody writes them, nobody maintains them, and when they do exist, they're static YAML files that go stale the moment they're committed.

Pactum treats these as one problem, not two. Contracts are the semantic layer that drift detection has been missing. Causal explanation is the loop that keeps contracts alive. A contract that never gets refined is dead. Drift detection with no semantic grounding is noise. Combine them, and you get something new: a data observability system that *understands* what it's watching.

## Show, don't tell

Here's what Pactum produces when your `orders.total_amount` column starts drifting:

```
Incident #INC-2426-0341 · orders.total_amount · Distribution drift · PSI 0.28

## Ranked hypotheses

1. UPSTREAM SCHEMA CHANGE (confidence: 0.82)
   The upstream table `raw_stripe_charges` added a new `currency` column
   on 2026-03-10 14:22 UTC. Previously, all amounts were coerced to USD
   during ingestion. Since the change, the coercion step has been skipped —
   `total_amount` now contains mixed currencies.
   ↳ Suggested action: fix the coercion step in dbt_stripe_charges.sql:47
   ↳ Related incident: INC-2025-0912 (same root cause pattern)

2. SEASONAL PATTERN (confidence: 0.11)
   Historical data shows a similar shift in mid-March 2024 and 2025.
   Could be an early-quarter promotion cycle.
   ↳ Suggested action: cross-check with the growth team.

3. SAMPLING BIAS (confidence: 0.05)
   The current window has 40% fewer records than the reference.
   May be ingesting a non-representative slice.
   ↳ Suggested action: extend observation window to 14 days.

## Proposed contract refinement

The current contract asserts total_amount is in [1, 10000] USD. If mixed
currencies are intentional, the range constraint should be scoped by
currency. Draft change:

+ currency_scoped_ranges:
+   USD: [1, 10000]
+   EUR: [1, 9200]
+   GBP: [1, 7900]
```

No dashboard tab-diving. No Slack thread with five people asking "did anyone deploy something?" Just a report you can actually act on.

## Quick start

```bash
pip install pactum-observe
```

```python
from pactum import Contract, Monitor, CausalExplainer

# 1. Auto-generate a contract from a source
contract = Contract.infer("postgres://prod/orders")
contract.review()  # opens a Streamlit UI to accept/edit

# 2. Start monitoring
monitor = Monitor(contract)
monitor.watch(schedule="hourly")

# 3. When an incident fires, get an explanation
explainer = CausalExplainer()
report = explainer.investigate(monitor.latest_incident())
print(report.render_markdown())
```

Full walkthrough on the NYC Taxi dataset: [`examples/nyc_taxi`](./examples/nyc_taxi).
Colab notebook (no install): [Open in Colab](#).

## How it works

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full picture. The short version:

1. **Foundation layer** — Dagster orchestration, DuckDB for local dev, PostgreSQL contract registry, LangGraph for agent orchestration.
2. **Contract Generator Agent** — 7 tools including schema inspection, semantic type classification, and self-critique.
3. **Monitoring layer** — statistical drift (KS, PSI, Chi-squared) plus contract adherence (schema, freshness, values).
4. **Causal Explanation Agent** — investigates in parallel across lineage, logs, schema diffs, calendar events, and past incidents. Ranks hypotheses by confidence.
5. **Feedback loop** — every incident becomes a proposed contract refinement.

## How Pactum differs

| | Great Expectations / Soda | Monte Carlo / Bigeye | Open-source data contracts | Pactum |
|---|---|---|---|---|
| Auto-generated contracts | No | No | No | Yes |
| Statistical drift detection | Basic | Yes | No | Yes |
| Causal explanation | No | No | No | Yes |
| Feedback loop to contracts | No | No | No | Yes |
| Local dev, self-hosted | Yes | No | Yes | Yes |
| MCP-ready | No | No | No | Yes |

## Roadmap

- **v0.1** — Contract Generator + basic monitoring. NYC Taxi example. *Target: week 6.*
- **v0.2** — Causal Explanation Agent + feedback loop. Bank Al-Maghrib and synthetic examples. *Target: week 10.*
- **v1.0** — Full documentation, Colab notebooks, 3-minute demo video, MCP server exposition. *Target: week 12.*
- **Post-1.0** — Streaming source support, distributed monitoring, catalog integrations (DataHub, OpenMetadata).

## Contributing

Pactum is built in the open from day one. Issues, PRs, and discussions are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md).

Areas where help matters most right now:

- More gold-standard reference contracts across domains (finance, e-commerce, healthcare, public sector).
- Additional causal investigation tools (Airflow, GitHub Actions, Slack integrations).
- Translations of the docs.

## Citation

If Pactum helps your research or product, please cite:

```bibtex
@software{pactum2026,
  author = {[YOUR NAME]},
  title  = {Pactum: Living data contracts with causal incident explanation},
  year   = {2026},
  url    = {https://github.com/[YOU]/pactum}
}
```

## License

Apache-2.0. Do what you want, keep the copyright notice.

---

Built with LangGraph, Dagster, DuckDB, and Claude.
