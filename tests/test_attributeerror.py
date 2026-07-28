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

# Deliberately importing classes that do not exist yet — ATTR003's
# import failing IS the expected state until it's implemented.
from tracekit.rules.attributeerror.rules import (
    AttributeErrorContainerConfusionRule,
    AttributeErrorNoneTypeRule,
    AttributeErrorTypoRule,
)


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


# ---------------------------------------------------------------------
# ATTR002: built-in container API confusion — written before the rule
# exists, per benchmark/README.md's ATTR002 scope boundary. Supported:
# str.append(), list.add(), dict.append(), set.append(). Explicitly
# NOT supported: user-defined classes, third-party APIs, attribute
# typos (ATTR003's job), NoneType access (ATTR001's job). Any test
# below asserting `is None` is enforcing that boundary, not just
# checking an edge case.
# ---------------------------------------------------------------------

def test_attr002_fires_on_str_append():
    def trigger():
        return "hello".append("!")

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is not None
    assert "list" in result.explanation.lower()


def test_attr002_fires_on_list_add():
    def trigger():
        return [].add(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is not None
    assert "set" in result.explanation.lower()


def test_attr002_fires_on_dict_append():
    def trigger():
        return {}.append(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is not None
    assert "list" in result.explanation.lower()


def test_attr002_fires_on_set_append():
    def trigger():
        return set().append(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is not None
    assert "list" in result.explanation.lower()


def test_attr002_does_not_fire_on_none():
    """None.append() is ATTR001's territory, not ATTR002's — this is
    the exact cross-family boundary check from the benchmark ground
    truth (ATTR002-005)."""

    def trigger():
        return None.append()

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is None


def test_attr002_does_not_fire_on_user_defined_class():
    """A user-defined class is explicitly out of scope for ATTR002 —
    only the four built-in container types are supported."""

    class Foo:
        pass

    def trigger():
        return Foo().bar()

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is None


def test_attr002_does_not_fire_on_unrecognized_method_name():
    """A missing attribute that isn't one of the specific tracked
    confusion pairs must not fire — ATTR002 is a fixed, curated lookup,
    not a general 'guess what method they meant' rule."""

    def trigger():
        return [].some_totally_unrelated_method()

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result is None


def test_attr002_confidence_matches_specification():
    """Locking in the target confidence (0.95) — deterministic like
    ATTR001, but a fixed lookup table rather than a direct structural
    fact, so pitched slightly below ATTR001's 0.98."""

    def trigger():
        return "hello".append("!")

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    assert result.confidence == 0.95


def test_attr002_evidence_contains_object_type_and_missing_method():
    def trigger():
        return "hello".append("!")

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorContainerConfusionRule().matches(ctx)
    evidence_text = " ".join(result.evidence)
    assert "str" in evidence_text
    assert "append" in evidence_text


def test_registry_isolates_a_crashing_attr002_rule():
    """Same crash-isolation guarantee, exercised against ATTR002's own
    class specifically rather than assuming ATTR001's check covers it."""

    class ExplodingAttr002Rule:
        RULE_ID = "ATTR002_BOOM"
        exception_types = (AttributeError,)
        priority = 0

        def matches(self, ctx):
            raise RuntimeError("broken on purpose")

    registry = RuleRegistry()
    registry.register(ExplodingAttr002Rule())

    def trigger():
        return "hello".append("!")

    ctx = _make_attr_ctx(trigger)

    with pytest.warns(RuntimeWarning):
        results = registry.evaluate(ctx)

    assert results == []


# ---------------------------------------------------------------------
# ATTR003: attribute typo detection — written against the frozen
# design contract in docs/design/ATTR003.md, before the rule exists.
# Candidate set: filtered dir(obj) (public, non-dunder). Threshold:
# edit distance <= 2. Ambiguity: abstain on ties (same principle as
# KEY001). Confidence: 0.88 at distance 1, 0.80 at distance 2 (ADR
# 0004's "strong heuristic" tier). Must never attempt semantic
# correction — only lexically close, real attributes on the object.
# ---------------------------------------------------------------------

def test_attr003_fires_on_method_typo_distance1():
    def trigger():
        items = []
        return items.apend(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is not None
    assert "append" in result.explanation


def test_attr003_fires_on_property_typo_distance1():
    def trigger():
        class Config:
            def __init__(self):
                self.setting = True
        return Config().seting

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is not None
    assert "setting" in result.explanation


def test_attr003_fires_on_attribute_typo_distance2():
    def trigger():
        class User:
            def __init__(self):
                self.name = "Ada"
        return User().nmae

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is not None
    assert "name" in result.explanation
    assert result.confidence == 0.80


def test_attr003_abstains_on_ambiguous_tie():
    """THE most important test in this file, per design review: if
    two real attributes are equally close to the missing name, the
    rule MUST stay silent. A confident wrong guess here is exactly the
    failure mode the whole ambiguity-abstention principle exists to
    prevent (same as KEY001's 'it' vs 'id'/'ip')."""

    def trigger():
        class Obj:
            def __init__(self):
                self.id = 1
                self.ip = "1.2.3.4"
        return Obj().it

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is None


def test_attr003_does_not_fire_when_no_close_candidate():
    def trigger():
        class Server:
            def __init__(self):
                self.host = "x"
                self.port = 80
        return Server().color

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is None


def test_attr003_does_not_fire_on_none():
    """None access is ATTR001's territory — enforced here by ATTR003
    itself declining to consider a None object at all, not by
    inspecting ATTR001 (Rule Independence Invariant, ADR 0004)."""

    def trigger():
        user = None
        return user.name

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is None


def test_attr003_does_not_fire_on_container_confusion_case():
    """[].add(1) is ATTR002's territory. Verified here as an actual
    behavioral outcome (minimum real edit distance from 'add' to any
    list method is 3, above ATTR003's threshold of 2) — not asserted
    via rule coupling, per ADR 0004."""

    def trigger():
        return [].add(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    assert result is None


def test_attr003_confidence_tiers_match_specification():
    def trigger_distance1():
        items = []
        return items.apend(1)

    def trigger_distance2():
        class User:
            def __init__(self):
                self.name = "Ada"
        return User().nmae

    ctx1 = _make_attr_ctx(trigger_distance1)
    ctx2 = _make_attr_ctx(trigger_distance2)

    result1 = AttributeErrorTypoRule().matches(ctx1)
    result2 = AttributeErrorTypoRule().matches(ctx2)

    assert result1.confidence == 0.88
    assert result2.confidence == 0.80


def test_attr003_evidence_contains_type_and_candidate():
    def trigger():
        items = []
        return items.apend(1)

    ctx = _make_attr_ctx(trigger)
    result = AttributeErrorTypoRule().matches(ctx)
    evidence_text = " ".join(result.evidence)
    assert "list" in evidence_text
    assert "apend" in evidence_text
    assert "append" in evidence_text


def test_registry_isolates_a_crashing_attr003_rule():
    class ExplodingAttr003Rule:
        RULE_ID = "ATTR003_BOOM"
        exception_types = (AttributeError,)
        priority = 0

        def matches(self, ctx):
            raise RuntimeError("broken on purpose")

    registry = RuleRegistry()
    registry.register(ExplodingAttr003Rule())

    def trigger():
        items = []
        return items.apend(1)

    ctx = _make_attr_ctx(trigger)

    with pytest.warns(RuntimeWarning):
        results = registry.evaluate(ctx)

    assert results == []
