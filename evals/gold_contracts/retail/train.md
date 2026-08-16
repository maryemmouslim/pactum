# Gold contract: retail/train

Source: `examples/data/train.csv` -- the public "Superstore" retail sales
dataset (18 columns, 9,800 rows, 2015-2018). Genuinely public and independently
sourced, unlike `orders.csv` (this project's own demo data) -- this is the
second gold contract, added to check whether the `unique`/`nullable` fix
verified on `orders` generalizes, or was tuned to that one dataset's shape.

## Why this dataset is a good regression test

`orders.csv` only had one plausible unique-looking identifier (`order_id`),
which really was unique. `train.csv` has **four** columns whose names all
suggest "identifier" -- `Row ID`, `Order ID`, `Customer ID`, `Product ID` --
but only one of them, `Row ID`, is actually unique across the data. The other
three repeat by design (an order has multiple line items, a customer places
multiple orders, a product appears in multiple orders). This is exactly the
failure pattern the earlier bug produced: guessing `unique=true` from an
"_id"-shaped name instead of checking real cardinality. A correct run should
get `Row ID` right and *not* be fooled by the other three.

## Reasoning per column

- **Row ID** -- identifier, unique. Distinct across all 9,800 rows; the
  dataset's true row-level primary key.
- **Order ID**, **Customer ID**, **Product ID** -- identifiers, but *not*
  unique (4,922 / 793 / 1,861 distinct values respectively, each far below
  the row count). See above.
- **Order Date**, **Ship Date** -- timestamp. Plain calendar dates, no time
  component; DuckDB infers `DATE` rather than a full timestamp type.
- **Ship Mode**, **Segment**, **Region**, **Category** -- categorical, small
  closed sets (4, 3, 4, and 3 observed values respectively) that read like
  enums a real system would validate against.
- **Country** -- categorical even though every row is `"United States"` in
  this extract -- it is still a bounded-domain field, not free text.
- **City**, **State**, **Sub-Category** -- categorical. Higher cardinality
  (529 / 49 / 17 distinct values) than the columns above, but still bounded,
  real-world dimensions used for grouping/filtering, not open-ended text.
- **Customer Name** -- PII. A real person's full name, so `sensitivity: true`
  regardless of the fact it isn't a structured value like an email or phone
  number. Not caught by the local regex/keyword heuristic in
  `pii_heuristics.py` (which only matches email/phone/ssn/credit-card
  patterns) -- classifying this correctly depends on the LLM step, not the
  cheap pre-filter. A genuine, harder test than `orders.csv`'s `email` column.
- **Product Name** -- free_text. Descriptive product titles, effectively
  unbounded (1,849 distinct values out of 9,800 rows) and not something a
  system would validate against a fixed list.
- **Postal Code** -- identifier (a location code, not a quantity). Numeric
  but not `currency` and not meaningfully bounded by `min`/`max`.
  **`nullable: true`** in this gold contract -- there are 11 real nulls in the
  full file. This is a known, honest miss the harness is expected to surface:
  `profile_column` only samples the first 1,000 rows (`LIMIT 1000`, not a
  random sample), and none of the 11 nulls happen to fall in that range, so
  the agent will very likely see 0% nulls and mark this `nullable: false`.
  That's a real limitation of the profiler's sampling strategy, not a defect
  in this gold contract -- documenting it here rather than silently grading
  around it.
- **Sales** -- currency. Always positive in the data (min `0.444`), so
  `min_value: 0.0` as a sane floor.

## Not scored (informational only)

`references_dataset`/`references_column` are left `null` throughout -- there
is no sibling `customers`/`products` dataset registered for this domain in
`examples/data/`, and cross-dataset foreign-key discovery is out of scope for
the generator's current tools regardless (see `orders.md`). `allowed_values`
lists are included for the clearly-enum columns as documentation but are not
part of the graded field set.

## Dataset-level

`freshness_sla_seconds` and `completeness_sla` are left `null` -- this is a
static historical extract with no real update cadence.
