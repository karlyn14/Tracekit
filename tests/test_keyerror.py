import pytest

from tracekit.core.context import ExceptionContext
from tracekit.core.registry import RuleRegistry
from tracekit.core.rule import MatchResult, Rule
from tracekit.rules.keyerror.rules import KeyErrorTypoRule


def _make_ctx(data: dict, missing_key: str) -> ExceptionContext:
    try:
        data[missing_key]
    except KeyError as exc:
        return ExceptionContext.from_exception(exc, exc.__traceback__)
    raise AssertionError("expected KeyError was not raised")


def test_key001_abstains_on_ambiguous_tie():
    """'it' is equally distance-1 from both 'id' and 'ip' — there's no
    principled winner, so the rule must abstain rather than guess.
    This is the exact false positive the benchmark caught (case008)."""
    ctx = _make_ctx({"id": 1, "ip": "10.0.0.1"}, "it")
    result = KeyErrorTypoRule().matches(ctx)
    assert result is None


from tracekit.rules.keyerror.rules import KeyErrorCaseMismatchRule, KeyErrorTypoRule
from tracekit.core.registry import RuleRegistry


def test_key002_fires_on_case_mismatch_regardless_of_length():
    ctx = _make_ctx({"API_KEY": "xyz"}, "api_key")
    result = KeyErrorCaseMismatchRule().matches(ctx)
    assert result is not None
    assert result.confidence == 0.95
    assert "API_KEY" in result.explanation


def test_key002_does_not_fire_when_no_case_variant_exists():
    ctx = _make_ctx({"host": "localhost"}, "hostname")
    result = KeyErrorCaseMismatchRule().matches(ctx)
    assert result is None


def test_key002_outranks_key001_when_both_could_apply():
    """For a short case-difference like 'Token'/'token' (edit distance
    1), KEY001 could technically also fire — KEY002 should win because
    it's the more specific, deterministic explanation."""
    registry = RuleRegistry()
    registry.register(KeyErrorTypoRule())
    registry.register(KeyErrorCaseMismatchRule())

    ctx = _make_ctx({"Token": "abc123"}, "token")
    ranked = registry.evaluate(ctx)

    assert len(ranked) >= 1
    top_rule, top_result = ranked[0]
    assert top_rule.RULE_ID == "KEY002"


from tracekit.rules.keyerror.rules import (
    KeyErrorCaseMismatchRule,
    KeyErrorNestedSectionRule,
    KeyErrorTypoRule,
)
from tracekit.core.registry import RuleRegistry


def test_key003_fires_on_one_level_nested_key():
    ctx = _make_ctx({"database": {"host": "localhost"}}, "host")
    result = KeyErrorNestedSectionRule().matches(ctx)
    assert result is not None
    assert result.confidence == 0.90
    assert "database" in result.explanation


def test_key003_abstains_when_key_appears_in_multiple_sections():
    ctx = _make_ctx(
        {"database": {"host": "x"}, "cache": {"host": "y"}}, "host"
    )
    result = KeyErrorNestedSectionRule().matches(ctx)
    assert result is None


def test_key003_does_not_fire_when_no_nesting_contains_key():
    ctx = _make_ctx({"host": "localhost"}, "port")
    result = KeyErrorNestedSectionRule().matches(ctx)
    assert result is None


def test_key003_does_not_recurse_past_one_level():
    """A key two levels deep must NOT be found — this is a scope
    boundary, not a bug."""
    ctx = _make_ctx({"a": {"b": {"host": "x"}}}, "host")
    result = KeyErrorNestedSectionRule().matches(ctx)
    assert result is None


def test_key001_fires_on_close_typo():
    ctx = _make_ctx({"Name": "Ada", "Age": 36}, "Nmae")
    result = KeyErrorTypoRule().matches(ctx)
    assert result is not None
    assert "Name" in result.explanation
    assert result.confidence > 0
    assert any("Nmae" in e for e in result.evidence)


def test_key001_does_not_fire_when_no_close_key():
    ctx = _make_ctx({"Alpha": 1, "Beta": 2}, "CompletelyDifferentThing")
    result = KeyErrorTypoRule().matches(ctx)
    assert result is None


def test_key001_does_not_fire_with_no_dict_like_locals():
    # Build a context manually for a KeyError with no dict-like local at all.
    exc = KeyError("orphan_key")
    ctx = ExceptionContext(
        exc_type=KeyError,
        exc_value=exc,
        filename="<test>",
        lineno=1,
        source_line="",
        ast_node=None,
        local_vars={},
        available_keys={},
    )
    result = KeyErrorTypoRule().matches(ctx)
    assert result is None


def test_key001_non_string_key_does_not_crash():
    exc = KeyError(42)  # non-string key, e.g. tuple/int-keyed dict
    ctx = ExceptionContext(
        exc_type=KeyError,
        exc_value=exc,
        filename="<test>",
        lineno=1,
        source_line="",
        ast_node=None,
        local_vars={},
        available_keys={"data": ["a", "b"]},
    )
    result = KeyErrorTypoRule().matches(ctx)
    assert result is None  # non-string keys are out of scope, not a crash


def test_registry_isolates_a_crashing_rule():
    """A rule that raises must never propagate — the registry logs a
    warning and treats it as 'no match', so TraceKit can never crash
    while diagnosing a crash."""

    class ExplodingRule(Rule):
        RULE_ID = "BOOM001"
        exception_types = (KeyError,)

        def matches(self, ctx):
            raise RuntimeError("this rule is broken on purpose")

    registry = RuleRegistry()
    registry.register(ExplodingRule())

    ctx = _make_ctx({"a": 1}, "b")

    with pytest.warns(RuntimeWarning):
        results = registry.evaluate(ctx)

    assert results == []  # crashed rule contributes no candidate, no exception


def test_registry_rejects_duplicate_rule_ids():
    class RuleA(Rule):
        RULE_ID = "DUP001"
        exception_types = (KeyError,)

        def matches(self, ctx):
            return None

    class RuleB(Rule):
        RULE_ID = "DUP001"
        exception_types = (KeyError,)

        def matches(self, ctx):
            return None

    registry = RuleRegistry()
    registry.register(RuleA())
    with pytest.raises(ValueError):
        registry.register(RuleB())


def test_matchresult_confidence_bounds_enforced():
    with pytest.raises(ValueError):
        MatchResult(confidence=1.5, explanation="bad")
    with pytest.raises(ValueError):
        MatchResult(confidence=-0.1, explanation="bad")


# ---------------------------------------------------------------------
# GH-20 fix: KeyError with a sentence-style message, not a bare key.
# Real bug found via evaluation/github/ (results.csv GH-20): pandas'
# .astype() raises KeyError with a full descriptive sentence as
# args[0] ('Only a column name can be used... "CustomerId" not found
# in columns.'), not the bare key 'CustomerId'. Every KeyError rule
# assumed args[0] IS the bare key — written BEFORE the fix, so these
# should currently FAIL against the unfixed implementation.
# ---------------------------------------------------------------------

from tracekit.rules.keyerror.rules import KeyErrorCaseMismatchRule as _KEY002


def _make_ctx_from_trigger(trigger):
    try:
        trigger()
    except KeyError as exc:
        return ExceptionContext.from_exception(exc, exc.__traceback__)
    raise AssertionError("expected KeyError was not raised")


def test_key002_fires_on_sentence_style_pandas_message():
    """The exact GH-20 scenario: a case-mismatch key embedded in a
    full sentence (pandas' .astype() dtype-mapping KeyError), not a
    bare key. KEY002 should extract 'CustomerId' from the sentence and
    match it against the real column 'customerid'."""

    class DF:
        columns = ["customerid", "name"]

    def astype_check(df, key):
        if key not in df.columns:
            raise KeyError(
                f"Only a column name can be used for the key in a dtype "
                f"mappings argument. '{key}' not found in columns."
            )

    def trigger():
        astype_check(DF(), "CustomerId")

    ctx = _make_ctx_from_trigger(trigger)
    result = _KEY002().matches(ctx)
    assert result is not None
    assert "CustomerId" in result.explanation or "customerid" in result.explanation


def test_key001_fires_on_sentence_style_message_generalization():
    """A DIFFERENT sentence-style pandas KeyError than the exact GH-20
    case (different column names, a typo instead of a case mismatch)
    — a generalization check, not a memorized special case."""

    class DF:
        columns = ["timestamp", "value"]

    def astype_check(df, key):
        if key not in df.columns:
            raise KeyError(
                f"Only a column name can be used for the key in a dtype "
                f"mappings argument. '{key}' not found in columns."
            )

    def trigger():
        astype_check(DF(), "timestmap")

    ctx = _make_ctx_from_trigger(trigger)
    result = KeyErrorTypoRule().matches(ctx)
    assert result is not None
    assert "timestamp" in result.explanation


def test_key001_still_fires_on_bare_key_containing_a_space():
    """Regression safety net: a REAL bare key that happens to contain
    a space ('first name'), with no sentence and no quote characters
    involved, must not be broken by whatever heuristic distinguishes
    'this looks like a sentence' from 'this is a bare key with a
    space in it'. This must pass both before AND after the GH-20 fix."""

    def trigger():
        d = {"first name": "Ada"}
        return d["first nsme"]

    ctx = _make_ctx_from_trigger(trigger)
    result = KeyErrorTypoRule().matches(ctx)
    assert result is not None
    assert "first name" in result.explanation


# ---------------------------------------------------------------------
# GH-01 behavioral contract (docs/design/GH01-behavioral-contract.md):
# KEY001's MATCHING is already correct — these tests do not touch or
# re-test the matching/threshold/ambiguity logic. What's wrong is the
# INTERPRETATION: the old explanation text ("did you mean 'X'?")
# asserts a fix direction TraceKit has no basis to assert. Real case:
# PyCQA/flake8 #668 — a caller typo'd a kwarg name ('excetion' instead
# of 'exception'); KEY001 found the right pair at the right distance,
# but told the user to request the MISSPELLED key, which would
# perpetuate the bug rather than fix it.
#
# These tests are RED by design until Stage 6 implements the frozen
# contract: explanation becomes direction-neutral; fix text, matching,
# and confidence are explicitly UNCHANGED (see contract for why 'fix'
# doesn't need to change — it was already direction-neutral).
# ---------------------------------------------------------------------

def test_key001_explanation_is_direction_neutral_on_gh01_exact_case():
    """The exact GH-01 scenario: the DATA has the typo ('excetion' in
    kwargs), the REQUEST is the correct, standard spelling
    ('exception'). The old wording ("did you mean 'excetion'?") would
    tell the user to request the misspelled key — exactly backwards.
    The new explanation must state the fact (these two keys are close)
    without implying which one is correct."""

    def trigger():
        def make_error(**kwargs):
            return kwargs.pop("exception")
        return make_error(excetion=Exception("boom"), plugin="F")

    ctx = _make_ctx_from_trigger(trigger)
    result = KeyErrorTypoRule().matches(ctx)

    assert result is not None
    # The specific old, direction-asserting phrase must be gone.
    assert "did you mean" not in result.explanation.lower()
    # The fact itself — that these two keys are close — must still be
    # stated. Both names should appear somewhere in the explanation.
    assert "exception" in result.explanation
    assert "excetion" in result.explanation
    # The edit distance fact is part of what makes this a stated fact
    # rather than an implied verdict — the contract's new wording
    # includes it explicitly.
    assert "1" in result.explanation  # edit distance is 1


def test_key001_explanation_is_direction_neutral_generalization():
    """A DIFFERENT reversed-direction case (not the memorized GH-01
    values) — the data has 'debgu' (typo), the request 'debug' (the
    correct, standard spelling) is legitimate. Same contract applies."""

    def trigger():
        settings = {"debgu": True, "verbose": False}
        return settings["debug"]

    ctx = _make_ctx_from_trigger(trigger)
    result = KeyErrorTypoRule().matches(ctx)

    assert result is not None
    assert "did you mean" not in result.explanation.lower()
    assert "debug" in result.explanation
    assert "debgu" in result.explanation


def test_key001_fix_text_is_unchanged_by_the_gh01_contract():
    """Per the frozen contract: 'fix' was ALREADY direction-neutral
    ("Check for a typo: 'X' vs 'Y'" never prescribed a direction), so
    Stage 6 must NOT touch it — only 'explanation' changes. This test
    locks the 'fix' string's exact, unchanged format in place so a
    future implementation can't accidentally widen its change beyond
    what the contract allows."""

    def trigger():
        def make_error(**kwargs):
            return kwargs.pop("exception")
        return make_error(excetion=Exception("boom"), plugin="F")

    ctx = _make_ctx_from_trigger(trigger)
    result = KeyErrorTypoRule().matches(ctx)

    assert result is not None
    assert result.fix == "Check for a typo: 'exception' vs 'excetion'"


def test_key001_confidence_is_unaffected_by_the_gh01_contract():
    """Per the frozen contract: confidence measures match certainty,
    which the wording change doesn't touch. Must stay exactly the
    existing formula's value (0.9 - 0.25 * distance) for both the
    exact GH-01 case (distance 1) and the generalization case
    (distance 2)."""

    def trigger_distance1():
        def make_error(**kwargs):
            return kwargs.pop("exception")
        return make_error(excetion=Exception("boom"), plugin="F")

    def trigger_distance2():
        settings = {"debgu": True, "verbose": False}
        return settings["debug"]

    ctx1 = _make_ctx_from_trigger(trigger_distance1)
    ctx2 = _make_ctx_from_trigger(trigger_distance2)

    result1 = KeyErrorTypoRule().matches(ctx1)
    result2 = KeyErrorTypoRule().matches(ctx2)

    assert result1.confidence == 0.9 - 0.25 * 1
    assert result2.confidence == 0.9 - 0.25 * 2
