# GH-02 Solution Design

**Stage 8: evaluate candidate signals and choose an approach (or
explicitly decide not to fix GH-02).** Builds on
`docs/design/GH02-failure-analysis.md` (Stage 7). No code, no
benchmark cases, no tests in this document.

## 1. Problem definition

**What KEY001 currently uses**: exactly two strings (`missing_key`,
the closest `available_key`) and their plain Levenshtein edit
distance. Nothing else.

**What it's missing**, per Stage 7: any signal that distinguishes
"these two strings are related by a plausible typo" from "these two
strings are coincidentally close but semantically unrelated." Stage 7
showed this gap can't be closed by adjusting the existing signal's
*threshold* (absolute or length-normalized) — `data`/`meta`
(false positive) and `Naem`/`Name` (genuine typo, one of the
project's own original examples) sit at the *identical* normalized
distance. The missing piece has to be a different kind of
information, or a more accurate model of the same information.

## 2. Candidate signals

### Identifier frequency (bundled reference table)

- **Detects**: rare/uncommon spellings vs. common ones.
- **Misses GH-02 specifically**: `'data'` and `'meta'` are both
  extremely common field names — frequency wouldn't flag either as
  the odd one out. This signal doesn't even apply to this failure's
  shape.
- **Cost**: real, new dependency (bundled table, staleness over time).
- **Evidence**: none collected; would need to be built to test, and
  wouldn't fix this specific case anyway. **Rejected for GH-02.**

### Naming-pattern signals (shared prefix/suffix position, first-letter stability)

- **Detects**: whether the difference sits at the start, middle, or
  end of the string.
- Checked directly: `data`/`meta` differs at the *first* character;
  every genuine typo in the benchmark preserves the first character.
  But `FEATURE_Y`/`FEATURE_X` and `ENABLE_CACHED`/`ENABLE_CACHE` (both
  known false positives) *also* preserve the first character — this
  signal doesn't distinguish them from real typos either.
- **Cost**: cheap, no dependency.
- **Evidence**: overlaps heavily with normalized distance on the
  available examples, without added discriminating power.
  **Rejected — doesn't generalize.**

### Source/target role information

- Not applicable here — that's GH-01's concern (which side is
  correct), not GH-02's (whether a typo relationship exists at all).

### Traceback/context structure (e.g. size of the containing dict)

- Checked directly: `data`/`meta`'s dict has 2 keys; `Naem`/`Name`'s
  dict also has 2 keys. Dict size doesn't separate genuine typos from
  coincidences in the available examples. **Rejected — inconclusive,
  no signal found.**

### Dictionary/English-word evidence ("is this a recognized word")

The natural human intuition: `'data'` and `'meta'` are both real,
complete words; typo'd strings (`'Naem'`, `'excetion'`) usually
aren't. Refined to be directionally safe (doesn't need to know *which*
side is the typo, only whether one exists): **suppress only when BOTH
the missing key and the closest available key are independently valid
words** — if only one side is a recognizable word and the other looks
like gibberish, that's evidence *for* a typo relationship, regardless
of which side is which (sidesteps needing to solve GH-01's
directionality question again).

Checked by hand against every current example: this cleanly separates
`data`/`meta` and `port`/`host` (both sides valid → suppress,
correct) from `Naem`/`Name`, `excetion`/`exception`, `debgu`/`debug`
(only one side valid → keep, correct). It does **not** cleanly handle
`FEATURE_Y`/`FEATURE_X`, `SERVER_HOST`/`SERVER_PORT`,
`ENABLE_CACHED`/`ENABLE_CACHE` — none of these compound, snake_case
identifiers are literal dictionary words as whole strings, so without
additional tokenization logic (splitting on `_`, checking each
component) this signal wouldn't touch those at all.

- **Cost**: a bundled word list (a real, new dependency with
  maintenance/staleness cost — exactly what was flagged as worth
  avoiding without stronger evidence), plus non-trivial tokenization
  logic to handle compound identifiers if the compound cases are ever
  meant to be covered too.
- **Evidence**: solid for the specific `data`/`meta`/`port`/`host`
  shape; no evidence it's worth building for the compound-identifier
  cases, which would need separate work regardless.
- **Verdict: deferred, not rejected** — same treatment GH-01's Stage 2
  gave the frequency-list idea. This is the conceptually "correct"
  fit for the general problem, but the cost isn't yet justified by
  evidence beyond one case, and a cheaper alternative below already
  resolves that one case.

### Combination: transposition-aware edit distance (Damerau-Levenshtein)

Not originally on the candidate list — found while re-examining Stage
7's distance-2 examples directly. Plain Levenshtein treats a
transposition (`'Naem'` vs `'Name'` — swapped adjacent letters) as
**two** substitutions, the same cost as two *unrelated* character
changes. Damerau-Levenshtein counts an adjacent transposition as
**one** edit, distinguishing "one mistake that moved two letters" from
"two independent mistakes."

Computed directly (not assumed) against every case currently in the
benchmark that requires `DEFAULT_MAX_EDIT_DISTANCE = 2` to match:

| Pair | Plain distance | Damerau distance | Is it actually a transposition? |
|---|---:|---:|---|
| `Naem`/`Name` | 2 | **1** | yes |
| `Heigth`/`Height` | 2 | **1** | yes |
| `passwrod`/`password` | 2 | **1** | yes |
| `timestmap`/`timestamp` | 2 | **1** | yes |
| `debgu`/`debug` | 2 | **1** | yes |
| `data`/`meta` (GH-02) | 2 | 2 | no |
| `port`/`host` (known FP) | 2 | 2 | no |
| `SERVER_PORT`/`SERVER_HOST` (known FP) | 2 | 2 | no |

**Every single one of the benchmark's current distance-2 genuine
matches turns out to be a transposition.** None of the known distance-2
false positives are. This means `DEFAULT_MAX_EDIT_DISTANCE` never
actually needed to tolerate "2 independent character changes" — it
needed to tolerate transpositions, which a better distance metric
recognizes as one mistake, not two. Switching to Damerau-Levenshtein
**and correspondingly tightening the threshold to 1** would:
- keep every currently-correct match (all collapse to Damerau distance 1)
- remove `data`/`meta`, `port`/`host`, and `SERVER_HOST`/`SERVER_PORT`
  (all stay at Damerau distance 2, now above the tightened threshold)
- leave `FEATURE_Y`/`FEATURE_X` and `ENABLE_CACHED`/`ENABLE_CACHE`
  unchanged (both already at distance 1, unaffected either way) — not
  fixed, but not worsened, and already a documented, accepted
  limitation predating this cycle.

- **Cost**: near zero. No new dependency, no bundled data, no
  tokenization logic — a well-known, standard algorithm (a small,
  fixed addition to the existing DP table computation), addressing a
  documented and extremely common real typo pattern (adjacent-key
  transposition while typing).
- **Evidence**: complete for the cases checked (every current
  benchmark case requiring distance 2), though **not yet validated
  against the full benchmark** — that's explicitly Stage 10's job, not
  assumed here.

## 3. The honest tension, and the choice

The Damerau-Levenshtein candidate is, by every measured criterion, the
strongest option: real evidence, zero new dependencies, resolves 3 of
4 known false positives including GH-02 itself, with zero measured
cost to any currently-correct match. **It is also, by classification,
still an edit-distance-family metric** — the exact category flagged as
worth moving past rather than re-tuning again.

Worth being precise about why it's a different *kind* of change than
the two Stage 7 already ruled out, not just a third attempt at the
same thing: raising the confidence cutoff and length-normalization
both tried to draw a *cleverer line* through the same, structurally
blind measurement (plain Levenshtein can't see the difference between
a transposition and two unrelated substitutions). Damerau-Levenshtein
instead **fixes the blindness itself** — it's a more accurate model of
what a keyboard typo actually looks like, not a sharper cutoff applied
to an inaccurate one. But it's true that this is still "make the
string-similarity math better" rather than "bring in a new kind of
information," and that distinction was the explicit ask for this
stage.

**Recommendation, not a unilateral decision**: adopt
Damerau-Levenshtein + threshold 1 as the Stage 8 solution for GH-02
specifically, on the strength of the evidence above, while explicitly
logging the dictionary/word-validity signal as deferred future work if
a *contextual* (non-lexical) signal is specifically wanted regardless
of this evidence — the same way the identifier-frequency idea was
deferred, not built, in GH-01's Stage 2. This is a judgment call
between "strongest evidence, imperfect category fit" and "correct
category, unproven cost" — flagged here for confirmation rather than
assumed, given the explicit steer toward contextual signals going in.

## 4. What Stage 9's behavioral contract would need to guarantee

Named now so Stage 9 isn't invented from scratch, contingent on the
above being confirmed:

- Exact scope: only `KeyErrorTypoRule` (`KEY001`)'s distance
  computation and threshold change — `KEY002`, `KEY003`, confidence
  formula shape (still `0.9 - 0.25 * distance`, now only ever
  evaluated at distance 0 or 1), evidence/explanation/fix text
  construction, and every other rule stay untouched.
- A falsifiable prediction, same discipline as GH-01's Stage 3: every
  *currently-correct* KEY001 benchmark case must still match after
  the change (this is the real risk — Stage 10 needs a full benchmark
  sweep, not just the ~5 spot-checked pairs above, since some
  currently-correct distance-2 match not yet examined could turn out
  to NOT be a transposition and would be lost).
- Explicit acknowledgment that `FEATURE_Y`/`FEATURE_X` and
  `ENABLE_CACHED`/`ENABLE_CACHE` remain known, accepted limitations
  after this change — not silently expected to also be fixed.
- A decision on whether `DEFAULT_MAX_EDIT_DISTANCE` becomes 1
  (Damerau) uniformly, or whether some other precise threshold value
  is warranted — checked against the full benchmark sweep, not
  assumed to be exactly 1 from the eight cases examined here.

## Stopping point

Stage 8 ends here: candidate signals evaluated with real evidence, one
recommended with an explicit, unresolved tension flagged rather than
smoothed over, and a named list of what the next stage's contract must
guarantee. No code, no benchmark cases, no tests. Waiting for
confirmation before Stage 9.
