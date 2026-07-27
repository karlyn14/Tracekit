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

`data/*_cases.jsonl` — one file per exception family
(`keyerror_cases.jsonl`, `attributeerror_cases.jsonl`, more as new
families are added), loaded together by `load_all_cases()`. Adding a
new family's dataset file requires no changes to `run.py` — this is
what makes multi-family evaluation additive rather than a rewrite each
time. Case IDs must be unique across ALL files combined (enforced at
load time), and each rule family's ID prefix (`KEY`, `ATTR`, ...)
keeps cases traceable to the exception type and strategy they validate.

Fields, one JSON object per line:

| field               | meaning |
|---------------------|---------|
| `source`             | `handwritten`, `stackoverflow`, or `github_issue` — kept distinct on purpose. A benchmark built from one source (e.g. only Stack Overflow) risks overfitting to that source's conventions and can't tell you whether the tool generalizes to real production code. |
| `split`              | `train` or `test`. **Rules are only designed and tuned against `train` cases.** All metrics reported by `run.py` are computed exclusively on `test` — cases the rules were never adjusted against. This is the direct fix for dataset leakage: writing a rule by reading a case and then "testing" on that same case proves nothing. |
| `expected_rule_id`   | The `RULE_ID` that should be the top candidate. **`null` is deliberate and important** — it marks a negative/adversarial case where NO rule should fire. Without negative cases, a benchmark can only ever report how often the tool finds something; it can't reveal how often the tool wrongly claims a cause when there isn't one. Can also name a rule that doesn't exist yet — see "Rule support" below. |

### Current state

**KeyError** (`keyerror_cases.jsonl`): 84 cases (52 train / 32 test).
**AttributeError** (`attributeerror_cases.jsonl`): 12 cases (7 train /
5 test).

KeyError categories: `typo`, `case_mismatch`, `ambiguous` (deliberate
ties — should abstain), `similar_but_different` (adversarial —
same-length, low-edit-distance identifiers that are NOT typos of each
other), `non_typo_missing`, `missing_config`, `nested_dict_assigned`,
`nested_dict_unassigned` (documents a known scope limitation — see
`context.py`), `dict_comprehension`, `pandas_column`.

AttributeError categories: `none_attribute`, `none_via_function_return`,
`genuine_missing_attribute` (true negative for ATTR001),
`attr002_container_api_confusion` (ground truth for ATTR002, not yet
implemented), `attr001_regression_check_literal_none` (cross-checks
that ATTR002's container-confusion detection doesn't steal cases that
belong to ATTR001), `genuine_missing_attribute_not_container` (true
negative for ATTR002), `future_attr003_typo` (ground truth for
ATTR003, not yet implemented).

### ATTR002 scope boundary (written before implementation, on purpose)

ATTR002 detects a narrow, specific pattern: **calling a method that
doesn't exist on a value because two built-in container APIs were
confused** (e.g. `.append()` — a list method — called on a `str`,
`dict`, or `set`). This boundary is deliberate, not an oversight, and
is fixed here *before* any implementation exists so scope creep has
something concrete to be checked against later:

```text
Supported:
  ✓ str.append()   (list method called on a str)
  ✓ list.add()      (set method called on a list)
  ✓ dict.append()   (list method called on a dict)
  ✓ set.append()    (list method called on a set)

Not supported (out of scope for ATTR002, on purpose):
  ✗ arbitrary user-defined classes        (not a built-in container)
  ✗ third-party library APIs              (pandas, requests, etc.)
  ✗ attribute-name typos                  (ATTR003's job, not ATTR002's)
  ✗ NoneType access                       (ATTR001's job, not ATTR002's)
```

If ATTR002 starts firing on any of the "not supported" cases, that's a
false positive against this stated boundary, not a missing feature to
add — the fix is narrowing the rule back to its scope, not widening
it into a general "explain every AttributeError" rule.

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

| Rule    | Strategy                     | Precision@1 | Coverage | FP Rate | Avg Confidence |
|---------|-------------------------------|------------:|---------:|--------:|---------------:|
| KEY001  | Fuzzy lexical similarity       | 100%        | 100%     | ~25%    | 0.57           |
| KEY002  | Deterministic normalization     | 100%        | 100%     | 0%      | 0.95           |
| KEY003  | Structural context analysis    | 100%        | 100%     | 0%      | 0.90           |
| ATTR001 | Runtime object inspection      | 100%        | 100%     | 0%      | 0.98           |

TraceKit is not "just edit distance" — each rule uses a genuinely
different diagnostic strategy, evaluated under one shared methodology.
The pattern holds across exception families, not just within
KeyError: the three deterministic rules (KEY002, KEY003, ATTR001) all
hit 0% false positives with near-instant execution, while the one
heuristic rule (KEY001) carries all of the measured false-positive
risk in this dataset. This is expected, not a flaw — lexical
similarity is inherently probabilistic, while case-folding,
one-level structural lookup, and reading CPython's own structured
exception data are exact checks with no room for ambiguity once a
match is found. ATTR001 reproducing this pattern in a second, entirely
different exception family is itself evidence the finding is about
the diagnostic strategy, not an artifact specific to KeyError.

## Benchmark history

| Version | Dataset size | Precision@1 | FP Rate | Coverage | Notes |
|---------|-------------:|------------:|--------:|---------:|-------|
| v0.1    | 12 cases     | 100%        | 33%     | 100%     | KEY001 only; ties broken by picking an arbitrary winner |
| v0.2    | 12 cases     | 100%        | 0%      | 100%     | KEY001 fixed to abstain on ambiguous ties (ADR 0002) |
| v0.5    | 82 cases     | 100%        | 20%     | 100%     | Dataset grown with adversarial negatives; KEY002 added |
| v1.0.0  | 84 cases     | 100%        | 25%     | 100%     | KEY003 added; FP rate increase is the larger, harder dataset surfacing more of KEY001's known lexical-similarity limitation, not a regression (see README "Known limitations") |
| ATTR001 | 90 cases     | 100%        | 25% (pooled; ATTR001 itself: 0%) | 100% | First rule for a second exception family; zero core pipeline changes needed (see README "Lessons learned"). Pooled FP rate unchanged from v1.0.0 — see per-rule breakdown in `benchmark/results/` for ATTR001's individual 0% |

Full v1.0.0 output saved as an artifact: `benchmark/results/benchmark_v1.0.0.txt`
and `.json` (regenerated by `python -m benchmark.run`).

## KEY003 — Missing intermediate dictionary level

Diagnoses `config['host']` failing when `config['database']['host']`
exists — the key is present, just one level down. Deliberately capped
at exactly one level of nesting (not recursive) and restricted to
plain `dict` values only. See `KeyErrorNestedSectionRule`'s docstring
in `rules/keyerror/rules.py` for the full reasoning. Accepted per the
acceptance criterion: 100% precision/coverage on its held-out test
cases, 0% false positives, sub-millisecond execution.

## ATTR001 — NoneType Attribute Access

Diagnoses `x.name` (or any attribute/method access) failing because
`x` is `None`. Deterministic — reads `AttributeError.obj`/`.name`
directly (structured data CPython attaches since Python 3.10) rather
than parsing the exception's message string. See
`AttributeErrorNoneTypeRule`'s docstring in `rules/attributeerror/rules.py`
for the full reasoning. Accepted per the acceptance criterion: 100%
precision/coverage on its held-out test case, 0% false positives,
sub-millisecond execution, zero regression on any KeyError rule.
