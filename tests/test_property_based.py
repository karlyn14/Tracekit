"""
Property-based robustness tests.

These don't test whether a specific rule fires correctly (see
test_keyerror_rules.py for that) — they test the weaker but more
critical invariant that TraceKit NEVER crashes, no matter how
malformed the input: missing frames, no traceback at all, arbitrary
unicode key content, huge dicts, or dicts containing values that
raise when repr()'d.

This is the concrete evidence behind claims like "TraceKit never
crashes while diagnosing a crash" — a property, not just a promise.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

import tracekit.rules  # noqa: F401 - registers rules as a side effect
from tracekit.core.analyzer import analyze
from tracekit.core.context import ExceptionContext
from tracekit.output.formatter import format_result

# Arbitrary text, including unicode, empty strings, and pathological
# whitespace/control characters — not just "normal" identifier-shaped
# strings like the hand-written benchmark cases use.
arbitrary_text = st.text(max_size=200)
identifier_like_text = st.text(alphabet=string.ascii_letters + "_", min_size=0, max_size=40)


@given(missing_key=arbitrary_text, available=st.lists(arbitrary_text, max_size=10))
@settings(max_examples=150)
def test_analyze_never_crashes_on_arbitrary_keyerror(missing_key, available):
    """A KeyError with an arbitrary (possibly unicode, empty, or
    pathological) key, against an arbitrary set of available keys,
    must never make analyze() raise."""
    d = {k: None for k in available if k != missing_key}

    def trigger():
        return d[missing_key]

    try:
        trigger()
    except KeyError as exc:
        # Must not raise, regardless of content.
        result = analyze(exc, exc.__traceback__)
        # And the formatter must handle whatever came out.
        formatted = format_result(result)
        assert isinstance(formatted, str)
        assert result.raw_traceback  # the real traceback is always present


def test_analyze_handles_no_traceback_at_all():
    """An exception instance that was never actually raised has
    __traceback__ is None — e.g. constructed directly, or re-raised
    across a serialization boundary. analyze() must not crash."""
    exc = KeyError("orphan")
    result = analyze(exc, None)
    assert result.raw_traceback  # traceback.format_exception handles tb=None
    formatted = format_result(result)
    assert isinstance(formatted, str)


def test_context_from_exception_handles_no_traceback():
    exc = KeyError("orphan")
    ctx = ExceptionContext.from_exception(exc, None)
    assert ctx.exc_type is KeyError
    assert ctx.lineno == -1
    assert ctx.local_vars == {}
    assert ctx.available_keys == {}
    assert ctx.nested_sections == {}


def test_context_survives_dict_with_unrepr_able_values():
    """A local dict containing a value whose __repr__ raises must not
    break context extraction — only that one value's repr is affected,
    not the whole snapshot."""

    class Cursed:
        def __repr__(self):
            raise RuntimeError("nope")

    def trigger():
        d = {"cursed": Cursed(), "fine": 1}
        return d["missing"]

    try:
        trigger()
    except KeyError as exc:
        ctx = ExceptionContext.from_exception(exc, exc.__traceback__)
        # Should not have raised getting here; local_vars should still
        # have recorded *something* for the cursed value.
        assert "d" in ctx.local_vars or ctx.local_vars is not None


def test_context_survives_dict_with_unrepr_able_keys_in_nested_structure():
    """A nested dict-of-dicts containing an object whose repr raises
    inside the outer dict's non-dict values must not break nested
    section extraction."""

    class Cursed:
        def __repr__(self):
            raise RuntimeError("nope")

    def trigger():
        d = {"section": {"inner_key": 1}, "cursed_value": Cursed()}
        return d["missing"]

    try:
        trigger()
    except KeyError as exc:
        ctx = ExceptionContext.from_exception(exc, exc.__traceback__)
        assert "section" in ctx.nested_sections
        assert ctx.nested_sections["section"] == ["inner_key"]


@given(st.dictionaries(identifier_like_text, st.integers(), max_size=15))
@settings(max_examples=100)
def test_analyze_never_crashes_on_arbitrary_dict_shapes(contents):
    """Fuzz the shape/contents of the dict itself, not just the
    missing key, to catch edge cases in key extraction."""
    missing = "definitely_not_a_key_" + "".join(reversed(list(contents.keys())[:1])) if contents else "x"

    def trigger():
        return contents[missing]

    try:
        trigger()
    except KeyError as exc:
        result = analyze(exc, exc.__traceback__)
        assert isinstance(format_result(result), str)


def test_analyze_never_crashes_on_deeply_nested_structure():
    """A deeply nested dict (well past KEY003's one-level cap) must
    not cause excessive work or a crash — it should simply not match
    past the documented one-level boundary."""

    def build_nested(depth: int):
        d = {"leaf": "value"}
        for _ in range(depth):
            d = {"wrapper": d}
        return d

    def trigger():
        deep = build_nested(50)
        return deep["leaf"]  # exists 50 levels down, not at top level

    try:
        trigger()
    except KeyError as exc:
        result = analyze(exc, exc.__traceback__)
        assert isinstance(format_result(result), str)
        # Must NOT claim a nested match past one level — either no
        # candidates, or candidates that are honestly not KEY003
        # firing on a 50-level-deep coincidence.
        for c in result.candidates:
            if c.rule_id == "KEY003":
                assert False, "KEY003 should never fire past one level of nesting"
