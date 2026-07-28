"""
Rules for AttributeError.

Rule inventory:
    ATTR001 - attribute/method accessed on a None value (deterministic)
    ATTR002 - built-in container API confusion (deterministic lookup;
               see benchmark/README.md "ATTR002 scope boundary" for
               exactly what's in/out of scope)
    ATTR003 - attribute/method typo detection (heuristic; see
               docs/design/ATTR003.md for the frozen design contract
               this implementation follows exactly — candidate set,
               threshold, ambiguity handling, and confidence tiers
               were all decided before this class was written)
"""

from __future__ import annotations

from typing import Optional

from tracekit.core.context import ExceptionContext
from tracekit.core.rule import MatchResult, Rule


class AttributeErrorNoneTypeRule(Rule):
    """
    ATTR001: the object an attribute/method was accessed on is None.

    Deliberately deterministic, no string parsing: reads
    `exc_value.obj` and `exc_value.name`, both attributes CPython
    attaches to AttributeError since Python 3.10 specifically to
    support tooling like this (see PEP 657 / bpo-38530). This is
    cleaner and more robust than parsing the exception's message
    string (e.g. "'NoneType' object has no attribute 'name'"), which
    would break on any wording change and offers no real benefit here.

    Identifying WHICH variable held the None value is a secondary,
    "nice to have" — not something to guess at if ambiguous. If
    exactly one local in scope is NoneType, name it; if zero or more
    than one, phrase the diagnosis generically. This is not the same
    kind of ambiguity as KEY001's tie-breaking: the fact that the
    object is None is certain either way, only the variable name in
    the explanation is uncertain, so this rule still fires — it just
    doesn't overclaim which variable was responsible.
    """

    RULE_ID = "ATTR001"
    exception_types = (AttributeError,)
    priority = 10  # same deterministic tier as KEY002/KEY003

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        exc = ctx.exc_value
        obj = getattr(exc, "obj", _MISSING)
        attr_name = getattr(exc, "name", None)

        if obj is _MISSING or attr_name is None:
            # Older/unusual AttributeError without these attributes
            # set — nothing to deterministically check, so abstain
            # rather than fall back to fragile string parsing.
            return None

        if obj is not None:
            return None  # not a None-related AttributeError at all

        none_var_names = [
            name for name, (type_name, _repr) in ctx.local_vars.items()
            if type_name == "NoneType"
        ]

        if len(none_var_names) == 1:
            subject = f"'{none_var_names[0]}'"
        else:
            subject = "the object"

        return MatchResult(
            confidence=0.98,
            explanation=f"{subject} is None — it has no attribute {attr_name!r}.",
            evidence=[
                "Exception type: AttributeError",
                "Object type: NoneType",
                f"Missing attribute: {attr_name!r}",
            ],
            fix=(
                "Check whether a function returned None, an earlier "
                "condition failed, or the object was never initialized."
            ),
        )


_MISSING = object()


# (wrong_type_name, missing_method_name) -> suggested_type_name
#
# A fixed, curated lookup table, not an if/elif chain — deliberately
# so that supporting a new confusion pair later (e.g. tuple.add) is a
# single new entry, not a code change to the matching logic. This is
# the exact scope boundary from benchmark/README.md "ATTR002 scope
# boundary": only these four built-in container types, only these
# specific confusion pairs. Anything not in this table falls through
# to `return None` — ATTR002 does not guess at arbitrary AttributeErrors.
_CONTAINER_CONFUSIONS: dict[tuple[str, str], str] = {
    ("str", "append"): "list",
    ("list", "add"): "set",
    ("dict", "append"): "list",
    ("set", "append"): "list",
}


class AttributeErrorContainerConfusionRule(Rule):
    """
    ATTR002: a method was called that doesn't exist on this built-in
    container type because it belongs to a different one (e.g.
    `.append()` — a list method — called on a str, dict, or set).

    Deliberately narrow, via a fixed lookup table
    (`_CONTAINER_CONFUSIONS`) rather than a general "any AttributeError
    on any container-like object" rule. Scope is fixed in
    benchmark/README.md before this class existed:
        Supported:     str.append, list.add, dict.append, set.append
        Not supported:  user-defined classes, third-party APIs,
                        attribute typos (ATTR003), NoneType access
                        (ATTR001)
    Any AttributeError not matching an exact entry in the table simply
    isn't claimed by this rule — that's the boundary working as
    intended, not a gap to patch by adding more guessing.

    Confidence is 0.95 — deterministic like ATTR001, but pitched
    slightly below its 0.98 because this rule's certainty rests on a
    fixed, curated table matching known confusion pairs, rather than
    a direct structural fact like "this object literally is None".
    """

    RULE_ID = "ATTR002"
    exception_types = (AttributeError,)
    priority = 10  # same deterministic tier as ATTR001/KEY002/KEY003

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        exc = ctx.exc_value
        obj = getattr(exc, "obj", _MISSING)
        attr_name = getattr(exc, "name", None)

        if obj is _MISSING or attr_name is None:
            return None

        if obj is None:
            return None  # ATTR001's territory, not ATTR002's

        obj_type_name = type(obj).__name__
        suggested_type = _CONTAINER_CONFUSIONS.get((obj_type_name, attr_name))

        if suggested_type is None:
            return None  # not a recognized confusion pair — out of scope

        return MatchResult(
            confidence=0.95,
            explanation=(
                f"'{attr_name}' is not a method of {obj_type_name} — "
                f"did you mean to use a {suggested_type}?"
            ),
            evidence=[
                "Exception type: AttributeError",
                f"Object type: {obj_type_name}",
                f"Missing method: {attr_name!r}",
                f"{attr_name!r} exists on: {suggested_type}",
            ],
            fix=f"Check whether you intended a {suggested_type} instead of a {obj_type_name}.",
        )


def _levenshtein(a: str, b: str) -> int:
    """Standard DP edit distance — small strings (attribute names),
    so O(n*m) is not a performance concern."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


# Per docs/design/ATTR003.md: conservative, fixed threshold — not
# "chase every typo". Confidence tiers below match ADR 0004's "strong
# heuristic" range (0.80-0.90) exactly as specified, not tuned by feel.
_MAX_EDIT_DISTANCE = 2
_CONFIDENCE_BY_DISTANCE = {1: 0.88, 2: 0.80}


class AttributeErrorTypoRule(Rule):
    """
    ATTR003: the missing attribute/method name is a likely typo of a
    real attribute/method that exists on the object.

    Implementation follows docs/design/ATTR003.md exactly — see that
    document for the full rationale behind each decision below:

    - Candidate set: `dir(obj)`, filtered to exclude dunder and
      private (`_`-prefixed) names — NOT limited to `obj.__dict__`,
      since real attributes often come from inheritance, `@property`,
      dataclasses, or descriptors.
    - Methods are included, same as data attributes — Python's
      AttributeError doesn't distinguish them and neither does this
      rule.
    - Ambiguity: if the missing name is equidistant from two or more
      real candidates, abstain — same principle as KEY001's tie
      handling. A confident wrong guess is worse than silence.
    - Threshold: edit distance <= 2, conservative by design.
    - Confidence: 0.88 at distance 1, 0.80 at distance 2 — ADR 0004's
      "strong heuristic" tier, deliberately below ATTR001 (0.98) and
      ATTR002 (0.95) since this rule infers from lexical similarity
      rather than observing a structural fact.
    - Does NOT attempt semantic correction: only ever suggests
      attributes that already exist on the object, never a
      conceptually related but lexically distant API.
    - Never fires on `None` (ATTR001's territory) or on cases better
      explained by ATTR002 (built-in container confusion) — the
      latter is enforced structurally via the confidence tiers (ADR
      0004's Rule Independence Invariant), not by this rule inspecting
      ATTR002's behavior.
    """

    RULE_ID = "ATTR003"
    exception_types = (AttributeError,)
    priority = 0  # heuristic tier, same as KEY001

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        exc = ctx.exc_value
        obj = getattr(exc, "obj", _MISSING)
        attr_name = getattr(exc, "name", None)

        if obj is _MISSING or attr_name is None:
            return None

        if obj is None:
            return None  # ATTR001's territory, not ATTR003's

        candidates = [name for name in dir(obj) if not name.startswith("_")]
        if not candidates:
            return None

        best_distance: Optional[int] = None
        best_names: list[str] = []
        for name in candidates:
            d = _levenshtein(attr_name, name)
            if best_distance is None or d < best_distance:
                best_distance = d
                best_names = [name]
            elif d == best_distance and name not in best_names:
                best_names.append(name)

        if best_distance is None or best_distance == 0:
            return None  # no candidates, or the "missing" name somehow exists

        if best_distance > _MAX_EDIT_DISTANCE:
            return None  # no candidate close enough — not a typo, genuinely missing

        if len(best_names) > 1:
            return None  # ambiguous tie — abstain, do not guess

        candidate = best_names[0]
        confidence = _CONFIDENCE_BY_DISTANCE[best_distance]
        obj_type_name = type(obj).__name__

        return MatchResult(
            confidence=confidence,
            explanation=f"'{attr_name}' is not an attribute — did you mean '{candidate}'?",
            evidence=[
                "Exception type: AttributeError",
                f"Object type: {obj_type_name}",
                f"Missing attribute: {attr_name!r}",
                f"Closest existing attribute: {candidate!r}",
                f"Edit distance: {best_distance}",
            ],
            fix=f"Check for a typo: {attr_name!r} vs {candidate!r}",
        )
