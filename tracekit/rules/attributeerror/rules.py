"""
Rules for AttributeError.

Rule inventory (in progress — see benchmark/data/attributeerror_cases.jsonl
for ground truth defined ahead of implementation for ATTR002/ATTR003):
    ATTR001 - attribute/method accessed on a None value (deterministic)
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
