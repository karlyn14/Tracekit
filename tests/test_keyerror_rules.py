import pytest

from tracekit.core.context import ExceptionContext
from tracekit.core.registry import RuleRegistry
from tracekit.core.rule import MatchResult, Rule
from tracekit.rules.keyerror_rules import KeyErrorTypoRule


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


from tracekit.rules.keyerror_rules import KeyErrorCaseMismatchRule, KeyErrorTypoRule
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


from tracekit.rules.keyerror_rules import (
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
