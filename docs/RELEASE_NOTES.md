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

---

## v2.1.0 — CLI, external evaluation, and KEY001 refinements

**Status: upcoming / unreleased — not yet tagged, released or
published.** `pyproject.toml` declares `2.1.0`. This is a minor
release: it adds no new exception family and no new rules. The rule set
is unchanged (KEY001-003, ATTR001-003).

**Highlights**
- **Command-line interface:** `tracekit diagnose <path>`, for example
  `tracekit diagnose crash.py`. Given a `.py` file, it runs the script
  and diagnoses the first uncaught exception using the real traceback,
  so every rule has the live state it needs. Given any other file, it
  does a best-effort diagnosis from pasted traceback text.
- **External evaluation:** `evaluation/github/` runs 20 exception
  examples from public GitHub issues and pull requests through
  TraceKit's actual `analyze()` code path.
- **KEY001 refinements** from that evaluation: a distance metric that
  treats adjacent-character swaps as one edit (GH-02), and an
  explanation that no longer assumes which spelling is the correct one
  (GH-01).
- **MIT license:** the project is now MIT-licensed, with a standard
  root-level `LICENSE` file and matching package metadata.

**Fixes and refinements**
- **GH-20 — sentence-style KeyError messages.** Some libraries raise
  `KeyError` with a full descriptive sentence as `args[0]`, such as
  pandas' `.astype()` column check, instead of the bare key. Every
  KeyError rule assumed `args[0]` was the key, so a fixable
  case-mismatch was missed. The key is now extracted from such
  messages; bare keys that contain spaces still work.
- **GH-01 — direction-neutral KEY001 explanation.** KEY001 compares two
  spellings but cannot know which one is the typo. The explanation now
  reads "the closest existing key is 'X' (edit distance N)" instead of
  "did you mean 'X'?". No change to which cases match.
- **GH-02 — Damerau-Levenshtein matching in KEY001.** KEY001 now uses
  restricted Damerau-Levenshtein distance (Optimal String Alignment),
  where swapping two adjacent characters costs one edit, and its
  maximum edit distance is 1 (previously 2 under plain Levenshtein).
  Genuine transposition typos such as `Nmae`/`Name` are still caught,
  and independent near-misses such as `data`/`meta` no longer match.
  On the same 19 negative test cases, KEY001 false positives fell from
  5 to 2, and KEY001's 13 correct matches were retained (Precision@1
  and positive coverage stayed at 100%). This is a measurement on
  TraceKit's own benchmark, not a claim about other datasets. The three
  removed false positives are `data`/`meta`, `host`/`port` and
  `SERVER_HOST`/`SERVER_PORT`. The before-figure comes from running the
  benchmark at the commit that added the ground truth but not the fix,
  so it uses the same dataset.
- **Dunder-local pollution.** At module scope (for example a script run
  through the CLI), `frame.f_locals` includes `__builtins__`, a dict of
  about 150 names, which flooded KEY001's candidate keys. Found while
  testing the CLI: `'Nmae'` tied with `'None'`. `ExceptionContext` now
  skips dunder-named locals.
- **Packaging metadata:** the `version` in `pyproject.toml` still read
  `1.0.0` at the `v2.0.0` tag. It is `2.1.0` from this release. The
  `tracekit` console script and the MIT license metadata are declared
  there.

**Behavior changes to be aware of**
- KEY001 now suggests only keys within edit distance 1 (counting an
  adjacent swap as 1). Some distance-2 suggestions that appeared in
  v2.0.0 no longer appear, which is the intended reduction in false
  positives but also means fewer suggestions overall.
- KEY001's explanation text changed (see GH-01). Anything that matches
  on the old "did you mean" wording will need updating.

**External evaluation result (small sample)**

| Outcome | Count |
|---|---:|
| Fully correct | 16 |
| Correct, with a stated caveat | 4 |
| Incorrect | 0 |

This is the final result. The initial run scored 13 fully correct / 4
with a caveat / 3 incorrect. The three failures (GH-20, GH-01, GH-02)
were then fixed. Because those fixes were informed by these same 20
examples, 16/4/0 is not an untouched holdout, and 20 examples are not
evidence of broad generalization. The four caveats are three cases
where TraceKit names only the immediate cause and one where the
phrasing is generic. Details are in `evaluation/github/README.md`.

**Internal benchmark (measured on the held-out test split — see README
"Results" scope note before citing elsewhere)**
- Dataset: 106 cases (KeyError 90, AttributeError 16), split 63 train /
  43 held-out test. The test split has 24 positive and 19 negative
  cases.
- Precision@1: 24/24 = 100%. Precision@3: 24/24 = 100%. Positive
  coverage: 24/24 = 100%.
- Overall false-positive rate: **2/19 negative cases = 10.5% (about
  11%)**. The denominator is the negative test cases. Both false
  positives are KEY001 (`KEY001-043`, `FEATURE_X`/`FEATURE_Y`, and
  `KEY001-074`, `ENABLE_CACHE`/`ENABLE_CACHED`), but 11% is the
  benchmark-wide rate, not a KEY001-specific rate.
- Earlier release notes report a KEY001 false-positive figure of about
  25%. That was measured on earlier versions of the dataset and is not
  comparable with the figure above.
- Timing varies from run to run and is not a claim of this release.

**Tests:** 71 passing (51 at v2.0.0). Coverage is 93%, the figure from
the earlier pre-release audit; it was not re-measured when these notes
were written.

**Known limitations**
- The two current false positives are still `KEY001-043` and
  `KEY001-074`: similar-but-different identifiers that are not
  transpositions, such as `FEATURE_X` and `FEATURE_Y`. This is
  documented and accepted; fixing it would need signals beyond lexical
  similarity.
- TraceKit is heuristic and rule-based. Its suggestions are likely
  causes, not certain ones, and should be verified against the code.
- The external evaluation is small (20 examples) and not an untouched
  holdout, because the fixes were informed by those examples.
- The CLI's traceback-text mode has no live objects, so most rules
  cannot fire there, and it only reconstructs `KeyError` and
  `AttributeError`. `tracekit diagnose script.py` executes the script.
  The CLI has no other options beyond `-h`.
- TraceKit is not published on PyPI; install from a clone with
  `python -m pip install .`.
- v2.1.0 is not yet tagged, released or published.
- Results are measured on TraceKit's own benchmark and a 20-example
  external sample. They do not establish production readiness or
  general accuracy.
