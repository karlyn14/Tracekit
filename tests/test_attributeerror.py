"""
Unit tests for ATTR001 (NoneType attribute access).

Written BEFORE the rule exists, per the same discipline used for
KEY001-003: benchmark ground truth first, then rule-level unit tests,
then implementation, then benchmark, then accept/reject.

These tests will fail to even collect right now (ImportError) because
`AttributeErrorNoneTypeRule` doesn't exist yet — that's the expected
"red" state of TDD, not a bug in the test file. All other test files
remain green; only this one is red until ATTR001 is implemented.

Design decision baked into these tests, stated here so the eventual
implementation is held to it: ATTR001 should read `exc_value.name` and
`exc_value.obj` directly — both attributes CPython attaches to
AttributeError since Python 3.10 (this project's minimum supported
version) specifically for this kind of diagnostic use. This is a
cleaner, more deterministic source of truth than parsing the
exception's string message, and needs no new ExceptionContext
extraction logic — `ctx.exc_value` already carries it.
"""

from __future__ import annotations

import pytest

from tracekit.core.context import ExceptionContext
from tracekit.core.registry import RuleRegistry
from tracekit.output.formatter import format_result
from tracekit.core.analyzer import AnalysisResult, Candidate

# Deliberately importing a class that does not exist yet — this
# import failing IS the expected state until ATTR001 is implemented.
from tracekit.rules.attributeerror.rules import AttributeErrorNoneTypeRule


def _make_attr_ctx(trigger) -> ExceptionContext:
    try:
        trigger()
    except AttributeError as exc:
        return ExceptionContext.from_exception(exc, exc.__traceback__)
    raise AssertionError("expected AttributeError was not raised")


def test_attr001_fires_on_nonetype_attribute_access():
    def trigger():
        user = None
        return user.name

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result is not None
    assert "None" in result.explanation or "NoneType" in result.explanation


def test_attr001_fires_on_nonetype_method_call():
    """The failing access doesn't have to be a plain attribute read —
    None.append(...) is also an AttributeError on NoneType."""
    def trigger():
        user = None
        return user.append(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result is not None


def test_attr001_fires_when_none_came_from_a_function_return():
    def trigger():
        def get_user():
            return None
        u = get_user()
        return u.read()

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result is not None


def test_attr001_does_not_fire_on_normal_missing_attribute():
    """A genuine AttributeError on a non-None, user-defined object must
    NOT be claimed by ATTR001 — that's a different failure mode
    entirely (see ATTR002/ATTR003 ground truth in the benchmark)."""

    class Foo:
        pass

    def trigger():
        obj = Foo()
        return obj.some_unrelated_attribute

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result is None


def test_attr001_does_not_fire_on_wrong_method_for_type():
    """'hello'.append(...) is a real AttributeError, but the object is
    a str, not None — out of scope for ATTR001 (this is ATTR002's
    ground truth, not ATTR001's)."""

    def trigger():
        text = "hello"
        return text.append("!")

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result is None


def test_attr001_confidence_matches_specification():
    """Locking in the target confidence from the ATTR001 spec (0.98)
    — NoneType attribute access is about as close to deterministic and
    unambiguous as a diagnosis gets, so this should sit near the top
    of TraceKit's confidence range, deliberately higher than KEY001's
    heuristic range and in the same tier as KEY002/KEY003."""

    def trigger():
        user = None
        return user.name

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    assert result.confidence == 0.98


def test_attr001_evidence_contains_type_and_attribute_name():
    def trigger():
        user = None
        return user.name

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorNoneTypeRule().matches(ctx)
    evidence_text = " ".join(result.evidence)
    assert "NoneType" in evidence_text
    assert "name" in evidence_text


def test_attr001_formatter_output_includes_rule_id_and_evidence():
    """End-to-end check that the formatter renders an ATTR001 result
    correctly — same contract as KEY001-003's formatter output."""
    candidate = Candidate(
        rule_id="ATTR001",
        confidence=0.98,
        explanation="'user' is None.",
        evidence=["Object type: NoneType", "Missing attribute: name"],
        fix="Check whether 'user' was ever assigned a non-None value.",
    )
    result = AnalysisResult(raw_traceback="Traceback (most recent call last):\n...\n", candidates=[candidate])
    formatted = format_result(result)
    assert "ATTR001" in formatted
    assert "NoneType" in formatted
    assert "0.98" in formatted


def test_registry_isolates_a_crashing_attributeerror_rule():
    """Crash isolation is a registry-level guarantee already proven
    generically in test_keyerror.py, but this exercises it on a new
    exception_types tuple (AttributeError) for the first time — worth
    a direct check rather than assuming it generalizes."""

    class ExplodingAttrRule:
        RULE_ID = "ATTR_BOOM"
        exception_types = (AttributeError,)
        priority = 0

        def matches(self, ctx):
            raise RuntimeError("broken on purpose")

    registry = RuleRegistry()
    registry.register(ExplodingAttrRule())

    def trigger():
        user = None
        return user.name

    ctx = _make_attr_ctx(trigger)

    with pytest.warns(RuntimeWarning):
        results = registry.evaluate(ctx)

    assert results == []
