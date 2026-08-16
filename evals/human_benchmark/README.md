# Human benchmark

Compares the Causal Explanation Agent's diagnostic accuracy against a human's,
on the same `evals/injected_incidents/` scenarios `pactum eval` already runs
the agent against.

`pactum eval` (see `pactum/eval/runner.py`) only checks the agent against a
scripted ground truth (`expected_cause` in each scenario's `expected.yaml`) --
that answers "is the agent right," not "how does the agent compare to a
person doing the same investigation." This benchmark answers the second
question.

## Methodology

For each scenario:

1. Run the real `setup.py` / `inject.py` to produce a genuine incident.
2. Gather the exact same evidence the agent's `investigate_incident` node
   gathers (lineage, schema diff, contract rules, distribution comparison,
   pipeline logs, calendar events, similar incidents).
3. A human reads that evidence -- blind, without reading `expected.yaml` or
   the agent's output -- and writes down a hypothesis for the root cause.
   This is recorded once in `human_hypotheses.yaml`; it isn't regenerated on
   each run, because a human judgment call can't be recomputed from code.
4. The real agent (`build_causal_explainer_graph`) is run on the same live
   incident to get its actual top hypothesis.
5. Both the human's and the agent's hypotheses are scored against
   `expected_cause` by the same LLM judge (`pactum/eval/judge.py`), so the
   comparison uses one consistent standard rather than two.

Run it with:

```bash
uv run pactum eval-human-benchmark \
  --scenarios evals/injected_incidents \
  --hypotheses evals/human_benchmark/human_hypotheses.yaml
```

This re-scores the *agent* fresh every run. The human side stays fixed to
`human_hypotheses.yaml` -- it's a recorded baseline, not something to
re-derive.

## Results (2026-08-14)

| Scenario | Human | Agent |
|---|---|---|
| completeness_violation | PASS | PASS |
| deployment_correlated_schema_change | PASS | PASS |
| distribution_shift_amount | PASS | PASS |
| freshness_violation | PASS | PASS |
| range_violation | PASS | PASS |
| referential_integrity_violation | PASS | PASS |
| regex_violation | FAIL | PASS |
| schema_column_missing | PASS | PASS |
| uniqueness_violation | PASS | PASS |

**Human: 8/9. Agent: 9/9.**

The human's one miss (`regex_violation`, invalid value `"not-a-valid-email"`
in an email column): the human hypothesis over-specified the mechanism as a
literal placeholder/sentinel string, rather than the more general, correct
framing the judge wanted ("malformed input entered a field expecting a valid
email format"). The agent's answer stayed at that more calibrated level of
generality and passed.

**Caveat:** for `schema_column_missing`, the human had already seen that
scenario's `expected.yaml` earlier in the session that produced this
benchmark, before the blind-review protocol above was adopted -- so that one
answer wasn't strictly blind. It's a low-ambiguity case (a column is simply
absent), so it's unlikely to have changed the outcome, but it's noted here
for honesty about the process.

The agent matched or beat a human working from identical evidence on every
scenario in this run.
