# GH-01 Solution Design

**Stage 2 of the GH-01 cycle: design a solution.** Builds directly on
`docs/design/GH01-failure-analysis.md` (Stage 1). No benchmark cases,
no tests, no code in this document — Stage 3 defines exact scope
boundaries; implementation comes after that.

## The question this stage must answer

Stage 1 established: edit distance alone cannot tell TraceKit which of
two close strings (`'exception'` vs `'excetion'`) is the standard,
intended spelling and which is the typo. So:

> **What additional signal can TraceKit use to determine which side of
> an edit-distance pair is likely the typo?**

## Candidate signals considered

| Signal | How it would work | Why it's rejected (or not) |
|---|---|---|
| **Bundled English word list** | Check whether one candidate is a recognized dictionary word and the other isn't | Rejected. Most real identifiers aren't English words at all (`customerid`, `msgstr`, `assertEqual`) — this would only ever fire on a narrow slice of cases, for real cost (bundling and maintaining a word list, a genuine new dependency). Low coverage, real cost. |
| **Bundled common-identifier frequency list** (e.g. "10,000 most common Python identifiers") | Prefer whichever candidate appears in a curated frequency table | Rejected for now. Broader than a plain word list, but still a maintained external artifact with real size/staleness cost, and still fundamentally guesses — a legitimate but unusual identifier (a real, correctly-named project-specific kwarg) would be judged "wrong" just for being uncommon. This is the closest thing to a genuinely new rule/signal source; explicitly deferred as future work, not rejected outright — see "What's deferred" below. |
| **Cross-frame / signature inspection** (e.g. `inspect.signature()` on the function being called, to see if a name is a documented parameter) | Check whether the requested name matches something the surrounding code already expects | Rejected for this stage. Would require capturing more than the single-frame `ExceptionContext` snapshot TraceKit currently takes (a real architecture change, not a rule change — see ADR 0001), and only applies to the narrow `kwargs.pop(...)`-shaped case, not general dict access. Worth remembering as a real option if this failure mode turns out to be common, but it's a bigger step than this fix needs to justify right now. |
| **Direction-neutral phrasing of the existing match** | Keep KEY001's matching exactly as-is (it's already correct — see Stage 1: "the problem is in how the finding is presented, not the matching itself"); change only the explanation/fix text so it states the found pair as a fact instead of asserting one direction | **Chosen.** No new dependency, no architecture change, directly targets the actual documented harm (wrong-direction advice), and is consistent with the project's existing abstention philosophy (ADR 0002: prefer honest uncertainty over confident wrong guesses) applied to *directionality* specifically, not just *whether a match exists at all*. |

## Decision

**Change KEY001's explanation/fix text to state both possible fix
directions instead of asserting one.** This is a phrasing fix to the
existing rule, not a new `RULE_ID` — the matching logic (candidate
selection, edit distance, ambiguity handling, confidence) is already
correct and stays unchanged. Only the `explanation`/`fix` strings in
`MatchResult` change.

Illustrative (not final — exact wording is Stage 3/4's job, checked
against benchmark cases):

> Before: *"'exception' is not a key — did you mean 'excetion'?"*
>
> After: *"'exception' is not a key. The closest existing key is
> 'excetion' (edit distance 1) — this looks like a typo on one side or
> the other. Check whether 'excetion' should be renamed to
> 'exception', or whether the code should request 'excetion' instead."*

## Rationale

1. **It directly fixes the documented harm.** GH-01's failure wasn't
   that TraceKit found the wrong pair — it found the *right* pair. The
   harm was asserting a fix direction it has no basis to assert. Stage
   1 states this explicitly: *"The problem is entirely in how that
   finding is interpreted and presented, not in the matching itself."*
   A phrasing fix addresses exactly that, and nothing more than that.

2. **Confidence is unaffected, correctly.** `confidence` measures "how
   likely is this pair related by typo" — that's still just as certain
   as before (edit distance 1, unambiguous). What was never actually
   certain, and was wrongly presented as if it were, is *which side*
   is correct. Hedging the phrasing doesn't require lowering
   confidence; it requires being honest about what the confidence
   score was actually measuring all along.

3. **It costs nothing architecturally.** No new dependency, no new
   `ExceptionContext` fields, no change to the registry or any other
   rule. Every other rule (KEY002, KEY003, ATTR001-003) is unaffected.

4. **It's consistent with, not a departure from, existing project
   principles**: ADR 0002 established "abstain rather than guess" for
   *whether* to fire at all (KEY001's ambiguous-tie handling). This
   applies the same instinct one level down — to *what the fix implies*
   once the rule does fire — rather than introducing a new mechanism.

## What's deferred, not rejected

The frequency-list signal (row 2 in the table) is a real, larger
future option — a genuinely new capability, not a tweak — if evidence
ever shows this directional-ambiguity failure mode is common enough to
justify the cost of maintaining a bundled reference list. That
decision needs its own evidence (more real-world cases like GH-01),
not speculation now. Recorded here so it isn't lost, not built.

## What Stage 2 does NOT decide

- The exact final wording of the hedged explanation/fix text —
  that's checked against real benchmark cases in Stage 3/4, the same
  way every other rule's wording was refined against evidence, not
  written once and assumed correct.
- Whether this phrasing change should apply to ALL KEY001 matches
  uniformly, or only trigger extra hedging under some condition —
  Stage 3's job to define precisely, as a scope boundary.
- Whether GH-01 will actually be judged "fixed" under the same
  correctness standard used in `evaluation/github/` once this ships —
  that's confirmed empirically at the "re-run 20 real-world cases"
  stage, not assumed here.

## Stopping point

Stage 2 ends here: a chosen direction (hedge the explanation text,
not a new rule, not a new dependency) with rejected alternatives
recorded and reasoned through, not just asserted. Stage 3 — defining
exactly what this change is and isn't allowed to do — is separate and
not started in this document.
