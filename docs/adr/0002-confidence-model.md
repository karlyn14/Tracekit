# ADR 0002: Confidence Model — Heuristic Scores, Ambiguity as Abstention

## Status
Accepted (v1.0.0)

## Context
Rules need a way to express how sure they are about a diagnosis, and
a way to handle the case where more than one candidate cause looks
equally plausible.

## Decision
Confidence is a float in [0.0, 1.0], hand-set per rule and adjusted
against benchmark data — not statistically derived from a training
process. When a rule finds more than one equally-good candidate (a
tie), it abstains (`returns None`) rather than picking a winner.

## Rationale
Early versions of KEY001 (typo detection) picked an arbitrary winner
on ties — e.g. `'it'` is equally close to both `'id'` and `'ip'`.
Benchmarking this directly (see `benchmark/README.md`) showed it
produced confident, wrong suggestions: a measured false-positive rate
of 33% on one benchmark slice. Changing the rule to abstain on exact
ties dropped that to 0% with no loss in precision or coverage on the
same slice — a controlled before/after comparison, not a guess.

Confidence values themselves remain heuristic (e.g. KEY001 scales
`0.9 - 0.25 * edit_distance`), and this is stated plainly rather than
implied to be statistically calibrated. The benchmark's confidence
calibration report (bucketed accuracy per 0.1-wide confidence range)
is the honest way to check, over time, whether a 0.8-confidence
candidate really is right about 80% of the time.

## Consequences
- "I don't know" is a first-class, deliberate outcome, not a failure
  mode — abstention rate is tracked as its own benchmark metric,
  separate from false positives and misses.
- Confidence is not a calibrated probability in v1; the calibration
  section of the benchmark report exists specifically to surface this
  honestly rather than let confidence values imply more certainty
  than they have evidence for.
- Deterministic rules (KEY002, KEY003) can justifiably use much
  higher confidence values (0.90–0.95) than heuristic rules (KEY001,
  ~0.4–0.65), since there is no equivalent ambiguity risk once they
  match — this is reflected in, and supported by, the measured
  per-rule benchmark results.
