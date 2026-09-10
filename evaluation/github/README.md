# Real-World Evaluation — GitHub Issues

**20 real exception examples, sourced from public GitHub issues/PRs,
executed against TraceKit's actual code.** Not a benchmark case set —
these are bugs TraceKit was never designed against, used to answer:
does the tool generalize past its own dataset?

Full methodology: [`methodology.md`](methodology.md). Raw results:
[`results.csv`](results.csv). Run it yourself: `python
evaluation/github/run_evaluation.py`.

## Headline result

**16 fully correct, 4 correct-with-a-stated-caveat, 0 incorrect, out
of 20** (originally 13/4/3 — all three original failures, GH-20,
GH-01, and GH-02, have since been fixed, see below) — a real number
from a small, honestly-sourced sample, not a general accuracy claim
(see the benchmark's own scope disclaimer, which applies equally
here).

| Outcome | Count | Cases |
|---|---:|---|
| Fully correct | 16 | GH-01,02,03,04,05,06,07,08,09,12,13,16,17,18,19,20 |
| Correct, immediate cause only | 3 | GH-10, 11, 15 |
| Correct, generic phrasing | 1 | GH-14 |
| **Incorrect** | **0** | — |

**Zero incorrect, on a real, external evaluation set.** Worth being
precise about what that does and doesn't mean: it's a genuine result
on 20 real cases, not a claim that KEY001 (or any rule) now has zero
false positives in general — `FEATURE_X`/`FEATURE_Y` and
`ENABLE_CACHE`/`ENABLE_CACHED` remain known, documented limitations
in the benchmark itself (see `benchmark/README.md`), just not
represented in this particular 20-case external sample. The right
next step if this number matters is growing this evaluation set
further, not treating 0/20 as "solved."

## GH-01 — fixed

Originally: a real, discovered directional limitation. TraceKit found
the right pair (`'exception'`/`'excetion'`, edit distance 1) but
suggested the wrong direction — *"did you mean `excetion`?"* — which
would make the code request the misspelled key, perpetuating the real
bug rather than fixing it (the actual fix renames the typo'd kwarg to
`exception`).

Unlike GH-20 (an extraction gap), this needed its own multi-stage
process before any code changed, since the initial instinct was that
it might need a whole new signal source (a word list, an identifier
frequency table, cross-frame inspection): `docs/design/GH01-failure-
analysis.md` (why it fails — edit distance is symmetric and carries no
information about which side is "standard"), `GH01-solution-design.md`
(candidate signals evaluated and explicitly rejected as overkill for
one case), `GH01-behavioral-contract.md` (the frozen, exact wording
change), then benchmark ground truth, RED tests, and only then the
one-line implementation change. The fix touches only KEY001's
`explanation` string — matching, confidence, evidence, and `fix` text
are all explicitly, verifiably unchanged (confirmed via a full
benchmark re-run showing byte-for-byte identical numbers before and
after). Explanation is now: *"'exception' is not a key — the closest
existing key is 'excetion' (edit distance 1)."* — states the fact
without implying which side is wrong.

## GH-20 — fixed

Originally: a real, discovered coverage gap. Pandas' `.astype()`
dtype-mapping check raises `KeyError` with a full descriptive
**sentence** as `args[0]` (`"Only a column name can be used... 'X' not
found in columns."`), not the bare key — every KeyError rule assumed
`args[0]` *is* the bare key, so this silently missed a real, fixable
case-mismatch bug that GH-09 (a different access pattern, same root
cause) caught correctly.

Per this project's benchmark-first discipline, this was **not**
patched reactively. It was promoted to proper benchmark ground truth
first (`KEY001-075/076/077` in `benchmark/data/keyerror_cases.jsonl`,
including a dedicated regression-safety case proving the fix
wouldn't break real space-containing bare keys), given unit tests
written against the *unfixed* code (confirmed red), then fixed in
`_missing_key_from_value()` — a fallback that extracts a single quoted
substring only when `args[0]` contains both a space and quote
characters, otherwise using it as-is exactly as before. Verified via a
full benchmark re-run: zero new false positives, zero regressions on
any of the other 89 benchmark cases. Then, and only then, this
external evaluation was re-run to confirm the fix against the original
real-world case.

## GH-02 — fixed

Originally: a real, confirmed instance of a known KEY001 limitation.
`'data'` and `'meta'` are both short, common words at edit distance 2
— within KEY001's threshold — but `'data'` is a legitimately,
sometimes-absent API field, not a typo of `'meta'`. Unlike GH-01, this
wasn't a directional/wording problem — KEY001 matched the *wrong pair
entirely*, and neither raising the confidence cutoff nor switching to
a length-normalized distance could fix it: both were checked directly
against real benchmark data (`docs/design/GH02-failure-analysis.md`,
Stage 7) and both failed for a quantified reason — a length-normalized
threshold tight enough to reject `data`/`meta` also rejects the
project's own canonical genuine-typo example, `Naem`/`Name` (identical
normalized distance, 0.50).

The actual fix, found by re-examining the failing cases directly
(`docs/design/GH02-solution-design.md`, Stage 8): a full sweep of
every KEY001 benchmark case needing plain-Levenshtein distance 2
showed **every single one** was an adjacent-letter transposition
(`Naem`/`Name`, `Heigth`/`Height`, `passwrod`/`password`, and others)
— while none of the known false positives were. Switched to restricted
Damerau-Levenshtein distance (a transposition costs 1 edit, not 2) and
tightened the threshold from 2 to 1 accordingly. Verified via a full
benchmark re-run: false positives dropped from 5 to 2, with **zero**
correct matches lost. `FEATURE_X`/`FEATURE_Y` and
`ENABLE_CACHE`/`ENABLE_CACHED` remain known, documented limitations —
explicitly out of scope for this fix (see the contract's own stated
scope, `docs/design/GH02-behavioral-contract.md`), not an oversight.

## GH-01 and GH-20 — see their own "fixed" sections above

Covered in their own sections above rather than repeated here, since
each fix's process is itself worth keeping visible as its own story —
particularly GH-01's, which took a full multi-stage design process
specifically to conclude that the *simplest* available fix (a wording
change, not a new signal source) was the right one, and GH-02's,
which took an even longer process (docs/design/GH02-*.md, seven
documents across failure analysis, solution design, and a behavioral
contract) to arrive at a fix that required no new dependency at all.

## No failures remain in this evaluation set

All three originally-recorded failures (GH-20, GH-01, GH-02) are now
fixed, each through the same benchmark-first discipline: understand
the failure, evaluate candidate solutions with real evidence, freeze
an exact contract, add ground truth, write RED tests, implement the
smallest change the evidence actually supports, then verify against
both the internal benchmark and this external evaluation. See "What
this evaluation does NOT do" below for what that does and doesn't
mean going forward.

## What generalized well

- **ATTR002 (container API confusion) generalized perfectly**: all
  three real `dict.append()` bugs found (GH-16, 17, 18, from three
  unrelated codebases) were diagnosed correctly. Worth noting as
  external validation that this exact mistake — a dict where a list
  was intended, then `.append()` called — is a genuinely common
  real-world error, not a contrived example invented for the
  benchmark.
- **ATTR003 (typo heuristic) got its first real-world validation**:
  GH-19 (`assertEquals` → `assertEqual`, a real Python 3.12 unittest
  deprecation) was diagnosed correctly. The project's own benchmark
  had no *external* validation for this specific rule before this
  evaluation — this is the first time it's been tested against code
  TraceKit's author didn't write.
- **The abstention discipline held**: 6 of 8 real KeyError cases with
  no close-candidate typo (GH-03 through GH-08) correctly produced no
  diagnosis rather than a guess — including cases involving genuinely
  absent API fields (`'commentCard'`, `'User'`, `'Platform'`) that a
  more aggressive fuzzy-matcher could easily have misfired on.
- **ATTR001's "immediate cause, not upstream chain" scope held up
  exactly as documented**: three real interpreter-teardown-timing bugs
  (GH-10, 11, 15) were correctly diagnosed at the level TraceKit
  actually claims to operate — "this object is `None`" — without
  overclaiming to explain *why* it became `None`, which in all three
  cases requires understanding of Python's shutdown/GC ordering that
  is explicitly out of scope.

## What this evaluation does NOT do

- It does not claim TraceKit is now free of false positives in
  general. `FEATURE_X`/`FEATURE_Y` and `ENABLE_CACHE`/`ENABLE_CACHED`
  remain known, documented limitations in `benchmark/README.md` —
  they simply aren't represented in this particular 20-case sample.
  All three fixes here (GH-20, GH-01, GH-02) followed the same
  benchmark-first discipline throughout this project: a fix earns its
  place by being benchmarked and evidenced, not patched reactively the
  moment a failure is found — and that discipline applies equally to
  whatever this evaluation set turns up next, if it's grown further.
- It is not a claim that TraceKit "handles real code" in general — 20
  cases, sourced by one person's search session, is a real but small
  sample. Treat these numbers exactly as the benchmark's own numbers
  are treated: evidence, with a stated scope, not a universal
  guarantee.
