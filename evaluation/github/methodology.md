# Real-World Evaluation — Methodology

## Goal

Answer one question the benchmark alone cannot: **does TraceKit work
on code it wasn't designed against?** `benchmark/` proves TraceKit
performs well on its own dataset. This evaluation checks generalization
to genuine bugs from public repositories TraceKit has never seen.

## Sourcing

20 examples were found via web search across public GitHub issues and
pull requests, targeting `KeyError` and `AttributeError` bugs with
enough public detail (a real traceback, or a diff/description
identifying the actual fix) to reconstruct faithfully. Search terms
covered: typo-caused KeyErrors, missing-key KeyErrors (to get honest
negative cases, not just favorable ones), NoneType AttributeErrors,
built-in container API confusion, case-mismatched dict/DataFrame keys,
and attribute-name typos.

**Explicit rule followed throughout: no cherry-picking.** Cases were
kept in the set once found and verified as real, regardless of whether
the anticipated TraceKit outcome looked favorable. Three of the 20
cases are recorded as outright incorrect — see `results.csv` and the
Failures section below.

**A genuine gap, stated rather than papered over:** despite a real
search effort, no publicly well-documented example of a one-level
nested-dict KeyError (`config['host']` failing when
`config['database']['host']` exists — KEY003's territory) was found
within the search budget. Rather than force a weak or synthetic
example into this set to hit a target category, this is recorded as a
known limitation of this evaluation round, not silently omitted.

## Reconstruction

Each case is a minimal, original Python reproduction of the bug's
essential shape — not code copied verbatim from the source repository
(respecting upstream licenses). What's preserved faithfully from the
cited source:
- the exact exception type
- the real traceback shape (same kind of expression failing)
- the real, cited fix (paraphrased from the issue/PR text, not quoted verbatim)

Every reconstruction was checked to actually raise the claimed
exception before being included — see `evaluate("in the actual repro
functions")` and the fact that the run script raises `AssertionError`
if a repro doesn't raise as expected.

## Execution — this is real, not simulated

`run_evaluation.py` imports TraceKit's actual `analyze()` function and
runs it against each reconstructed repro's real, live exception and
traceback — the exact same code path used by the CLI and the
benchmark. **Every value in the `tracekit_diagnosis` column of
`results.csv` is the literal, unedited output of that function call.**
Nothing in that column was written by hand.

## Judging correctness

`correct` and `notes` are the one part of this evaluation that
required human judgment, not automated comparison — TraceKit's output
was compared against the real, cited fix for each case and judged as:

- **Yes** — TraceKit's top diagnosis matches the real fix's underlying
  cause.
- **Yes (immediate cause only)** — TraceKit correctly identifies a true
  fact (e.g. "this object is `None`"), but the real-world fix requires
  understanding something upstream TraceKit doesn't attempt to trace
  (see README's documented "diagnoses the raise site, not upstream
  causal chains" limitation). Not wrong, just narrower than the full
  real-world fix.
- **Yes (generic phrasing)** — the correct rule fired with the correct
  underlying fact, but couldn't name a specific variable (see GH-14).
- **No** — TraceKit's diagnosis is either a false positive (suggests a
  cause that isn't the real one) or a false negative (misses a case it
  should have caught, i.e. abstains when a correct, in-scope diagnosis
  was actually available).

## Results summary

**13 fully correct, 4 correct-with-a-stated-caveat, 3 incorrect, out
of 20** (see `results.csv` for the full breakdown, and the README for
analysis of each failure).

This is a real number from a real, small sample — not a claim of
general accuracy. Treat it the same way the benchmark's own numbers
are treated (see `benchmark/README.md`'s scope disclaimer): as
evidence about this specific sample, not a universal guarantee.
