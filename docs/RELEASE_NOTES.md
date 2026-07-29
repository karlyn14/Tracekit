# Release Notes

These are written for use as GitHub Release descriptions (Releases →
Draft a new release → select each tag → paste the matching section).

---

## v1.0.0 — Feature-complete release

**Highlights**
- Core pipeline: `ExceptionContext` (memory-safe snapshot, no frame
  retained past analysis), `RuleRegistry` (O(1) lookup, crash-isolated
  rule execution, deterministic tie-breaking), `Analyzer`, `Formatter`
  (raw traceback always shown in full).
- Three diagnostic strategies, each independently benchmarked:
  - **KEY001** — fuzzy lexical similarity (typo detection via edit
    distance, abstains on ambiguous ties)
  - **KEY002** — deterministic case-insensitive normalization
  - **KEY003** — one-level nested-dict structural lookup
- 84-case benchmark dataset (train/test split, adversarial negatives,
  ground-truth-ahead-of-implementation for future rules)
- 22 tests (unit + Hypothesis property-based fuzzing), 92% coverage
- CI via GitHub Actions across Python 3.10–3.12
- Three ADRs documenting the registry, confidence model, and benchmark
  methodology design decisions

**Results (measured on the held-out test split — see README "Results"
scope note before citing elsewhere)**

| Rule | Strategy | Precision@1 | Coverage | FP Rate |
|---|---|---:|---:|---:|
| KEY001 | Fuzzy lexical similarity | 100% | 100% | ~25% |
| KEY002 | Deterministic normalization | 100% | 100% | 0% |
| KEY003 | Structural context analysis | 100% | 100% | 0% |

---

## v1.0.1 — Documentation & presentation

**Changes**
- `demo.py` — scripted end-to-end demo (normal crash → TraceKit
  diagnosis → benchmark → test suite), runnable as one command
- Real, browsable HTML coverage report (`htmlcov/index.html`)
- Strengthened benchmark scope disclaimer, placed directly beside the
  results table in the README

**No functional changes** to rules, pipeline, or benchmark logic.

---

## v1.0.2 — Documentation maintenance & reproducibility fix

**Changes**
- `docs/viva_prep.md` — concise, evidence-linked answers to core
  design questions
- Releases section added to README
- **Fix:** benchmark runs no longer silently overwrite frozen release
  artifacts. Running the benchmark (including via `demo.py`) was
  quietly mutating `benchmark_v1.0.0.*` with fresh timing numbers on
  every run — a released, supposedly-frozen artifact was actually
  mutable. Live runs now write to `benchmark_latest.*` (gitignored);
  versioned snapshots must be copied and committed deliberately at
  release time.

**Lesson learned (see dissertation Evaluation chapter):** a notable
engineering issue encountered during development was the accidental
mutation of released benchmark artifacts by the demonstration
workflow. This was resolved by separating immutable versioned
benchmark outputs from mutable development artifacts, improving the
reproducibility of experimental results.

No functional changes to rules or pipeline.

---

## v2.0.0 — Two exception families closed

**Highlights**
- **AttributeError family closed** (3/3 planned rules): ATTR001
  (runtime object inspection — `None` attribute access), ATTR002
  (deterministic API-confusion lookup — e.g. `.append()` on a `str`),
  ATTR003 (lexical typo heuristic — attribute/method name typos).
- **KeyError family remains closed** (3/3): KEY001-003, unchanged
  since v1.0.0 — zero regressions across the entire v1.0.0 → v2.0.0
  span.
- Benchmark's "ground-truth rules... not yet implemented" section is
  **empty for the first time** — every rule ever committed to as
  ground truth ahead of implementation has been built and accepted.
- **ADR 0004**: formalized the Rule Independence Invariant (rules
  never inspect each other's outputs; conflicts resolve solely via
  confidence-tier ranking) and the project-wide confidence tiers
  (structural fact / deterministic lookup / strong heuristic / weak
  heuristic) that make that invariant enforceable without any rule
  coupling.
- `docs/design/ATTR003.md`: the project's first written design
  contract, frozen before any benchmark case or implementation existed
  — the first heuristic rule in a second family went from red tests
  to accepted with zero iteration, directly attributable to this step.
- `docs/RETROSPECTIVE_v2.md`: honest retrospective on what worked and
  what cost time across both families, written specifically to inform
  the next exception family rather than repeating discovery.
- 51 tests (up from 22 at v1.0.0), 92% coverage maintained throughout.

**Results (measured on the held-out test split — see README "Results"
scope note before citing elsewhere)**

| Rule | Strategy | Precision@1 | Coverage | FP Rate |
|---|---|---:|---:|---:|
| KEY001 | Fuzzy lexical similarity | 100% | 100% | ~25% |
| KEY002 | Deterministic normalization | 100% | 100% | 0% |
| KEY003 | Structural context analysis | 100% | 100% | 0% |
| ATTR001 | Runtime object inspection | 100% | 100% | 0% |
| ATTR002 | Deterministic API lookup | 100% | 100% | 0% |
| ATTR003 | Lexical typo heuristic | 100% | 100% | 0% |

**Project-level acceptance criterion for v3.0** is now stated
explicitly in the README, not left open-ended: a third exception
family closed (all planned rules accepted), 9-10 total accepted rules,
no reduction in coverage from 92%, no increase in KEY001's false
positive rate, benchmark reproducibility unchanged.

No functional regressions on any KeyError rule.
