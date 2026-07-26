"""
Base classes for TraceKit's rule engine.

A Rule inspects an ExceptionContext and, if it recognizes a pattern,
returns a MatchResult describing the likely (NOT "root") cause,
a confidence score, and the concrete evidence that led to that score.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from tracekit.core.context import ExceptionContext


@dataclass
class MatchResult:
    """
    The output of a single rule's analysis.

    confidence: float in [0.0, 1.0]. Not a probability guarantee — a
        relative score used for ranking candidates against each other.
    explanation: one-line, human-readable, phrased as "likely cause",
        never "root cause" (a rule only sees the raise site, not the
        full causal chain that led to it).
    evidence: concrete facts that justify the confidence score, shown
        to the user so the suggestion is never a black box.
    fix: optional short suggestion for how to address it.
    """

    confidence: float
    explanation: str
    evidence: list[str] = field(default_factory=list)
    fix: Optional[str] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )


class Rule(ABC):
    """
    Base class for all diagnostic rules.

    Subclasses MUST define:
        RULE_ID: a short, stable, unique identifier (e.g. "KEY001").
                 Used in output, benchmarks, docs, and bug reports —
                 never rename an existing RULE_ID once released.
        exception_types: tuple of exception classes this rule applies to.

    Subclasses MUST implement `matches`.

    `matches` must be side-effect free and must not raise — the
    registry wraps every call in a try/except and treats an unexpected
    exception from a rule as "no match, log a warning", specifically so
    a broken rule can never crash the very tool that is diagnosing a
    crash.
    """

    RULE_ID: str = ""
    exception_types: tuple[type[BaseException], ...] = ()
    priority: int = 0  # higher runs/ranks first on ties

    @abstractmethod
    def matches(self, ctx: ExceptionContext) -> Optional[MatchResult]:
        """Return a MatchResult if this rule recognizes the pattern, else None."""
        raise NotImplementedError

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Fail fast at class-definition time, not at first use.
        if not cls.RULE_ID:
            raise TypeError(f"{cls.__name__} must define a non-empty RULE_ID")
        if not cls.exception_types:
            raise TypeError(f"{cls.__name__} must define exception_types")
