"""
Formats an AnalysisResult for terminal output.

Design rule: the raw traceback is ALWAYS shown, in full, unmodified.
Suggestions are additive and clearly labeled as suggestions — never
presented as a replacement for the real traceback, and never phrased
as certainty ("the cause is") rather than a candidate ("likely cause").
"""

from __future__ import annotations

from tracekit.core.analyzer import AnalysisResult


def format_result(result: AnalysisResult) -> str:
    lines = [result.raw_traceback.rstrip("\n")]

    if not result.has_suggestion:
        return "\n".join(lines)

    lines.append("")
    lines.append("--- TraceKit suggestions (not certainty — verify against your code) ---")
    for i, candidate in enumerate(result.candidates, start=1):
        lines.append("")
        lines.append(f"[{candidate.rule_id}] Likely cause (confidence {candidate.confidence:.2f}):")
        lines.append(f"  {candidate.explanation}")
        if candidate.evidence:
            lines.append("  Evidence:")
            for e in candidate.evidence:
                lines.append(f"    - {e}")
        if candidate.fix:
            lines.append(f"  Suggested fix: {candidate.fix}")

    return "\n".join(lines)
