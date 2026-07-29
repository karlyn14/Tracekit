"""
tracekit CLI entry point.

Usage:
    tracekit diagnose crash.py         # run the script, diagnose whatever it raises
    tracekit diagnose traceback.txt    # best-effort diagnosis from a pasted traceback

v1 scope, deliberately minimal — one subcommand, two input modes,
plain text output. No JSON output, no watch mode, no config file, no
color, no multi-file batch mode. Add those later if there's evidence
they're needed, not before.
"""

from __future__ import annotations

import argparse
import re
import runpy
import sys
from pathlib import Path
from typing import Optional

import tracekit.rules  # noqa: F401 - registers rules as a side effect
from tracekit.core.analyzer import AnalysisResult, analyze

# Matches the final "ExceptionType: message" line of a standard Python
# traceback, e.g. "KeyError: 'username'" or
# "AttributeError: 'NoneType' object has no attribute 'name'".
_TRACEBACK_LAST_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")

# Only these two are meaningfully reconstructable as real exception
# instances from parsed text right now — matches the two exception
# families TraceKit currently has rules for.
_KNOWN_EXCEPTION_TYPES = {
    "KeyError": KeyError,
    "AttributeError": AttributeError,
}


def _run_python_file(path: Path) -> Optional[tuple[BaseException, object]]:
    """
    Execute the given script (as if run via `python path.py`) and
    capture the first uncaught exception with its REAL traceback —
    live frames intact, so the full rule set (which needs actual
    local variables, dict contents, object types) can work exactly as
    it does when analyzing an exception raised in-process.
    """
    try:
        runpy.run_path(str(path), run_name="__main__")
    except Exception as exc:  # noqa: BLE001 - deliberately broad: diagnose ANY exception the script raises
        return exc, exc.__traceback__
    return None


def _parse_traceback_text(path: Path) -> Optional[tuple[BaseException, None]]:
    """
    Best-effort: extract the exception type + message from the last
    non-blank line of a pasted traceback file.

    Important, honest limitation: this has NO live object state — no
    real dict contents, no real attribute values, no local variables.
    Most TraceKit rules (KEY001-003, ATTR003) need that live state and
    will correctly find nothing to say here — not a bug, a structural
    consequence of the input being static text rather than a live
    exception. ATTR001/ATTR002 also need `.obj`/`.name` on a REAL
    AttributeError raised naturally, which a reconstructed instance
    from parsed text will not have either. For full diagnosis, run the
    actual script with `tracekit diagnose script.py` instead.
    """
    text = path.read_text()
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    match = _TRACEBACK_LAST_LINE_RE.match(lines[-1].strip())
    if not match:
        return None

    exc_type_name, message = match.group(1), match.group(2)
    exc_type = _KNOWN_EXCEPTION_TYPES.get(exc_type_name, Exception)

    # KeyError's message in a traceback is the repr of the key, e.g.
    # "'username'" — strip the quotes so KeyError(...) gets the key
    # itself, not a string containing literal quote characters.
    if exc_type is KeyError and len(message) >= 2 and message[0] == message[-1] and message[0] in "'\"":
        message = message[1:-1]

    try:
        exc_instance = exc_type(message)
    except Exception:
        exc_instance = Exception(message)

    return exc_instance, None


def _print_cli_diagnosis(result: AnalysisResult, raw_text_override: Optional[str] = None) -> None:
    print("TraceKit Diagnosis")
    print()

    if not result.candidates:
        print("No rule matched — no diagnosis available.")
        print()
        print("Raw traceback:")
        print(raw_text_override if raw_text_override is not None else result.raw_traceback)
        return

    top = result.candidates[0]
    print(f"Rule      : {top.rule_id}")
    print(f"Confidence: {top.confidence:.2f}")
    print()
    print("Reason")
    print("------")
    print(top.explanation)
    if top.fix:
        print()
        print("Suggestion")
        print("----------")
        print(top.fix)


def _cmd_diagnose(args: argparse.Namespace) -> int:
    path = Path(args.target)
    if not path.exists():
        print(f"tracekit: no such file: {path}", file=sys.stderr)
        return 1

    if path.suffix == ".py":
        outcome = _run_python_file(path)
        if outcome is None:
            print("Script ran without raising an exception — nothing to diagnose.")
            return 0
        exc, tb = outcome
        raw_text_override = None  # the real, full traceback is already correct here
    else:
        outcome = _parse_traceback_text(path)
        if outcome is None:
            print(
                f"tracekit: could not find a recognizable exception line in {path}",
                file=sys.stderr,
            )
            return 1
        exc, tb = outcome
        # Show the user's ORIGINAL pasted text, not a synthesized
        # reconstruction from parsing — it's more complete (file name,
        # line number, source line) and more honest than re-deriving a
        # one-line approximation of what they already had.
        raw_text_override = path.read_text()

    result = analyze(exc, tb)
    _print_cli_diagnosis(result, raw_text_override=raw_text_override)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracekit", description="Diagnose Python exceptions — likely causes, not certainty."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Diagnose an exception from a Python script or a pasted traceback file.",
    )
    diagnose.add_argument(
        "target",
        help="Path to a .py script to run (full live diagnosis), or a text "
        "file containing a pasted traceback (limited, best-effort diagnosis).",
    )
    diagnose.set_defaults(func=_cmd_diagnose)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
