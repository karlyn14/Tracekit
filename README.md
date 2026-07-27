# TraceKit

![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)
![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

TraceKit diagnoses common Python exceptions and suggests likely causes
— never certain ones — without hiding the original traceback.

```
KeyError: 'Nmae'

--- TraceKit suggestions (not certainty — verify against your code) ---

[KEY001] Likely cause (confidence 0.40):
  'Nmae' is not a key — did you mean 'Name'?
  Evidence:
    - Requested key: 'Nmae'
    - Closest available key: 'Name'
    - Edit distance: 2
  Suggested fix: Check for a typo: 'Nmae' vs 'Name'
```

## Problem

Existing traceback tools (`rich`, `better-exceptions`, IPython's
formatter) make tracebacks *prettier*. None of them diagnose *why* an
exception happened. TraceKit fills that specific, narrow gap: pattern
recognition over common exception shapes, with an evaluation
methodology to back every claim it makes.

## Architecture

```
Exception
   │
   ▼
ExceptionContext   ── a memory-safe snapshot: source line, AST,
   │                   local variable names/types, key/column names,
   │                   one level of nested-dict structure. The frame
   │                   itself is never retained past this point.
   ▼
RuleRegistry       ── O(1) lookup by exception type. Every rule call
   │                   is wrapped in try/except: a broken rule is
   │                   logged and skipped, never crashes the analyzer
   │                   diagnosing the crash.
   ▼
Candidate Rules    ── each rule independently returns a MatchResult
   │                   (confidence, explanation, evidence, fix) or
   │                   None. Rules never talk to each other.
   ▼
Ranking            ── sorted by confidence, then priority, then
   │                   registration order (fully deterministic —
   │                   never an arbitrary tiebreak).
   ▼
Formatter          ── raw traceback always shown, unmodified.
                       Suggestions are additive and clearly labeled
                       "likely cause", never "root cause".
```

Full code: `tracekit/core/` (`context.py`, `registry.py`, `rule.py`,
`analyzer.py`), `tracekit/rules/`, `tracekit/output/formatter.py`.

## Rule engine

A `Rule` is a plain Python class exposing:
- `RULE_ID` — a stable identifier (e.g. `KEY001`), never renamed once released
- `exception_types` — which exception classes it applies to
- `matches(ctx) -> MatchResult | None` — must be side-effect free and never raise

Adding a rule means writing one class and registering it in
`rules/__init__.py` — zero changes to existing code, addressing the
"why not YAML/plugins" question directly: v1 uses compiled Python
rules because there was no evidence a declarative schema was needed
at ~10 rules; the interface is designed so a declarative loader could
be added later without a rewrite.

### Implemented rules

| Rule   | Strategy                    | What it catches |
|--------|------------------------------|-----------------|
| KEY001 | Fuzzy lexical similarity (edit distance, ambiguity-aware) | Likely typos in dict/DataFrame keys |
| KEY002 | Deterministic case normalization | Key exists with different letter casing |
| KEY003 | Structural context analysis (one-level nested lookup) | Key exists one level deeper in a nested dict |

Each rule uses a genuinely different diagnostic strategy — TraceKit
is not "just edit distance"; it's a small framework for testing
different diagnostic approaches under one shared evaluation.

## Benchmark methodology

Every rule earns its place with evidence, not intuition. Full detail
in `benchmark/README.md`; summary here:

- **84 cases**, hand-written + Stack-Overflow-style + GitHub-issue-style,
  split into train/test.
- **Rules are designed only against the train split.** All reported
  metrics run exclusively on the held-out test split — this is the
  direct fix for dataset leakage (designing a rule against a case,
  then "testing" on that same case proves nothing).
- **Negative and adversarial cases are included on purpose** — e.g.
  `SERVER_HOST` vs `SERVER_PORT` (similar-looking, NOT a typo of each
  other) — specifically to measure false positives, not just coverage.
  A benchmark of only positive examples can never reveal how often a
  tool confidently gives wrong advice.
- **Rule acceptance criterion:** *a rule is accepted only if it
  improves held-out precision or coverage without an unacceptable
  increase in false positives.*

Run it: `python -m benchmark.run`

## Results

**Scope note, read before citing these numbers anywhere:** every
percentage below is measured on TraceKit's own 84-case benchmark
dataset (`benchmark/data/keyerror_cases.jsonl`), split train/test, for
the KeyError exception type only. It is not a general claim about
Python error diagnosis, and it is not validated against a truly
independent, external dataset. Treat these as "measured on this
benchmark, under this methodology" — not as universal accuracy claims.
See `benchmark/README.md` for exactly what's in the dataset and its
known composition/size limitations.

| Rule   | Strategy                     | Precision@1 | Coverage | FP Rate | Avg Confidence | Avg Exec Time |
|--------|-------------------------------|------------:|---------:|--------:|---------------:|--------------:|
| KEY001 | Fuzzy lexical similarity       | 100%        | 100%     | ~25%    | 0.57           | 0.030 ms      |
| KEY002 | Deterministic normalization     | 100%        | 100%     | 0%      | 0.95           | 0.002 ms      |
| KEY003 | Structural context analysis    | 100%        | 100%     | 0%      | 0.90           | 0.001 ms      |

**Hypothesis, supported by the above:** deterministic diagnostic
strategies (KEY002, KEY003) achieve higher precision and zero measured
false positives compared to heuristic lexical similarity (KEY001),
though they solve a narrower class of problems. This is expected, not
a flaw — case-folding and one-level structural lookup are exact checks
with no room for ambiguity once a match is found; lexical similarity
is inherently probabilistic.

## Known limitations (documented, not hidden)

- **KEY001 has a real, measured false-positive rate (~25% on adversarial
  cases).** Raw edit distance cannot distinguish "typo of an existing
  key" from "a different key that happens to look similar"
  (`FEATURE_X`/`FEATURE_Y`, `SERVER_HOST`/`SERVER_PORT`). Further
  reducing this would need semantic/contextual signals beyond lexical
  similarity — out of scope for KEY001 by design.
- **v1 diagnoses the raise site, not upstream causal chains.** If
  `foo()` returns `None` and `x.name` then raises `AttributeError`,
  TraceKit explains the immediate `AttributeError`, not that `foo()`
  was the true origin. Walking frames backward is a natural v2
  direction.
- **KEY003 is capped at exactly one level of nesting, by design** —
  not a bug. Recursive search into arbitrarily deep structures would
  produce guesses ("maybe `a.b.c.d.host`") rather than confident
  diagnoses.
- **Scope is deliberately narrow**: KeyError, plain dicts and
  DataFrame-like `.columns` only. No async, multiprocessing, C
  extensions, or non-English error messages in v1.

## Lessons learned during implementation

These are actual findings from building this, not speculative future
work:

- **Raw edit distance overestimates typo likelihood for semantically
  distinct identifiers.** Distance-1/2 pairs like `SERVER_HOST`/
  `SERVER_PORT` or `FEATURE_X`/`FEATURE_Y` are common in real
  configuration code and are indistinguishable from genuine typos
  using lexical similarity alone.
- **Ambiguity detection reduced false positives without reducing
  coverage.** Abstaining when two candidates tie for closest match
  (e.g. `'it'` equidistant from `'id'` and `'ip'`) dropped the
  measured false positive rate on one benchmark slice from 33% to 0%,
  with precision@1 and coverage unchanged.
- **Case-insensitive matching needs its own rule, not a forgiving edit
  distance threshold.** Short case differences (`Token`/`token`,
  distance 1) happen to fall under KEY001's threshold; longer ones
  (`API_KEY`/`api_key`, distance 6) don't. This inconsistency is what
  motivated KEY002 as a dedicated, deterministic check instead of
  tuning KEY001's threshold further.
- **The benchmark can specify ground truth ahead of implementation.**
  KEY003's benchmark cases were written before the rule existed,
  tracked as "pending" rather than counted as failures, and the rule
  was later built specifically to satisfy that pre-committed
  specification — a stronger methodological story than inventing
  rules first and testing after.
- **Benchmark-driven development surfaced real bugs earlier than
  manual testing would have.** Growing the dataset from 12 to 84 cases
  (adding deliberately adversarial "similar but different" pairs)
  raised the measured KEY001 false-positive rate from 10% to ~25% —
  not a regression, but the dataset doing exactly what it was
  expanded to do.

## Releases

**v1.0.0** — Feature-complete implementation: pipeline, KEY001-003,
84-case benchmark, CI, ADRs, 22 tests at 92% coverage.

**v1.0.1** — Demo script, HTML coverage report, strengthened benchmark
scope disclaimer. Documentation and presentation only — no functional
changes to rules, pipeline, or benchmark logic.

## Architecture Decision Records

Key design decisions, with rationale and consequences, in `docs/adr/`:
- [0001 — Rule Registry: compiled classes, not declarative YAML](docs/adr/0001-rule-registry.md)
- [0002 — Confidence Model: heuristic scores, ambiguity as abstention](docs/adr/0002-confidence-model.md)
- [0003 — Benchmark Methodology: train/test split, ground truth ahead of implementation](docs/adr/0003-benchmark-methodology.md)

Prepared answers to the core viva questions: [docs/viva_prep.md](docs/viva_prep.md)

## Future work

- KEY004+: additional exception types beyond KeyError (AttributeError,
  IndexError, TypeError)
- Frame-walking for upstream causal chains (documented v1 limitation)
- A declarative rule format, if/when the rule count justifies it (see
  "Rule engine" above)
- `sys.excepthook` integration for zero-config drop-in use

## Demo

For a viva or a 2-3 minute video, `demo.py` runs the whole story as
one command: a normal Python crash → the same crash diagnosed by
TraceKit → the benchmark run → the test suite passing.

```bash
python demo.py          # with short pauses, good for narrating live
python demo.py --fast   # no pauses, good for CI or a quick check
```

## Testing & CI

- **22 tests, 92% coverage** — unit tests per rule (`tests/test_keyerror_rules.py`)
  plus property-based fuzz tests (`tests/test_property_based.py`, via
  [Hypothesis](https://hypothesis.readthedocs.io/)) that generate ~250
  arbitrary/malformed inputs (unicode keys, missing tracebacks,
  un-repr-able objects, 50-level-deep nesting) to verify the core
  robustness claim: **TraceKit never crashes while diagnosing a crash.**
  Generate a browsable HTML coverage report with
  `python -m pytest tests/ --cov=tracekit --cov-report=html` (writes
  to `htmlcov/index.html` — a screenshot of this is much stronger in
  a dissertation than a bare percentage).
- GitHub Actions (`.github/workflows/ci.yml`) runs the full test suite,
  the benchmark (as a regression check), and the smoke test on every
  push, across Python 3.10–3.12.

## Running it

```bash
python -m pytest tests/ -v                              # unit + property tests
python -m pytest tests/ --cov=tracekit --cov-report=term-missing  # with coverage
python -m benchmark.run                                   # full benchmark report
python smoke_test.py                                       # end-to-end sanity check
```
