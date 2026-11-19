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
| `split`              | `train` or `test`. **Rules are only designed and tuned against `train` cases.** All metrics reported by `run.py` are computed exclusively on `test` — cases the rules were never adjusted against. This is the direct fix for dataset leakage: writing a rule by reading a case and then "testing" on that same case proves nothing. (No model is being trained here — the train split is used to develop and refine deterministic diagnostic rules by hand; the test split stays untouched until evaluation, for the same reason a held-out set matters in ML: to reduce the risk of overfitting rule behavior to the specific cases used to build it.) |
| `expected_rule_id`   | The `RULE_ID` that should be the top candidate. **`null` is deliberate and important** — it marks a negative/adversarial case where NO rule should fire. Without negative cases, a benchmark can only ever report how often the tool finds something; it can't reveal how often the tool wrongly claims a cause when there isn't one. Can also name a rule that doesn't exist yet — see "Rule support" below. |

### Current state

**KeyError** (`keyerror_cases.jsonl`): 90 cases (54 train / 36 test).
**AttributeError** (`attributeerror_cases.jsonl`): 16 cases (9 train /
7 test).
**Total: 106 cases — 63 train / 43 held-out test.** The held-out test
split has 24 positive cases (a rule should fire) and 19 negative cases
(no rule should fire).

(Historical sizes: the KeyError file held 84 cases (52 train / 32 test)
through v2.0.0; the 6 cases added since come from GH-20 (3), GH-01 (2)
and GH-02 (1) — see "Benchmark history".)

KeyError categories: `typo`, `case_mismatch`, `ambiguous` (deliberate
ties — should abstain), `similar_but_different` (adversarial —
same-length, low-edit-distance identifiers that are NOT typos of each
other), `non_typo_missing`, `missing_config`, `nested_dict_assigned`,
`nested_dict_unassigned` (documents a known scope limitation — see
`context.py`), `dict_comprehension`, `pandas_column`, plus the
categories added after v2.0.0: `sentence_style_keyerror_message` and
`bare_key_with_space_regression` (GH-20), `gh01_reversed_direction_typo`
(GH-01) and `gh02_short_word_coincidental_similarity` (GH-02).

AttributeError categories: `none_attribute`, `none_via_function_return`,
`genuine_missing_attribute` (true negative for ATTR001),
`attr002_container_api_confusion` (ground truth for ATTR002),
`attr001_regression_check_literal_none` (cross-checks that ATTR002's
container-confusion detection doesn't steal cases that belong to
ATTR001), `genuine_missing_attribute_not_container` (true negative for
ATTR002), `attr003_typo_distance1`/`future_attr003_typo` (ground truth
for ATTR003 — now implemented; the `future_` prefix is a historical
label), `attr003_ambiguous` (tie between
two equally-close real attributes — true negative, same abstention
principle as KEY001), `attr003_no_close_candidate` (genuinely no
attribute within edit distance 2 — true negative).

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

*Historical context (v0.5 – v1.0.0):* growing the dataset with
deliberately adversarial `similar_but_different` cases (e.g.
`SERVER_HOST`/`SERVER_PORT`, `ENABLE_CACHE`/`ENABLE_CACHED`) raised the
measured false positive rate from an earlier 10% (on a smaller, easier
dataset) to **~20%** on the larger, harder one (25% at v1.0.0; see
"Benchmark history").
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

*Current status:* after the GH-02 fix (KEY001 now uses restricted
Damerau-Levenshtein distance with a maximum edit distance of 1), the
overall false positive rate on the 43-case held-out split is
**2/19 negative cases = 10.5% (≈11%)**. The two remaining false
positives are `KEY001-043` (`FEATURE_X`/`FEATURE_Y`) and `KEY001-074`
(`ENABLE_CACHE`/`ENABLE_CACHED`) — near-identical identifiers that are
not adjacent-character swaps, so the transposition-aware distance does
not separate them from a typo. They are the accepted limitation
described above; the denominator of the rate is the negative test
cases. This rate is not comparable with the 25% / ~20% figures quoted
above, which were measured on earlier, smaller versions of the dataset.

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

### Overall rate versus per-rule counts

Two kinds of false-positive figure appear in the output and they have
different denominators:

- **Overall false positive rate** — negative test cases where *any*
  candidate was produced, divided by all negative test cases. Currently
  2/19 = 10.5%.
- **Per-rule `Fired` / `Correct` / `False positives`** — counts over
  candidates at *any* rank, not only the top-ranked one. `Fired` is every
  case on which the rule produced a candidate; `Correct` is a firing on a
  positive case whose expected rule is this rule; `False positives` is a
  firing on a negative case. A firing on a positive case whose expected
  rule is a different one is counted in `Fired` only. These are counts,
  not rates, and there is no per-rule rate in the output. Dividing a
  rule's false positives by its own `Fired` count gives a different
  number than the overall rate and should not be presented as the
  benchmark's false positive rate.

## Rule acceptance criterion

A rule is accepted into TraceKit only if it improves held-out
benchmark precision or meaningfully increases coverage, without an
unacceptable increase in the false positive rate. "Unacceptable" is a
judgment call to make explicit per rule addition — document it in the
PR / commit, don't leave it implicit.

## Current results

Held-out test split (43 cases: 24 positive, 19 negative), regenerated
with `python -m benchmark.run`. The live output goes to
`benchmark/results/benchmark_latest.{txt,json}`, which is gitignored and
regenerable; the committed `benchmark_v1.0.0.*` and `benchmark_v2.0.0.*`
files are frozen historical snapshots and are not updated by a run.

| Metric | Value |
|--------|-------|
| Dataset | 106 cases: 63 train / 43 test (KeyError 90, AttributeError 16) |
| Precision@1 | 24/24 = 100% |
| Precision@3 | 24/24 = 100% |
| Positive coverage | 24/24 = 100% |
| Overall false positive rate | 2/19 negative cases = 10.5% (≈11%) |
| Matched / abstained | 26 / 17 (26 = the 24 positive cases + the 2 false positives) |

Both false positives are KEY001 (`KEY001-043`, `KEY001-074`). Confidence
calibration: [0.6–0.7) 76% on n=17, [0.8–0.9) 100% on n=2 (low N,
indicative only), [0.9–1.0) 100% on n=9. Average analysis time varies
from run to run and is not a stable performance claim.

## Rule strategy summary

Per-rule counts on the same split. `Fired` counts candidates at any
rank, and `False positives` is a count over the 19 negative cases, not a
rate (see "Overall rate versus per-rule counts").

| Rule    | Strategy                     | Precision@1 | Coverage | Fired | Correct | False positives | Avg Confidence |
|---------|-------------------------------|------------:|---------:|------:|--------:|----------------:|---------------:|
| KEY001  | Fuzzy lexical similarity (restricted Damerau-Levenshtein, max distance 1) | 100% | 100% | 17 | 13 | 2 | 0.65 |
| KEY002  | Deterministic normalization     | 100%        | 100%     | 4     | 4       | 0               | 0.95           |
| KEY003  | Structural context analysis    | 100%        | 100%     | 2     | 2       | 0               | 0.90           |
| ATTR001 | Runtime object inspection      | 100%        | 100%     | 1     | 1       | 0               | 0.98           |
| ATTR002 | Deterministic API lookup (built-in container method confusion) | 100% | 100% | 2 | 2 | 0 | 0.95 |
| ATTR003 | Lexical typo heuristic (attribute-name typos) | 100% | 100% | 2 | 2 | 0 | 0.84 |

No rule missed a positive case it was expected to fire on. KEY001's 17
firings are 13 correct, 2 false positives and 2 appearances as the
second-ranked candidate behind KEY002 on positive cases
(`KEY002-005`, `KEY002-007`), which count as neither correct nor false
positive.

TraceKit is not "just edit distance" — each rule uses a genuinely
different diagnostic strategy, evaluated under one shared methodology.
The pattern holds across exception families, not just within
KeyError: the four deterministic rules (KEY002, KEY003, ATTR001,
ATTR002) all recorded zero false positives with near-instant execution,
while KEY001, the heuristic rule with the largest number of firings,
carries all of the measured false-positive risk in this dataset. ATTR003
is also a lexical heuristic; it recorded no false positives here, but on
only 2 firings, so that is weak evidence either way. The pattern is
expected, not a flaw — lexical similarity is inherently probabilistic,
while case-folding, one-level structural lookup, a fixed table of
built-in container methods, and reading CPython's own structured
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
| v2.0.0  | 100 cases (test split: 39 = 21 pos / 18 neg) | 100% | 22% (4/18) | 100% | ATTR002 and ATTR003 added; both exception families closed. The v1.0.0 snapshot recorded 4 false positives over 16 negative cases (25%); here the negative set has grown to 18, so 4 false positives is 22% |
| GH-20   | 103 cases (test split: 41 = 23 pos / 18 neg) | 100% | 22% (4/18) | 100% | +3 KeyError cases (`71c8a12`); sentence-style KeyError message extraction fixed (`dae8026`). No change in false positives |
| GH-01   | 105 cases (test split: 42 = 24 pos / 18 neg) | 100% | 22% (4/18) | 100% | +2 KeyError cases (`067967c`); KEY001 explanation wording made direction-neutral (`2f1c795` changes the explanation string only). No change in false positives |
| GH-02   | 106 cases (test split: 43 = 24 pos / 19 neg) | 100% | 10.5% (2/19) | 100% | +1 negative case, `data`/`meta` (`255bd17`); KEY001 switched to restricted Damerau-Levenshtein with max distance 2 → 1 (`34f3f46`). On the same 19 negatives, false positives fell from 5 (26%) before the fix to 2 after, and KEY001's 13 correct matches were preserved |

How to read the table: rows up to ATTR001 are the figures recorded at the
time. The v2.0.0 and GH-* rows were produced by running
`python -m benchmark.run` on a clean checkout of the named commit (the
v2.0.0 tag commit `04944a5`, then `dae8026`, `2f1c795` and `34f3f46`),
and the GH-02 "before" figure by running it at `255bd17`, which has the
GH-02 ground-truth case but not the fix. The dataset and test split grow
between rows, so the FP Rate column is a within-row measurement and is
not directly comparable across rows. The frozen `benchmark_v2.0.0.*`
snapshot matches the v2.0.0 row (39 test cases, 22%); its header reads
"run tag: latest" instead of "v2.0.0", a labelling quirk left as-is.

Full v1.0.0 and v2.0.0 outputs are saved as frozen artifacts:
`benchmark/results/benchmark_v1.0.0.{txt,json}` and
`benchmark_v2.0.0.{txt,json}`. `python -m benchmark.run` does not
overwrite them; it writes `benchmark_latest.*`.

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
