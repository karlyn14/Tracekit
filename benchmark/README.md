# TraceKit Benchmark

## How to run

```
python -m benchmark.run
```

## Why this exists

A rule's confidence score is meaningless without evidence it actually
predicts correctness, and "it works on the examples I wrote the rule
against" is not evidence — it's circular. This benchmark exists to
give every rule addition an honest, held-out score.

## Dataset design

`data/keyerror_cases.jsonl` — one JSON object per line. Fields:

| field               | meaning |
|---------------------|---------|
| `source`             | `handwritten`, `stackoverflow`, or `github_issue` — kept distinct on purpose. A benchmark built from one source (e.g. only Stack Overflow) risks overfitting to that source's conventions and can't tell you whether the tool generalizes to real production code. |
| `split`              | `train` or `test`. **Rules are only designed and tuned against `train` cases.** All metrics reported by `run.py` are computed exclusively on `test` — cases the rules were never adjusted against. This is the direct fix for dataset leakage: writing a rule by reading a case and then "testing" on that same case proves nothing. |
| `expected_rule_id`   | The `RULE_ID` that should be the top candidate. **`null` is deliberate and important** — it marks a negative/adversarial case where NO rule should fire. Without negative cases, a benchmark can only ever report how often the tool finds something; it can't reveal how often the tool wrongly claims a cause when there isn't one. |

### Current state

As of this snapshot: **82 cases** (51 train / 31 test), spanning:
- `handwritten`, `stackoverflow`, `github_issue` sources, roughly balanced
- Categories: `typo`, `case_mismatch`, `ambiguous` (deliberate ties —
  should abstain), `similar_but_different` (adversarial — same-length,
  low-edit-distance identifiers that are NOT typos of each other),
  `non_typo_missing`, `missing_config`, `nested_dict_assigned`,
  `nested_dict_unassigned` (documents a known scope limitation —
  see `context.py`), `dict_comprehension`, `pandas_column`,
  `future_key003_nested` (ground truth for an unimplemented rule)

### Known, accepted limitation: edit-distance false positives

Growing the dataset with deliberately adversarial `similar_but_different`
cases (e.g. `SERVER_HOST`/`SERVER_PORT`, `ENABLE_CACHE`/`ENABLE_CACHED`)
raised the measured false positive rate from an earlier 10% (on a
smaller, easier dataset) to **~20%** on this larger, harder one.
This is not a regression — it's the dataset doing its job: exposing a
real, structural limitation of edit-distance-only matching, which
cannot distinguish "typo of an existing key" from "a different key
that happens to look similar." KEY001's confidence is intentionally
capped below KEY002's to reflect this uncertainty; further reducing
false positives here would need semantic/contextual signals beyond
lexical similarity, which is out of scope for KEY001 by design.

Still true at this dataset size: KEY001 and KEY002 both hold
Precision@1 = 100% and Coverage = 100% — the false positives are
*additional* wrong suggestions on true-negative cases, not missed or
incorrect suggestions on true-positive ones.

## Metrics reported

- **Precision@1** — of positive cases, was the top-ranked candidate correct?
- **Precision@3** — was the correct rule anywhere in the top 3 candidates?
- **Coverage** — of positive cases, did the correct rule fire at all (any rank)?
- **False positive rate** — of negative cases (nothing should fire), how
  often did TraceKit produce a candidate anyway? This is the metric
  most likely to be asked about in a viva ("isn't wrong advice worse
  than no advice") and the one a purely-positive dataset can never show you.
- **Confidence calibration** — within each 0.1-wide confidence bucket,
  what fraction of candidates were actually correct? A well-calibrated
  0.8-confidence bucket should be right about 80% of the time. Buckets
  with fewer than 5 samples are flagged as low-N / indicative only —
  don't over-claim calibration quality from a small dataset.
- **Average analysis time** — overhead per exception, to answer
  performance questions with a real number instead of "it should be fast."

## Rule acceptance criterion

A rule is accepted into TraceKit only if it improves held-out
benchmark precision or meaningfully increases coverage, without an
unacceptable increase in the false positive rate. "Unacceptable" is a
judgment call to make explicit per rule addition — document it in the
PR / commit, don't leave it implicit.

## Rule strategy summary

| Rule   | Strategy                     | Precision@1 | Coverage | FP Rate | Avg Confidence |
|--------|-------------------------------|------------:|---------:|--------:|---------------:|
| KEY001 | Fuzzy lexical similarity       | 100%        | 100%     | ~25%    | 0.57           |
| KEY002 | Deterministic normalization     | 100%        | 100%     | 0%      | 0.95           |
| KEY003 | Structural context analysis    | 100%        | 100%     | 0%      | 0.90           |

TraceKit is not "just edit distance" — each rule uses a genuinely
different diagnostic strategy, evaluated under one shared methodology.
The pattern above is itself a finding: both deterministic rules
(KEY002, KEY003) hit 0% false positives with near-instant execution,
while the one heuristic rule (KEY001) carries all of the measured
false-positive risk in this dataset. This is expected, not a flaw —
lexical similarity is inherently probabilistic, while case-folding and
one-level structural lookup are exact checks with no room for
ambiguity once a match is found.

## Benchmark history

| Version | Dataset size | Precision@1 | FP Rate | Coverage | Notes |
|---------|-------------:|------------:|--------:|---------:|-------|
| v0.1    | 12 cases     | 100%        | 33%     | 100%     | KEY001 only; ties broken by picking an arbitrary winner |
| v0.2    | 12 cases     | 100%        | 0%      | 100%     | KEY001 fixed to abstain on ambiguous ties (ADR 0002) |
| v0.5    | 82 cases     | 100%        | 20%     | 100%     | Dataset grown with adversarial negatives; KEY002 added |
| v1.0.0  | 84 cases     | 100%        | 25%     | 100%     | KEY003 added; FP rate increase is the larger, harder dataset surfacing more of KEY001's known lexical-similarity limitation, not a regression (see README "Known limitations") |

Full v1.0.0 output saved as an artifact: `benchmark/results/benchmark_v1.0.0.txt`
and `.json` (regenerated by `python -m benchmark.run`).

Diagnoses `config['host']` failing when `config['database']['host']`
exists — the key is present, just one level down. Deliberately capped
at exactly one level of nesting (not recursive) and restricted to
plain `dict` values only. See `KeyErrorNestedSectionRule`'s docstring
in `rules/keyerror/rules.py` for the full reasoning. Accepted per the
acceptance criterion: 100% precision/coverage on its held-out test
cases, 0% false positives, sub-millisecond execution.
