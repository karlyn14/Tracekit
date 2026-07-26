"""
Analyzer: the single entry point that turns a raw exception into an
AnalysisResult. This is intentionally thin — it does not itself decide
anything about causes; it just wires ExceptionContext + RuleRegistry
together and always preserves the original traceback untouched.
"""

from __future__ import annotations

import traceback
import types
from dataclasses import dataclass, field

from tracekit.core.context import ExceptionContext
from tracekit.core.registry import RuleRegistry, default_registry
from tracekit.core.rule import MatchResult, Rule

# Below this, a candidate is considered too weak to be worth surfacing
# as a suggestion. Chosen against benchmark data, not a guess — see
# benchmark/README for the precision/coverage tradeoff at this cutoff.
MIN_SURFACED_CONFIDENCE = 0.35


@dataclass
class Candidate:
    rule_id: str
    confidence: float
    explanation: str
    evidence: list[str]
    fix: str | None = None


@dataclass
class AnalysisResult:
    raw_traceback: str  # always the real, unmodified traceback
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def has_suggestion(self) -> bool:
        return len(self.candidates) > 0


def analyze(
    exc_value: BaseException,
    tb: types.TracebackType | None,
    registry: RuleRegistry = default_registry,
    timing_sink: dict[str, list[float]] | None = None,
) -> AnalysisResult:
    raw_tb = "".join(
        traceback.format_exception(type(exc_value), exc_value, tb)
    )

    ctx = ExceptionContext.from_exception(exc_value, tb)
    ranked = registry.evaluate(ctx, timing_sink=timing_sink)

    candidates = [
        Candidate(
            rule_id=rule.RULE_ID,
            confidence=result.confidence,
            explanation=result.explanation,
            evidence=result.evidence,
            fix=result.fix,
        )
        for rule, result in ranked
        if result.confidence >= MIN_SURFACED_CONFIDENCE
    ]

    return AnalysisResult(raw_traceback=raw_tb, candidates=candidates)
