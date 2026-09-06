# GH-02 Failure Analysis

**Stage 7: understand exactly why GH-02 fails, and what a naive fix
would actually cost.** No code, no benchmark changes, no tests — same
discipline as GH-01's Stage 1.

## The failure, precisely

Real bug: [facebookarchive/python-instagram #235](https://github.com/facebookarchive/python-instagram/pull/235).
Live TraceKit output:

```
KEY001: 'data' is not a key — the closest existing key is 'meta' (edit distance 2).
  confidence: 0.4
  evidence: ["Requested key: 'data'", "Closest available key: 'meta'", "Edit distance: 2"]
```

`'data'` is a legitimately, sometimes-absent API field. `'meta'` is a
real, unrelated field that happens to exist in the same response. They
are not typos of each other.

## This is a different kind of failure than GH-01

GH-01 found the *right* pair and stated it with the wrong implied
direction — a presentation problem. GH-02 is more fundamental: `'meta'`
is the wrong match entirely. Confirmed there's no ambiguity being
mishandled — `'meta'` is the single, unambiguous closest candidate
(`'pagination'`, the only other real key in this response, is distance
8 away, nowhere close). The matching logic did exactly what it's
designed to do; it just picked a real but wrong answer.

## Exact mechanical cause

`'data'` and `'meta'` are both 4 characters and share the suffix
`'ta'`. Edit distance 2 means exactly half the characters differ. For
a 4-letter string, KEY001's fixed threshold (`distance <= 2`) allows
up to 50% of the string to differ — a far larger *relative* allowance
than the same absolute threshold gives a longer identifier. This is
the same broad category as the already-documented
`benchmark/README.md` limitation (`FEATURE_X`/`FEATURE_Y`,
`SERVER_HOST`/`SERVER_PORT`) — a fixed absolute threshold applied to
identifiers of different lengths — but GH-02 is real, external
confirmation that it also occurs on short, common English words,
not just longer domain-specific identifiers.

## Quantifying the "obvious" fixes before considering either — both fail

Two threshold-based fixes come to mind immediately. Both were checked
against the real benchmark data (`benchmark/data/*.jsonl`, test split)
rather than assumed to work.

### Attempt 1: raise the confidence-surfacing cutoff

`tracekit/core/analyzer.py`'s `MIN_SURFACED_CONFIDENCE = 0.35` already
exists. GH-02's confidence (0.4) sits only 0.05 above it — tempting to
just raise the cutoff. Since KEY001's confidence formula
(`0.9 - 0.25 * distance`, capped at `DEFAULT_MAX_EDIT_DISTANCE = 2`)
only ever produces exactly two values — 0.65 (distance 1) or 0.4
(distance 2) — raising the cutoff above 0.4 would suppress **every**
distance-2 KEY001 match, not just this one. Measured against the
current benchmark's test split:

| Distance | Genuine false positives | Correctly-diagnosed real cases |
|---|---:|---:|
| 1 | 2 | 8 |
| 2 | 2 | 5 |

Raising the cutoff to silence all distance-2 matches would remove 2 of
4 known false positives — but at the cost of silencing **5 correct,
real diagnoses**, and it wouldn't touch the other 2 false positives at
all (they're at distance 1). A bad trade, quantified, not assumed.

### Attempt 2: use a length-normalized distance instead of an absolute one

Normalizing by string length (`edit_distance / max(len(a), len(b))`)
looked promising at first — it separates GH-02 from the *other*
known false positives cleanly:

| Pair | Distance | Normalized | |
|---|---:|---:|---|
| `data`/`meta` (GH-02) | 2 | **0.50** | false positive |
| `port`/`host` (benchmark negative) | 2 | **0.50** | false positive |
| `FEATURE_Y`/`FEATURE_X` | 1 | 0.11 | false positive |
| `SERVER_PORT`/`SERVER_HOST` | 2 | 0.18 | false positive |
| `ENABLE_CACHED`/`ENABLE_CACHE` | 1 | 0.08 | false positive |

GH-02 and the `port`/`host` case stand out as high-normalized-distance
outliers among the false positives — a normalized threshold (e.g.
reject anything above ~0.3) looks like it would catch exactly these
two and leave the others alone (which it wouldn't fix, but wouldn't
break either).

**Then the decisive counter-example, found by checking the
*correctly-matched* cases at the same normalization, not just the
false positives:**

```
KEY001-037: 'Naem' vs 'Name'  distance=2  normalized=0.50
```

This is one of the project's own original, canonical KEY001 examples
— a genuine, correct typo match — sitting at **exactly the same
normalized distance as GH-02's false positive.** Any normalized
threshold tight enough to reject `data`/`meta` also rejects
`Naem`/`Name`. Short strings don't just make false positives
proportionally more likely — they make false positives and genuine
typos land in the *same* region of normalized-distance space. There
is no threshold, absolute or normalized, that cleanly separates them
using edit distance alone.

## What this means

Both of the "obvious," cheap fixes were checked against real data and
both fail for a quantified, structural reason — not a vague hunch.
This matches the anticipated shape of the problem: **GH-02 may
genuinely require a different signal than edit distance, in either of
its forms, or it may need to remain a documented, accepted
limitation** rather than be forced into a fix that trades away real
diagnoses to chase a prettier number. Which of those two it should be
is a Stage 8 design decision, not decided here.

## What GH-02 is NOT

- It is **not** an ambiguity-handling gap — there's no tie to detect;
  `'meta'` is the unambiguous single closest candidate.
- It is **not** the same mechanism as GH-01 — GH-01's matching was
  correct and only its wording was wrong; GH-02's matching itself
  picked the wrong candidate.
- It is **not** obviously fixable by adjusting either the absolute
  distance threshold or a length-normalized one — both were checked
  against real benchmark data and both have a real, quantified cost
  that includes breaking a genuine, original KEY001 example
  (`Naem`/`Name`).

## Stopping point

This is Stage 7 only: the mechanism is understood, and two
tempting-but-wrong fixes are ruled out with real numbers rather than
speculation. No solution is chosen here. Stage 8 (if there is one)
would need to weigh: pursuing a genuinely new signal (with the same
cost/evidence bar GH-01's Stage 2 applied), or accepting this as a
documented, honest limitation the same way `FEATURE_X`/`FEATURE_Y` and
`SERVER_HOST`/`SERVER_PORT` already are — not chasing a fix just
because a failure exists.
