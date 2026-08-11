# GH-01 Failure Analysis

**Stage 1 of the GH-01 cycle: understand exactly why it fails.**
No design decisions, no benchmark cases, no code in this document —
those are later stages, done separately.

## The failure, precisely

Real bug: [PyCQA/flake8 #668](https://github.com/pycqa/flake8/issues/668).
A caller passes `excetion=all_exc` as a keyword argument; the code
does `kwargs.pop("exception")`, raising `KeyError: 'exception'`.

Live TraceKit output on this exact case:

```
KEY001: 'exception' is not a key — did you mean 'excetion'?
  evidence: ["Requested key: 'exception'", "Closest available key: 'excetion'", "Edit distance: 1"]
```

This is not a crash, not an abstention, and not a case where TraceKit
found nothing — it found the *right pair* at the *right distance* and
still produced advice that, if followed, makes the bug worse: it
implies the fix is to change the code to request `'excetion'` (the
misspelling), which would make the crash go away while permanently
enshrining the typo. The real, merged-in-spirit fix is the opposite:
rename the caller's kwarg from `excetion` to `exception`.

## The exact mechanical cause

`KeyErrorTypoRule.matches()` (`tracekit/rules/keyerror/rules.py`,
`KEY001`) does the following, unconditionally:

1. Take `missing_key` (the key the code asked for — here, `'exception'`).
2. Take `available` (the keys that actually exist — here, the
   `kwargs` dict's real keys, including `'excetion'`).
3. Find the closest `available` key to `missing_key` by edit distance.
4. Report: *"`missing_key` is not a key — did you mean
   `closest_available_key`?"*

Step 4 bakes in a directional assumption: **the request is assumed
wrong, and the available data is assumed correct.** That assumption is
true for every existing KEY001 benchmark case (`benchmark/data/
keyerror_cases.jsonl`) by construction — every positive case was
authored as "dict has the correct key, the *access expression* has the
typo" (e.g. `{'Name': 'Ada'}['Nmae']`). It has never been tested
against the mirror-image scenario: the *data* has the typo and the
*request* is the standard, correct spelling. GH-01 is exactly that
mirror-image scenario, occurring in real code TraceKit was never
designed against — which is precisely why the benchmark never
surfaced it and the external evaluation did.

## Why this can't be fixed by tuning KEY001's existing inputs

`_closest()` (the function computing edit distance) is symmetric:
`distance('exception', 'excetion')` is the same number regardless of
which string is "the request" and which is "the available key." Edit
distance, by itself, contains **no information about which of two
close strings is more likely the intended, correct one.** It only
answers "how different are these two strings," never "which one is
right."

This means the failure is not a case of KEY001's threshold, ambiguity
handling, or confidence formula being miscalibrated — all of those
operate correctly given the inputs they have. The problem is that
**the inputs themselves are insufficient** to answer the question GH-01
requires answering: not "are these two strings close?" (KEY001 already
answers this correctly) but "which of these two strings is the
standard/intended one?" That second question needs a fundamentally
different kind of signal — something outside string-distance
comparison entirely. Candidate signal sources (not evaluated or
chosen here — that's Stage 2):

- A known-word/known-identifier reference (is one candidate a
  recognized standard term and the other not?).
- Frequency information (how common is each spelling, in some
  reference corpus?).
- Cross-reference within the same codebase (does the "wrong-looking"
  side appear correctly spelled elsewhere?).

TraceKit's current architecture has access to none of these — each
`Rule.matches(ctx)` call sees only a single `ExceptionContext`
snapshot of one exception, in isolation (see ADR 0001, ADR 0004). This
is why the earlier discussion flagged that GH-01 may need a **new
design approach**, not a KEY001 parameter tweak: fixing this requires
either a new information source KEY001 doesn't have, or an entirely
different rule with a different scope and different confidence
posture — not a change to the distance threshold or confidence
formula of the existing rule.

## What GH-01 is NOT

To keep the next stage properly scoped, it's worth being explicit
about what this failure is *not*, so a future design doesn't
over-correct:

- It is **not** a false positive in the sense GH-02 is. KEY001 didn't
  hallucinate an unrelated candidate — it found the objectively
  closest real candidate. The problem is entirely in how that finding
  is *interpreted and presented*, not in the matching itself.
- It is **not** evidence that edit-distance matching is broken or
  should be abandoned — it works correctly for the (large) majority of
  real cases already validated (GH-09, and 13 of 20 real-world cases
  overall).
- It is **not** something a confidence-tier reassignment (ADR 0004)
  can resolve on its own, the way the ATTR002/ATTR003 ordering
  question was resolved — that mechanism settles *which of two rules
  should win* when both fire; GH-01 is a single rule producing one
  fact stated with the wrong implied direction, which confidence
  tiering doesn't address.

## Stopping point

This is Stage 1 only. Next stage — **design a solution** — is a
separate, deliberate step: deciding whether the right response is
constraining KEY001's explanation to be direction-neutral (state the
fact without prescribing which side to change), adding a genuinely new
signal source, introducing a new rule with a narrower and more
cautious scope, or something else entirely. Not decided here.
