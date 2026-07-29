# TraceKit

![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)
![Tests](https://img.shields.io/badge/tests-51%20passed-brightgreen)
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

### Implemented rules — a strategy matrix, not just a rule count

Each new rule is chosen to demonstrate a genuinely different
diagnostic *strategy*, not just to cover another exception type. The
architecture's real claim is that it generalizes across exception
families without redesign — the AttributeError family (below) is the
proof: all three rules added with zero changes to the core pipeline
(`context.py`, `registry.py`, `analyzer.py`, `formatter.py`).

| Family | Rule | Strategy | What it catches |
|---|---|---|---|
| KeyError | KEY001 | Fuzzy lexical similarity | Likely typos in dict/DataFrame keys |
| KeyError | KEY002 | Deterministic normalization | Key exists with different letter casing |
| KeyError | KEY003 | Structural context analysis | Key exists one level deeper in a nested dict |
| AttributeError | ATTR001 | Runtime object inspection | Attribute/method accessed on a `None` value |
| AttributeError | ATTR002 | Deterministic API lookup | Built-in container method confusion (e.g. `.append()` on a `str`) |
| AttributeError | ATTR003 | Lexical typo heuristic | Attribute/method name is a likely typo of a real one on the object |

**AttributeError is closed at 3/3 planned rules** — every rule this
benchmark ever committed to ahead of implementation has been built and
accepted (see `benchmark/README.md`; the "ground-truth rules... not
yet implemented" report section is empty for the first time). Further
AttributeError rules would need a new benchmark case and an explicit
roadmap decision, not just "since we're here."

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
percentage below is measured on TraceKit's own benchmark dataset
(`benchmark/data/*_cases.jsonl`, one file per exception family), split
train/test, currently covering KeyError and AttributeError. It is not
a general claim about Python error diagnosis, and it is not validated
against a truly independent, external dataset. Treat these as
"measured on this benchmark, under this methodology" — not as
universal accuracy claims. See `benchmark/README.md` for exactly
what's in the dataset and its known composition/size limitations.

| Rule   | Strategy                     | Precision@1 | Coverage | FP Rate | Avg Confidence | Avg Exec Time |
|--------|-------------------------------|------------:|---------:|--------:|---------------:|--------------:|
| KEY001 | Fuzzy lexical similarity       | 100%        | 100%     | ~25%    | 0.57           | 0.036 ms      |
| KEY002 | Deterministic normalization     | 100%        | 100%     | 0%      | 0.95           | 0.003 ms      |
| KEY003 | Structural context analysis    | 100%        | 100%     | 0%      | 0.90           | 0.001 ms      |
| ATTR001| Runtime object inspection      | 100%        | 100%     | 0%      | 0.98           | 0.002 ms      |
| ATTR002| Deterministic API lookup       | 100%        | 100%     | 0%      | 0.95           | 0.003 ms      |
| ATTR003| Lexical typo heuristic         | 100%        | 100%     | 0%      | 0.84           | 0.089 ms      |

**Hypothesis, supported by the above:** deterministic diagnostic
strategies (KEY002, KEY003, ATTR001, ATTR002) reliably achieve zero
measured false positives, while heuristic lexical strategies (KEY001,
ATTR003) carry some false-positive risk by nature of inferring from
similarity rather than observing a fact — though ATTR003 measured 0%
FP on its own current benchmark, its confidence tier (0.80-0.90) is
set below the deterministic rules specifically because that risk is
structural, not because it has been observed yet at this dataset size.
This pattern held across two entirely different exception families,
which is evidence the finding is about the diagnostic strategy, not
something specific to KeyError. ATTR003 also measurably costs more
compute than deterministic lookups (0.089ms vs ~0.002-0.003ms) — the
price of searching filtered candidates by edit distance instead of an
O(1) lookup, still negligible in absolute terms. (Timing figures carry
normal run-to-run jitter — see `benchmark/run.py`'s p95 reporting for
a steadier picture than a single average.)

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
- **The architecture generalized to a second exception family with
  zero core changes.** Adding ATTR001 (AttributeError) touched exactly
  two files — the new rule and its registration — and required no
  changes to `ExceptionContext`, `RuleRegistry`, `Analyzer`, or
  `Formatter`. This is the first real evidence that the pipeline
  designed around KeyError wasn't accidentally KeyError-specific.
- **Reporting gaps should be fixed in the report, not the dataset.**
  When a pending rule's only ground-truth case happened to sit in the
  train split (making it invisible in a test-split-only pending
  report), the fix was to make the report honestly show train/test
  counts for every un-implemented rule — not to add a manufactured
  benchmark case just to make a status table look complete.
- **A design-contract step written before any benchmark cases paid
  for itself exactly once, and it was worth it.** ATTR003 (the first
  heuristic rule in a second family) went from red tests to accepted
  on the first implementation attempt, with zero iteration — the only
  heuristic rule in the project to do so. Full analysis in
  [`docs/RETROSPECTIVE_v2.md`](docs/RETROSPECTIVE_v2.md), written
  before starting IndexError specifically so this doesn't need
  rediscovering.

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
- [0004 — Rule Independence Invariant: rules never inspect each other, conflicts resolve via confidence ranking](docs/adr/0004-rule-independence-invariant.md)

Prepared answers to the core viva questions: [docs/viva_prep.md](docs/viva_prep.md)

## Roadmap

Not "add more rules" — each exception family should demonstrate
multiple distinct reasoning techniques, so the benchmark keeps
comparing diagnostic strategies rather than just accumulating count.

**Progress by family** (planned rule counts are working targets, not
commitments — they'll adjust as each family's benchmark reveals what's
actually worth building):

| Family | Rules planned | Implemented | Status |
|---|---:|---:|---|
| KeyError | 3 | 3 | Closed |
| AttributeError | 3 | 3 | Closed |
| IndexError | — | 0 | Next |
| TypeError | — | 0 | Planned |
| ValueError | — | 0 | Planned |

**KeyError — closed** (3/3 strategies represented): heuristic lexical
(KEY001), deterministic normalization (KEY002), structural (KEY003).

**AttributeError — closed** (3/3 strategies represented): runtime
object inspection (ATTR001), deterministic API lookup (ATTR002),
lexical typo heuristic (ATTR003). Every rule this benchmark ever
committed to ahead of implementation has been built and accepted — the
"ground-truth rules... not yet implemented" report section is empty
for the first time (see `benchmark/README.md`). "Closed" means further
AttributeError rules require a new benchmark case and an explicit
roadmap decision, not that the family can never grow — the point is to
avoid a family feeling permanently half-finished by default.

**IndexError is next.** Before starting it: see
[`docs/RETROSPECTIVE_v2.md`](docs/RETROSPECTIVE_v2.md) for what
actually worked and cost time across KeyError and AttributeError,
written specifically to inform this transition rather than repeating
the same discovery process. One concrete watch-item carried forward:
`_levenshtein` is now duplicated in both `rules/keyerror/rules.py` and
`rules/attributeerror/rules.py` — not yet worth extracting (see ADR
0001 on avoiding premature abstraction), but a third occurrence in
IndexError is the signal to actually do it.

**Future families**, each intended to eventually span multiple
strategies rather than a single rule: TypeError, ValueError,
ImportError/ModuleNotFoundError, ZeroDivisionError, FileNotFoundError.

**Beyond new rules:**
- Frame-walking for upstream causal chains (v1 only diagnoses the
  raise site — documented limitation, applies across all families)
- A declarative rule format, if/when rule count actually justifies it
  (ADR 0001 — deliberately not built prematurely)
- A richer shared `RuleResult` abstraction, if/when enough rules
  across enough families are visibly duplicating the same
  confidence/evidence/fix construction — six rules across two families
  haven't shown clear enough duplication yet to justify this; revisit
  once IndexError exists and there's a third family's worth of
  evidence either way
- `sys.excepthook` integration for zero-config drop-in use
- IDE integration, PyPI packaging, plugin API for third-party rule
  packs — real directions, explicitly not v1 scope

## Suite health (tracked over time, not just a snapshot)

The exact test count matters less than whether the suite stays fast
and the coverage trend holds as the project grows — tracking both
here rather than only quoting a single current number.

| Milestone | Tests | Test runtime | Benchmark runtime | Coverage |
|---|---:|---:|---:|---:|
| v1.0.0 (KEY001-003) | 22 | ~0.6s | ~0.05s | 92% |
| ATTR001 added | 31 | ~0.9s | ~0.07s | 92% |
| AttributeError closed (ATTR001-003) | 51 | ~1.8s | ~0.09s | 92% |

## Demo

For a viva or a 2-3 minute video, `demo.py` runs the whole story as
one command: a normal Python crash → the same crash diagnosed by
TraceKit → the benchmark run → the test suite passing.

```bash
python demo.py          # with short pauses, good for narrating live
python demo.py --fast   # no pauses, good for CI or a quick check
```

## Testing & CI

- **51 tests, 92% coverage** — unit tests per rule
  (`tests/test_keyerror.py`, `tests/test_attributeerror.py`)
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
