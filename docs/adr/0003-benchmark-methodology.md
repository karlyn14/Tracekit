# ADR 0003: Benchmark Methodology — Train/Test Split, Ground Truth Ahead of Implementation

## Status
Accepted (v1.0.0)

## Context
A rule's precision/coverage numbers are meaningless if the same cases
used to design the rule are also used to "test" it — that's circular,
not evidence. The benchmark also needed a way to plan future rules
without penalizing them for not existing yet.

## Decision
1. Every benchmark case is labeled `train` or `test`. Rules are only
   designed and tuned against `train` cases. All reported metrics
   (precision@1, precision@3, coverage, false positive rate,
   calibration, timing) are computed exclusively on the `test` split.
2. Benchmark cases may specify an `expected_rule_id` for a rule that
   does not exist yet (e.g. `KEY003` before it was implemented). These
   are tracked separately as "pending" — reported as
   awaiting-implementation, never scored as failures against rules
   that do exist.
3. Negative cases (`expected_rule_id: null`) are included deliberately,
   including adversarial ones specifically constructed to look like a
   positive case without being one (e.g. `SERVER_HOST` vs
   `SERVER_PORT` — similar-looking, not a typo of each other).

## Rationale
(1) is the direct fix for dataset leakage — a rule "passing" only
cases it was written to pass proves nothing about generalization.
(2) lets the benchmark function as a specification: KEY003's ground
truth was written and committed before the rule existed, and the rule
was later built specifically to satisfy that pre-defined
specification — a stronger methodological claim than inventing a rule
first and testing it after the fact. (3) exists because a benchmark
built only from positive examples can only ever measure how often the
tool finds something — it can never reveal how often the tool
confidently claims a cause that isn't there. Growing the dataset from
12 to 84 cases with adversarial negatives raised KEY001's measured
false-positive rate from 10% to ~25%; this was the dataset correctly
doing its job, not a regression.

## Consequences
- Every reported metric in this project comes with an explicit
  train/test provenance — no metric here is self-graded.
- New rules must clear a stated acceptance criterion (README.md /
  benchmark/README.md) against held-out data before being accepted,
  not merely "seem to work" on hand-picked examples.
- The benchmark dataset itself is a maintained artifact
  (`benchmark/data/keyerror_cases.jsonl`), versioned alongside the
  code, with saved historical snapshots in `benchmark/results/`.
