"""
Rules for AttributeError.

Rule inventory (in progress — see benchmark/data/attributeerror_cases.jsonl
for ground truth defined ahead of implementation for ATTR003):
    ATTR001 - attribute/method accessed on a None value (deterministic)
    ATTR002 - built-in container API confusion (deterministic lookup;
               see benchmark/README.md "ATTR002 scope boundary" for
               exactly what's in/out of scope)
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
