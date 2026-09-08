# GH-02 Behavioral Contract

**Stage 9: freeze the exact contract Stage 10 onward implements
against.** Builds on `docs/design/GH02-solution-design.md` (Stage 8,
which chose Damerau-Levenshtein + threshold 1). No benchmark cases, no
tests, no code in this document.

## Chosen approach (frozen)

Replace `KeyErrorTypoRule`'s plain Levenshtein distance with
**restricted Damerau-Levenshtein distance (Optimal String Alignment /
OSA variant)** — the same formulation validated with real numbers in
Stage 8: identical to Levenshtein, plus one additional rule: if the
last two characters compared are a transposition of each other
(`a[i] == b[j-1] and a[i-1] == b[j]`), that transposition costs 1 edit
instead of 2. Correspondingly, `DEFAULT_MAX_EDIT_DISTANCE` changes
from `2` to `1`.

## Exact current implementation (the baseline this contract changes)

`tracekit/rules/keyerror/rules.py`:

```python
DEFAULT_MAX_EDIT_DISTANCE = 2

def _levenshtein(a: str, b: str) -> int:
    # standard DP edit distance — insertion, deletion, substitution only
    ...
```

`_levenshtein` is called from `_closest()`, which `KeyErrorTypoRule.matches()`
uses to find the nearest candidate key and detect ties. Nothing else
in the codebase calls this specific function or reads
`DEFAULT_MAX_EDIT_DISTANCE`.

**Important scope note, checked directly, not assumed**: `ATTR003`
(`tracekit/rules/attributeerror/rules.py`) has its **own**, entirely
separate `_levenshtein` function — same name, same signature, but an
independent definition in a different module, with no shared code.
Changing KEY001's copy does not touch ATTR003's at all. This is
explicitly called out because a future reader might reasonably wonder
whether "the Levenshtein fix" affected typo detection everywhere it's
used — it doesn't; this contract is scoped to the one copy inside
`keyerror/rules.py`.

## New implementation (frozen for Stage 10 onward)

```python
DEFAULT_MAX_EDIT_DISTANCE = 1  # was 2

def _levenshtein(a: str, b: str) -> int:
    # same DP table as before, PLUS: if the current and previous
    # characters are a transposition of each other, that transposition
    # costs 1 (not 2) — this is the restricted Damerau-Levenshtein /
    # Optimal String Alignment (OSA) distance.
    ...
```

The function name `_levenshtein` stays as-is (not renamed to
`_damerau_levenshtein`) unless Stage 12 finds a concrete reason to
rename it — not decided here, a minor implementation detail left to
that stage, not a contract term.

## What must NOT change

- `RULE_ID`, `exception_types`, `priority` — unchanged.
- The **confidence formula shape** —
  `max(0.0, 0.9 - 0.25 * best_distance)` — stays exactly as written.
  Per Stage 8's contract point ("confidence behavior should remain
  governed by the existing model unless the evidence requires
  otherwise"): no evidence requires a change, so none is made. The
  **practical effect** is a narrowing, not a formula change — with
  `best_distance` now only ever `1` (distance `0` is already excluded
  by the existing "the missing key isn't actually missing" guard, and
  distance `>1` no longer matches at all), the confidence value KEY001
  ever produces narrows from `{0.65, 0.4}` to just `{0.65}`. This is a
  consequence of the threshold change, not a separate decision.
- The **ambiguity-tie logic in `_closest()`** — unchanged in
  structure. Ties are still detected by comparing candidates at the
  minimum distance found; the only difference is that "distance" now
  means Damerau distance instead of plain Levenshtein distance.
- The **explanation/fix/evidence text construction** (the GH-01 fix)
  — completely unrelated to this change, untouched.
- `KEY002`, `KEY003`, `ATTR001`, `ATTR002`, `ATTR003` — untouched, per
  Stage 8's explicit scope (and see the ATTR003 note above: its
  separate `_levenshtein` copy isn't shared code, so it's untouched
  by construction, not just by restraint).
- `KeyErrorCaseMismatchRule` and `KeyErrorNestedSectionRule` — don't
  use `_levenshtein` or `DEFAULT_MAX_EDIT_DISTANCE` at all (confirmed
  by direct search), so nothing to explicitly preserve there beyond
  "don't touch the file outside `_levenshtein` and the constant."

## Falsifiable predictions for the benchmark stage

Two specific, checkable claims — not vague expectations:

1. **Every currently-correct KEY001 benchmark match must still match
   after this change.** Stage 8 spot-checked 5 distance-2 cases by
   hand; Stage 10 must run this against the **full** benchmark, not
   just those 5, since an unexamined distance-2 correct match that
   *isn't* a transposition would be a real, unacceptable regression —
   this contract does not yet guarantee there isn't one.
2. **`data`/`meta` (GH-02), `port`/`host`, and `SERVER_HOST`/`SERVER_PORT`
   must no longer match** (all three stay at Damerau distance 2, now
   above the tightened threshold of 1).
3. **`FEATURE_Y`/`FEATURE_X` and `ENABLE_CACHED`/`ENABLE_CACHE` are
   explicitly EXPECTED to remain false positives** (both already sit
   at distance 1 under either metric, unaffected by this change) — if
   Stage 10's benchmark run shows them still failing, that is not a
   sign this implementation is broken; it's the documented, accepted
   scope of this specific fix.

If prediction 1 fails for any case, the correct response is to
investigate that specific case (it may reveal the threshold needs to
be something other than exactly 1, or that this approach has a real
gap Stage 8 didn't find) — not to force the benchmark to pass by
loosening the definition of "correct."

## What Stage 10 (benchmark) specifically needs to do

- Run the **entire** existing `KEY001-*` positive benchmark set
  through the new distance function and confirm every one still
  matches — a full sweep, not a sample.
- Add explicit ground truth for the three now-expected-to-be-fixed
  negative cases (`data`/`meta`, `port`/`host`,
  `SERVER_HOST`/`SERVER_PORT`) if they aren't already benchmark
  negatives (check first — `port`/`host` and `SERVER_HOST`/`SERVER_PORT`
  already exist as benchmark cases per Stage 7's analysis; `data`/`meta`
  needs to be added as GH-02's dedicated ground truth case, the same
  way GH-01 got its own).
- Explicitly do **not** add new ground truth expecting
  `FEATURE_Y`/`FEATURE_X` or `ENABLE_CACHED`/`ENABLE_CACHE` to start
  passing — per this contract, they're out of scope and expected to
  remain as-is.

## Stopping point

Stage 9 ends here: the exact algorithm (restricted Damerau-Levenshtein
/ OSA), the exact threshold (1), a complete list of what must not
change (including the non-obvious ATTR003 non-interaction, checked not
assumed), and falsifiable predictions with a stated response if they
fail. Stage 10 — benchmark ground truth — is separate and not started
here.
