# ATTR003 Design Contract — Attribute Typo Detection

Status: frozen design, no benchmark cases or implementation yet.
This document is the contract benchmark cases will be checked against
— not a summary written after the fact.

## Purpose

Diagnose likely typos in attribute/method names by comparing the
missing attribute against attributes that actually exist on the
object.

**Not** "guess any missing attribute." **Not** "fix all
AttributeErrors." Just typo detection — the same narrow philosophy
that kept ATTR001/ATTR002 maintainable.

## Candidate attribute set

`dir(obj)`, filtered to exclude:
- dunder attributes (`__init__`, `__class__`, ...)
- private/internal names starting with `_`

**Not** limited to `obj.__dict__`. Real attributes frequently come
from inheritance, `@property`, dataclasses, or descriptors, and won't
always appear in `__dict__` — restricting to it would silently miss
the majority of real-world typo cases (e.g. a typo'd property name on
a class that defines it via `@property`).

## Methods are included, not just data attributes

`items.apend(1)` → "did you mean `append`?" is exactly as valid a typo
diagnosis as `user.nmae` → "did you mean `name`?". Python's
`AttributeError` doesn't distinguish attribute access from method
lookup, and neither should this rule — the user isn't thinking "is
this a method," they're thinking "why doesn't this work."

## Interaction with ATTR002 — resolved via confidence ordering, not rule coupling

The stated requirement is that `[].add()` must be diagnosed by ATTR002
("did you mean `.append()`, a list has no `.add()`"), never by ATTR003
("did you mean... `.append()`? edit-distance-based guess").

**Decision: do not make ATTR003 aware of ATTR002.** The core
architecture principle (see main README pipeline diagram) is that
rules never talk to each other — each is evaluated independently and
ranked purely by confidence, then priority, then registration order.
Adding an explicit "don't run if ATTR002 already matched" check would
break that decoupling for one special case, and every future rule pair
would need the same kind of special-casing.

Instead, this is enforced structurally, by construction:
- ATTR002's confidence floor is 0.95 (fixed, deterministic lookup).
- ATTR003's confidence ceiling is 0.88 (heuristic, distance 1 — see
  table below), always strictly below ATTR002's floor.

Whenever both rules happen to fire on the same case, the registry's
existing confidence-based ranking guarantees ATTR002 wins the top
rank without either rule knowing the other exists. If a future
confidence value ever needs to change, this invariant (ATTR002's floor
> ATTR003's ceiling) is the thing to check before merging — noted here
explicitly so it isn't lost.

In practice this rarely even needs to be tested: `_CONTAINER_CONFUSIONS`
entries (`add`, `append` on the wrong container) and genuine typos
(`nmae`, `apend`) are lexically different enough that both rules
firing on the exact same missing-name is an edge case, not the common
path — but the ordering guarantee holds regardless.

## Ambiguity — abstain, not guess (same principle as KEY001)

If the missing name is equidistant from two or more real candidate
attributes (e.g. object has both `.id` and `.ip`, missing name is
`.it`), there is no principled way to pick a winner. **Abstain.**
Exact same philosophy as KEY001's tie-breaking fix — a confident wrong
guess is worse than silence.

## Distance threshold

Conservative: `edit_distance <= 2`. Not "chase every typo" — false
positives are more expensive than a missed diagnosis (same principle
established for KEY001 and reaffirmed for every rule since).

## Confidence mapping

| Situation | Confidence |
|---|---:|
| distance 1 | 0.88 |
| distance 2 | 0.80 |
| ambiguous (tie) | — (abstain, no MatchResult) |

Deliberately below ATTR001 (0.98) and ATTR002 (0.95) — this rule
infers from lexical similarity, it doesn't observe a structural fact.
Also deliberately below KEY001's ceiling of ~0.9 at distance-0-ish
cases, since KEY001 operates on short, flat identifier strings (dict
keys) while attribute names carry additional risk of colliding with
real, unrelated attributes on complex objects — slightly more
conservative confidence reflects that.

## Scope boundary

```text
Supported:
  ✓ missing attribute/method name is within edit distance 2 of
    exactly one real, public (non-dunder, non-underscore-prefixed)
    attribute or method on the object (via dir())

Not supported (out of scope for ATTR003, on purpose):
  ✗ private/internal (_foo) or dunder (__foo__) attributes as candidates
  ✗ ambiguous ties (two+ equally close candidates) — abstain instead
  ✗ NoneType access (ATTR001's job)
  ✗ built-in container API confusion (ATTR002's job — enforced via
    confidence ordering above, not explicit coupling)
  ✗ attributes that don't exist anywhere close (genuine missing
    functionality, not a typo) — no candidate within distance 2 means
    no diagnosis
```

## What happens next

Only after this contract is reviewed and confirmed does benchmark
case-writing start — cases will be checked against these exact rules
(candidate set = filtered `dir()`, threshold = distance ≤2, ambiguity
= abstain, confidence table above), not against evolving intuition
during case-writing.
