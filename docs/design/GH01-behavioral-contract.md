# GH-01 Behavioral Contract

**Stage 3 of the GH-01 cycle: define the exact contract for the
phrasing change Stage 2 selected.** Still no benchmark cases, no
tests, no code — this document is what Stage 4 onward gets checked
against, the same way `docs/design/ATTR003.md` was written before
ATTR003 existed.

## Exact current behavior (the baseline this contract changes)

From `tracekit/rules/keyerror/rules.py`, `KeyErrorTypoRule.matches()`,
verified against the live code, not recalled from memory:

```python
explanation = f"'{missing_key}' is not a key — did you mean '{best_match}'?"
fix = f"Check for a typo: '{missing_key}' vs '{best_match}'"
```

**Precise observation, not made in Stage 1/2**: of these two strings,
`fix` is already reasonably neutral — it names both candidates without
prescribing which one to change. `explanation` is the actual offender
— *"did you mean X?"* directly implies *"you should have written X"*,
which is the specific claim GH-01 showed to be sometimes backwards.
This narrows the contract: **only `explanation` needs to change in
substance; `fix` needs only a small clarifying adjustment**, not a
rewrite.

## New wording (frozen for Stage 4 to implement against)

```python
explanation = f"'{missing_key}' is not a key — the closest existing key is '{best_match}' (edit distance {best_distance})."
fix = f"This looks like a typo on one side: either rename '{best_match}' to '{missing_key}', or change the code to request '{best_match}' instead."
```

- `explanation` now states the fact TraceKit actually knows (these two
  keys are suspiciously close) without implying which one is wrong.
- `fix` now explicitly names both possible directions instead of
  implicitly favoring one.

## Scope of this contract

**Applies to:** `KeyErrorTypoRule` (`KEY001`) only.

**Applies uniformly to every KEY001 match, with no exceptions.**
This follows directly from Stage 2's decision: since no signal was
chosen to distinguish "this looks like the common, correct-direction
case" from "this looks like GH-01's reversed-direction case," there is
no principled basis for hedging only *some* matches. Any conditional
hedging would require exactly the kind of signal Stage 2 explicitly
declined to build. Uniform application is not a compromise — it's the
direct, honest consequence of the Stage 2 decision.

**Does NOT apply to KEY002 or KEY003, in this cycle.** Both have
similarly-phrased, direction-implying `fix` text (`KEY002`: *"Use the
exact casing: 'X'"*; `KEY003`: *"Use ['section']['key']..."*) that
could, in principle, face an analogous problem in some hypothetical
future case. This is worth recording as a real observation — but noting
it and acting on it are different things. Stage 1's analysis was about
a real, evidenced KEY001 failure (GH-01); no equivalent real-world
failure has been observed for KEY002 or KEY003. Extending this contract
to them now, without evidence, is exactly the scope creep the rest of
this project has consistently declined to do (see ADR 0001's rationale
against premature abstraction, and Stage 2's own rejection of
signals with real but unearned cost). If a KEY002/KEY003 case like
GH-01 is ever found, it gets its own Stage 1 analysis, not an
automatic inheritance of this one's conclusion.

## What must NOT change

- `RULE_ID`, `exception_types`, `priority` — unchanged.
- The entire matching algorithm: candidate selection, edit distance
  computation, the `DEFAULT_MAX_EDIT_DISTANCE` threshold, and the
  ambiguity-tie abstention logic — byte-for-byte unchanged. Stage 1
  already established the matching itself is correct.
- **The confidence formula and value** — unchanged
  (`max(0.0, 0.9 - 0.25 * best_distance)`). Confidence measures match
  certainty, which this contract doesn't touch (reaffirming Stage 2's
  rationale #2).
- **The `evidence` list** — unchanged. It already states plain facts
  (`"Requested key: X"`, `"Closest available key: Y"`, `"Edit
  distance: N"`) with no directional claim, so it never had this
  problem in the first place.
- Every other file: `formatter.py`, `cli.py`, `analyzer.py`,
  `registry.py`, `context.py`, and every rule in every other family —
  all unaffected, since only two string-construction lines inside one
  method of one class change.

## Falsifiable prediction for the benchmark stage

Because this changes only string content, never which rule fires or
how candidates are ranked, this contract makes one specific, checkable
prediction for later: **`benchmark/data/keyerror_cases.jsonl`'s
existing precision@1, coverage, and false-positive-rate numbers must
come out byte-for-byte identical before and after this change**, since
those metrics are computed from `expected_rule_id` matches, not
message text. If the benchmark numbers move at all once this is
implemented, that means something in this contract was violated
(most likely: the matching logic was accidentally touched) — a
concrete, falsifiable check, not just an expectation.

## What Stage 4 (benchmark cases) will specifically need to test

Named here so Stage 4 isn't inventing criteria on the spot:

- At least one case in the *reversed-direction* shape GH-01 actually
  has (the available/stored key contains the typo; the missing/
  requested key is the standard spelling) — something no existing
  KEY001 benchmark case currently covers, since all of them were
  authored the other way around (per Stage 1's finding).
- An assertion on the **content of the explanation/fix text itself**
  — not just "a `MatchResult` was returned" — specifically checking
  that no phrase implies a single fix direction (e.g. asserting the
  old `"did you mean '{best_match}'?"` pattern is absent, and both
  candidate names appear in the fix text).
- Re-running the *existing* `KEY001-*` positive benchmark cases
  (the "normal," correct-direction ones) to confirm they still count
  as matches under `expected_rule_id: "KEY001"` — the benchmark
  doesn't grade message wording, so these shouldn't need new cases,
  but it's worth explicitly listing as something to check, not assume.

## Stopping point

Stage 3 ends here: an exact, frozen `explanation`/`fix` wording,
a stated scope (KEY001 only, applied uniformly, KEY002/KEY003
explicitly deferred without evidence), an explicit list of what must
not change, and a falsifiable prediction to verify later. Stage 4 —
writing the actual benchmark cases — is separate and not started here.
