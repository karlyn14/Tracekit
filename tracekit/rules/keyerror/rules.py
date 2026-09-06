"""
Rules for KeyError.

Rule inventory (v1, deliberately small — pipeline first, breadth later):
    KEY001 - likely typo in a dict/DataFrame key against known keys
    KEY002 - key exists but with different letter casing (deterministic,
             not edit-distance based — see class docstring for why)
    KEY003 - key exists one level deeper, inside a nested dict
             (deterministic, capped at exactly one level — see
             class docstring for why deeper recursive search is
             deliberately out of scope)
"""

from __future__ import annotations

import re

from typing import Optional

from tracekit.core.context import ExceptionContext
from tracekit.core.rule import MatchResult, Rule

# Tuned against the benchmark, not guessed — see benchmark/README.md
# for the precision/coverage numbers at distance 1 vs 2 vs 3 that
# justified this default.
DEFAULT_MAX_EDIT_DISTANCE = 2


def _levenshtein(a: str, b: str) -> int:
    """Standard DP edit distance. Small strings only (keys), so O(n*m)
    is not a performance concern here."""
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
            curr[j] = min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + cost # substitution
            )
        prev = curr
    return prev[-1]


def _closest(target: str, candidates: list[str]) -> tuple[Optional[str], int, bool]:
    """
    Return (closest_candidate, distance, is_ambiguous).

    is_ambiguous is True when more than one distinct candidate ties
    for the minimum distance — e.g. 'it' is equally distance-1 from
    both 'id' and 'ip'. In that case there is no principled way to
    pick a winner, so the caller should abstain rather than guess.
    This is a real fix, not a threshold tweak: the benchmark showed
    that picking an arbitrary winner among ties produces confident,
    wrong suggestions (see benchmark/README.md, case008).
    """
    best_distance: Optional[int] = None
    best_keys: list[str] = []
    for candidate in candidates:
        d = _levenshtein(target, candidate)
        if best_distance is None or d < best_distance:
            best_distance = d
            best_keys = [candidate]
        elif d == best_distance:
            if candidate not in best_keys:
                best_keys.append(candidate)

    if best_distance is None:
        return None, -1, False

    is_ambiguous = len(best_keys) > 1
    # Deterministic pick when not ambiguous; when ambiguous, the
    # "winner" is never actually used (caller abstains), but we still
    # return a stable value for logging/debugging.
    return best_keys[0], best_distance, is_ambiguous


class KeyErrorCaseMismatchRule(Rule):
    """
    KEY002: the missing key matches an available key exactly, except
    for letter casing (e.g. 'API_KEY' vs 'api_key').

    Deliberately does NOT use edit distance. Case differences aren't a
    "closeness" heuristic — `requested.lower() == candidate.lower()`
    is a deterministic, unambiguous check, so this rule can afford
    much higher confidence than KEY001's fuzzy typo matching. This is
    also why KEY001 can't reliably cover this case on its own: raw
    edit distance grows with string length, so short case-differences
    (e.g. 'Token'/'token', distance 1) happen to sneak under KEY001's
    threshold while longer ones (e.g. 'API_KEY'/'api_key', distance 6)
    don't — see benchmark/README.md for the case that exposed this.
    """

    RULE_ID = "KEY002"
    exception_types = (KeyError,)
    priority = 10  # outranks KEY001 on a tie: case-mismatch is a more
                    # specific, more certain explanation than a fuzzy typo

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        missing_key = _missing_key_from_value(ctx.exc_value)
        if missing_key is None:
            return None

        available = _available_keys_from_source(ctx)
        if not available:
            return None

        missing_lower = missing_key.lower()
        matches_found = [
            k for k in available if k != missing_key and k.lower() == missing_lower
        ]
        if not matches_found:
            return None

        if len(matches_found) > 1:
            # Two available keys that both case-fold to the same
            # string is degenerate/unusual — abstain rather than guess,
            # same principle as KEY001's ambiguity handling.
            return None

        match = matches_found[0]
        return MatchResult(
            confidence=0.95,
            explanation=(
                f"'{missing_key}' differs from '{match}' only by letter casing."
            ),
            evidence=[
                f"Requested key: {missing_key!r}",
                f"Available key: {match!r}",
                "Match type: case-insensitive exact match (deterministic)",
            ],
            fix=f"Use the exact casing: '{match}'",
        )


class KeyErrorNestedSectionRule(Rule):
    """
    KEY003: the missing key exists, but one level deeper, inside a
    nested dict (e.g. `config['host']` fails, but `config['database']`
    is a dict containing `'host'`).

    Deliberately narrow, on purpose:
      - Exactly ONE level of nesting is searched. This is a capability
        boundary, not a limitation to apologize for — recursively
        walking arbitrarily deep structures would produce suggestions
        like "maybe you meant a.b.c.d.host", which stops being a
        confident diagnosis and starts being a guess. A human
        confidently means "this specific key is one level down," not
        "somewhere in this tree."
      - Restricted to plain `dict` values only (see
        `_safe_extract_nested_sections` in context.py) — not
        DataFrame-like or other mapping types, which don't have a
        comparable "section" structure.
      - No edit distance involved: the key must match EXACTLY inside
        the nested dict. This is a structural/positional diagnosis,
        not a lexical one — a different diagnostic strategy from
        KEY001 (fuzzy) and KEY002 (case-normalized exact), not a
        variation of either.

    Ambiguity handling, same philosophy as KEY001: if the missing key
    appears inside MORE THAN ONE nested section, there's no principled
    way to pick a winner, so this rule abstains rather than guess.
    """

    RULE_ID = "KEY003"
    exception_types = (KeyError,)
    priority = 10  # structural match is as specific as KEY002's case match

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        missing_key = _missing_key_from_value(ctx.exc_value)
        if missing_key is None:
            return None

        sections_containing = [
            section
            for section, inner_keys in ctx.nested_sections.items()
            if missing_key in inner_keys
        ]

        if not sections_containing:
            return None

        if len(sections_containing) > 1:
            # Ambiguous: the same key name exists in more than one
            # nested section — abstain rather than guess which one.
            return None

        section = sections_containing[0]
        return MatchResult(
            confidence=0.90,
            explanation=(
                f"'{missing_key}' exists inside '{section}', not at the top level."
            ),
            evidence=[
                f"Requested key: {missing_key!r}",
                f"Nested occurrence: {section}.{missing_key}",
                "Match type: one-level nested key match (deterministic)",
            ],
            fix=f"Use ['{section}']['{missing_key}'] instead of top-level ['{missing_key}']",
        )


class KeyErrorTypoRule(Rule):
    RULE_ID = "KEY001"
    exception_types = (KeyError,)
    priority = 0

    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        missing_key = _missing_key_from_value(ctx.exc_value)
        if missing_key is None:
            return None

        available = _available_keys_from_source(ctx)
        if not available:
            return None

        best_match, best_distance, is_ambiguous = _closest(missing_key, available)
        if best_match is None:
            return None

        if best_distance == 0:
            # Exact match found among "available" candidates means this
            # isn't a typo case at all (e.g. key existed then was
            # deleted) — out of scope for this rule, let it pass.
            return None

        if best_distance > DEFAULT_MAX_EDIT_DISTANCE:
            return None

        if is_ambiguous:
            # More than one candidate ties for closest — e.g. 'it' is
            # equally close to both 'id' and 'ip'. There's no
            # principled way to pick a winner here, so we abstain
            # rather than guess. See benchmark/README.md for the
            # false-positive case that motivated this (v1.1 could
            # instead surface all tied candidates at reduced
            # confidence — deliberately out of scope for now).
            return None

        # Confidence scales down as edit distance grows, and is capped
        # to reflect that this is a heuristic, not certainty.
        confidence = max(0.0, 0.9 - 0.25 * best_distance)

        return MatchResult(
            confidence=confidence,
            explanation=(
                f"'{missing_key}' is not a key — the closest existing "
                f"key is '{best_match}' (edit distance {best_distance})."
            ),
            evidence=[
                f"Requested key: {missing_key!r}",
                f"Closest available key: {best_match!r}",
                f"Edit distance: {best_distance}",
            ],
            fix=f"Check for a typo: '{missing_key}' vs '{best_match}'",
        )


_QUOTED_SUBSTRING_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def _missing_key_from_value(exc_value: BaseException) -> Optional[str]:
    """
    KeyError's .args[0] is normally the missing key itself (the
    overwhelmingly common case, and the only shape most of TraceKit's
    benchmark previously covered). Some libraries instead raise
    KeyError with a full descriptive SENTENCE as args[0], with the
    actual key embedded in quotes — e.g. pandas' `.astype()`
    dtype-mapping check: "Only a column name can be used... 'X' not
    found in columns." Confirmed as a real, external bug via
    evaluation/github/results.csv (GH-20): this caused a silent false
    negative on a real, fixable case-mismatch bug.

    Strategy: use args[0] as-is whenever possible — this preserves
    correct behavior for the common case, INCLUDING real keys that
    happen to contain a space (e.g. {'first name': ...}), which must
    not be broken by whatever detects "this looks like a sentence".
    Only fall back to extracting a quoted substring when args[0]
    itself contains quote characters AND multiple words — a strong
    combined signal of "this is a description with an embedded key",
    not just "this key has a space in it". If extraction finds more
    than one quoted substring, the correct one is ambiguous — abstain
    rather than guess (same ambiguity-averse principle used
    throughout this rule set).
    """
    if not exc_value.args:
        return None
    raw = exc_value.args[0]
    if not isinstance(raw, str):
        return None

    looks_like_a_sentence = (
        (" " in raw) and ("'" in raw or '"' in raw)
    )
    if not looks_like_a_sentence:
        return raw

    matches = _QUOTED_SUBSTRING_RE.findall(raw)
    if len(matches) == 1:
        return matches[0]
    return None


def _available_keys_from_source(ctx: ExceptionContext) -> list[str]:
    """
    Pull candidate keys from ctx.available_keys — the plain-string
    snapshot of dict/DataFrame key names taken at context-creation
    time (see context.py: we never retain the live object, only its
    key names, so this stays memory-safe).

    v1 scope limitation, stated explicitly: if more than one dict-like
    local is in scope, we pool all of their keys together rather than
    trying to determine which variable was actually indexed on the
    failing line. That disambiguation would need matching the AST
    subscript target's name against a local — a reasonable v1.1
    improvement, out of scope for the first slice.
    """
    pooled: list[str] = []
    for keys in ctx.available_keys.values():
        pooled.extend(keys)
    return pooled
