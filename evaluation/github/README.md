# Real-World Evaluation — GitHub Issues

**20 real exception examples, sourced from public GitHub issues/PRs,
executed against TraceKit's actual code.** Not a benchmark case set —
these are bugs TraceKit was never designed against, used to answer:
does the tool generalize past its own dataset?

Full methodology: [`methodology.md`](methodology.md). Raw results:
[`results.csv`](results.csv). Run it yourself: `python
evaluation/github/run_evaluation.py`.

## Headline result

**14 fully correct, 4 correct-with-a-stated-caveat, 2 incorrect, out
of 20** (originally 13/4/3 — GH-20 has since been fixed, see below) —
a real number from a small, honestly-sourced sample, not a general
accuracy claim (see the benchmark's own scope disclaimer, which
applies equally here).

| Outcome | Count | Cases |
|---|---:|---|
| Fully correct | 14 | GH-03,04,05,06,07,08,09,12,13,16,17,18,19,20 |
| Correct, immediate cause only | 3 | GH-10, 11, 15 |
| Correct, generic phrasing | 1 | GH-14 |
| **Incorrect** | **2** | **GH-01, GH-02** |

## GH-20 — fixed (was one of the three original failures)

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

## The two remaining failures — the important part

Per the instruction that started this evaluation: *"the failures are
likely to teach us more than the successes."* Each one is a genuine,
distinct finding, not a repeat of an already-documented limitation.

### GH-01 — KEY001 has no notion of which spelling is "correct"

Real bug: [PyCQA/flake8 #668](https://github.com/pycqa/flake8/issues/668).
A caller passed `excetion=all_exc` as a keyword argument; the code
does `kwargs.pop("exception")`. TraceKit correctly found the closest
pair (`exception`/`excetion`, edit distance 1) — but reported **"did
you mean `excetion`?"**, the wrong direction. Following that advice
would mean changing the code to request the *misspelled* key,
perpetuating the bug rather than fixing it. The real fix renames the
typo'd kwarg to the correctly-spelled `exception`.

**Why this happened:** KEY001 measures only string distance between
two keys. It has no way to know that `exception` is a real, standard
English word and `excetion` looks like a typo of it — that requires
some notion of "which spelling is more likely intended," which is a
fundamentally different (and harder) kind of signal than lexical
similarity. This is a genuine, non-obvious limitation the benchmark's
own synthetic cases never surfaced, because every benchmark case was
authored with the "request has the typo" framing baked in by
construction. **Not yet fixed — likely needs a new design approach,
not a KEY001 tweak (see project discussion: this may need actual
semantic/dictionary knowledge, which is a different kind of signal
than anything currently in TraceKit).**

### GH-02 — a confirmed instance of the known KEY001 limitation, found in the wild

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
**Not yet fixed — same underlying limitation as GH-01: lexical
similarity alone cannot distinguish "close enough to be a typo" from
"close enough to be a coincidence."**

### GH-20 — see "GH-20 — fixed" section above

This was originally the third failure in this set. It's covered in
its own section above rather than here, since — unlike GH-01/GH-02 —
it has since been fixed, and the fix's process (benchmark ground truth
→ tests → implementation → re-evaluation) is itself worth keeping
visible as its own story.

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

- GH-01 and GH-02 are not yet fixed. Per the same benchmark-first
  discipline used throughout this project, a fix earns its place by
  being benchmarked, not patched reactively the moment a failure is
  found. GH-20 followed exactly that discipline and is now fixed (see
  above); GH-01/GH-02 remain logged as findings for a future
  rule-review cycle — likely a genuinely new design question (see
  GH-01's note), not a simple tweak.
- It is not a claim that TraceKit "handles real code" in general — 20
  cases, sourced by one person's search session, is a real but small
  sample. Treat these numbers exactly as the benchmark's own numbers
  are treated: evidence, with a stated scope, not a universal
  guarantee.
