"""
RuleRegistry: indexes rules by exception type for fast lookup, and
runs every rule with crash isolation so a broken rule can never take
down the analyzer that's trying to diagnose a crash.

Tie-breaking for equal-confidence candidates is deterministic and
documented (not "arbitrary"):
    1. explicit `priority` (higher wins)
    2. registration order (first-registered wins) as the final,
       fully deterministic tiebreak
"""

from __future__ import annotations

import logging
import time
import warnings
from collections import defaultdict

from tracekit.core.context import ExceptionContext
from tracekit.core.rule import MatchResult, Rule

logger = logging.getLogger("tracekit.registry")


class RuleRegistry:
    def __init__(self) -> None:
        # exception type -> list of (registration_order, rule_instance)
        self._rules_by_type: dict[type[BaseException], list[tuple[int, Rule]]] = (
            defaultdict(list)
        )
        self._seen_ids: set[str] = set()
        self._next_order = 0

    def known_rule_ids(self) -> set[str]:
        """RULE_IDs actually registered right now — used by the
        benchmark to distinguish 'this rule exists and got it wrong'
        from 'this rule is specified in the benchmark but not built
        yet'. The benchmark's ground truth is allowed to reference
        rules ahead of their implementation; this is what lets it do
        so honestly instead of silently penalizing an unbuilt rule."""
        return set(self._seen_ids)

    def register(self, rule: Rule) -> None:
        if rule.RULE_ID in self._seen_ids:
            raise ValueError(f"Duplicate RULE_ID: {rule.RULE_ID!r}")
        self._seen_ids.add(rule.RULE_ID)

        order = self._next_order
        self._next_order += 1
        for exc_type in rule.exception_types:
            self._rules_by_type[exc_type].append((order, rule))

    def rules_for(self, exc_type: type[BaseException]) -> list[Rule]:
        """O(1) dict lookup, not a scan over every registered rule."""
        return [rule for _, rule in self._rules_by_type.get(exc_type, [])]

    def evaluate(
        self,
        ctx: ExceptionContext,
        timing_sink: dict[str, list[float]] | None = None,
    ) -> list[tuple[Rule, MatchResult]]:
        """
        Run every applicable rule against ctx, isolate failures, and
        return (rule, result) pairs sorted by:
            1. confidence, descending
            2. rule.priority, descending
            3. registration order, ascending (first-registered wins ties)

        If timing_sink is provided, appends each rule's individual
        matches() call duration (in milliseconds) to
        timing_sink[rule.RULE_ID] — used by the benchmark to report
        per-rule average/p95 latency, not just an aggregate figure.
        """
        candidates = self._rules_by_type.get(ctx.exc_type, [])
        results: list[tuple[int, Rule, MatchResult]] = []

        for order, rule in candidates:
            start = time.perf_counter()
            try:
                outcome = rule.matches(ctx)
            except Exception as exc:  # noqa: BLE001 - intentional catch-all
                # A rule crashing must never crash TraceKit itself.
                warnings.warn(
                    f"Rule {rule.RULE_ID!r} raised {exc.__class__.__name__} "
                    f"during matches(); skipping this rule. ({exc})",
                    RuntimeWarning,
                    stacklevel=2,
                )
                logger.warning("Rule %s failed: %r", rule.RULE_ID, exc)
                continue
            finally:
                if timing_sink is not None:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    timing_sink.setdefault(rule.RULE_ID, []).append(elapsed_ms)

            if outcome is not None:
                results.append((order, rule, outcome))

        results.sort(key=lambda r: (-r[2].confidence, -r[1].priority, r[0]))
        return [(rule, outcome) for _, rule, outcome in results]


# Module-level default registry. Rules are registered once at import
# time (see rules/__init__.py), before any application threads start
# consuming it, so no locking is required — the registry is
# effectively read-only for the lifetime of the process afterward.
default_registry = RuleRegistry()
