# Real-World Evaluation — GitHub Issues

**20 real exception examples, sourced from public GitHub issues/PRs,
executed against TraceKit's actual code.** Not a benchmark case set —
these are bugs TraceKit was never designed against, used to answer:
does the tool generalize past its own dataset?

Full methodology: [`methodology.md`](methodology.md). Raw results:
[`results.csv`](results.csv). Run it yourself: `python
evaluation/github/run_evaluation.py`.

## Headline result

**15 fully correct, 4 correct-with-a-stated-caveat, 1 incorrect, out
of 20** (originally 13/4/3 — GH-20 and GH-01 have since been fixed,
see below) — a real number from a small, honestly-sourced sample, not
a general accuracy claim (see the benchmark's own scope disclaimer,
which applies equally here).

| Outcome | Count | Cases |
|---|---:|---|
| Fully correct | 15 | GH-01,03,04,05,06,07,08,09,12,13,16,17,18,19,20 |
| Correct, immediate cause only | 3 | GH-10, 11, 15 |
| Correct, generic phrasing | 1 | GH-14 |
| **Incorrect** | **1** | **GH-02** |

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

## The one remaining failure — the important part

Per the instruction that started this evaluation: *"the failures are
likely to teach us more than the successes."*

### GH-02 — a confirmed instance of a known KEY001 limitation, found in the wild

Real bug: [facebookarchive/python-instagram #235](https://github.com/facebookarchive/python-instagram/pull/235).
`'data'` and `'meta'` are both short, common words at edit distance 2
— within KEY001's threshold — but `'data'` is a legitimately,
sometimes-absent API field, not a typo of `'meta'`. TraceKit
confidently suggested "did you mean `meta`?", which is wrong.

This is the *same class* of false positive already documented in
`benchmark/README.md` (the `FEATURE_X`/`FEATURE_Y` case) — but that
was a synthetic, hand-written adversarial example. This is
confirmation that the same failure mode occurs on genuine, unrelated
external code, not just in a benchmark case designed to expose it.
**Not yet fixed — and unlike GH-01, this isn't a directional/wording
problem: KEY001 didn't just misstate its finding, it matched the wrong
pair entirely.** Fixing this would need either a narrower distance
threshold (at real precision/coverage cost — see `benchmark/README.md`'s
documented tradeoff) or a genuinely new signal distinguishing "close
enough to be a typo" from "close enough to be a coincidence," the same
category of harder problem GH-01's Stage 2 design work declined to
build without stronger evidence it's worth the cost. If this failure
mode shows up again in a future real-world evaluation round, that's
the evidence needed to revisit that decision.

### GH-01 and GH-20 — see their own "fixed" sections above

Both were originally recorded as failures here. They're covered in
their own sections above rather than here, since they've since been
fixed, and each fix's process is itself worth keeping visible as its
own story — particularly GH-01's, which took a full multi-stage design
process (four documents in `docs/design/`) specifically to conclude
that the *simplest* available fix (a wording change, not a new
signal source) was the right one.

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

- GH-02 is not yet fixed. Per the same benchmark-first discipline used
  throughout this project, a fix earns its place by being benchmarked,
  not patched reactively the moment a failure is found. GH-20 and
  GH-01 both followed that discipline in full and are now fixed (see
  above); GH-02 remains logged as a finding for a future rule-review
  cycle, since fixing it would trade away real precision/coverage or
  need a genuinely new signal source, not a one-line change.
- It is not a claim that TraceKit "handles real code" in general — 20
  cases, sourced by one person's search session, is a real but small
  sample. Treat these numbers exactly as the benchmark's own numbers
  are treated: evidence, with a stated scope, not a universal
  guarantee.
