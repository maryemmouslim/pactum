# Gold contract: ecommerce/orders

Source: `examples/data/orders.csv` (this project's own demo dataset -- a public,
independently-sourced dataset like `train.csv` is a natural second gold
contract to add once this harness is proven; this one was chosen first to
keep the first real run cheap).

## Reasoning per column

- **order_id** -- identifier, unique. Every row has a distinct value (`o1`..`o4`)
  and it's the obvious primary key for the dataset.
- **amount** -- currency. Always positive in the sample; a negative order
  amount would be a real anomaly (see the `range_violation` eval scenario),
  so `min_value: 0.0`.
- **status** -- categorical with a small, closed set of observed values
  (`pending`, `shipped`, `cancelled`). Not `free_text`: this looks like an
  enum a real system would validate against, not open-ended input.
- **email** -- PII. Must be flagged `sensitivity: true` regardless of format
  validity, since it's a customer's real (or realistic) contact info. Also
  regex-validated as a sanity check on format.
- **created_at** -- timestamp. DuckDB infers `TIMESTAMP WITH TIME ZONE` for
  this column's ISO-8601-with-offset values; the contract's `data_type`
  should match what the live schema actually reports, not a generic guess.
- **customer_id** -- identifier, and *not* unique (customer `c1` places two
  orders in the sample, `o1` and `o4`) -- a human writer knows this should
  reference `customers.id` in the sibling `customers.csv` dataset. The
  Contract Generator Agent has no mechanism to discover this on its own
  (nothing in its tool list does cross-dataset foreign-key detection), so
  this field is intentionally excluded from the harness's pass/fail score --
  it's a known, expected gap, not a defect to penalize the agent for.

## Dataset-level

`freshness_sla_seconds` and `completeness_sla` are left `null` -- this is a
static demo dataset with no real update cadence, so there's no principled
value a human reviewer would pick here either. Not scored by the harness.
