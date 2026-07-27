"""
demo.py — the 2-3 minute demo flow, runnable as one command.

    python demo.py

Sequence (matches the recommended viva/video structure):
    1. A script crashes — show the normal, unmodified traceback.
    2. Run the same crash through TraceKit — show the diagnosis.
    3. Run the benchmark — show measured precision/coverage/FP rate.
    4. Run the test suite — show it passing.

Each step pauses briefly so it reads well on camera or in person;
pass --fast to skip the pauses (e.g. for CI).
"""

from __future__ import annotations

import subprocess
import sys
import time

import tracekit.rules  # noqa: F401 - registers rules as a side effect
from tracekit.core.analyzer import analyze
from tracekit.output.formatter import format_result

FAST = "--fast" in sys.argv


def pause(seconds: float = 1.2) -> None:
    if not FAST:
        time.sleep(seconds)


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    pause(0.6)


def buggy_script():
    """The exact bug the demo is built around: a realistic typo in a
    dict lookup, the kind every developer hits weekly."""
    api_response = {
        "status": "ok",
        "user_name": "ada_lovelace",
        "created_at": "2024-01-01",
    }
    return api_response["usre_name"]  # typo: should be 'user_name'


def step_1_normal_traceback():
    header("STEP 1 — A normal Python crash (no TraceKit)")
    print("Running buggy_script() the way Python normally reports it:\n")
    pause()
    try:
        buggy_script()
    except Exception as exc:
        import traceback
        print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    print("→ This is all a developer gets by default: WHERE it failed, not WHY.")
    pause(2)


def step_2_tracekit_diagnosis():
    header("STEP 2 — The same crash, diagnosed by TraceKit")
    pause()
    try:
        buggy_script()
    except Exception as exc:
        result = analyze(exc, exc.__traceback__)
        print(format_result(result))
    print("\n→ Same traceback, still shown in full — plus a labeled")
    print("  'likely cause' (never 'root cause'), with visible evidence")
    print("  and a confidence score, so nothing is a black box.")
    pause(2)


def step_3_run_benchmark():
    header("STEP 3 — Benchmark: is this actually reliable, or just a demo?")
    print("Running the full benchmark (84 held-out cases, 3 rules)...\n")
    pause()
    subprocess.run([sys.executable, "-m", "benchmark.run"], check=False)
    print("\n→ Precision, coverage, false-positive rate, and timing are all")
    print("  measured on a held-out test split — not hand-picked examples.")
    pause(2)


def step_4_run_tests():
    header("STEP 4 — Test suite: is the implementation itself solid?")
    print("Running unit tests + property-based fuzz tests...\n")
    pause()
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], check=False)
    print("\n→ Includes ~250 Hypothesis-generated malformed inputs proving")
    print("  TraceKit never crashes while diagnosing a crash.")
    pause(2)


def main():
    step_1_normal_traceback()
    step_2_tracekit_diagnosis()
    step_3_run_benchmark()
    step_4_run_tests()

    header("Done")
    print("Full source, benchmark methodology, and ADRs: see README.md and docs/adr/")


if __name__ == "__main__":
    main()
