"""
Loads benchmark cases and executes each one to produce a real
(exc_value, traceback) pair, exactly as would occur in a user's
program — no mocking of ExceptionContext internals.

Dataset format (JSONL, one case per line):
    id:               unique case identifier
    source:           "handwritten" | "stackoverflow" | "github_issue"
                       (kept honest and distinct — see benchmark/README.md
                       for why single-source benchmarks are misleading)
    split:            "train" | "test" — rules must only be designed
                       against "train"; all reported metrics run on
                       "test" only, to avoid dataset leakage.
    expected_rule_id: the RULE_ID that should be the top candidate, or
                       null if NO rule should fire (a negative /
                       adversarial case — used to measure false
                       positive rate, not just coverage).
    code:             a self-contained Python snippet that raises the
                       target exception when exec'd.
"""

from __future__ import annotations

import json
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class BenchmarkCase:
    id: str
    source: str
    split: str
    expected_rule_id: Optional[str]
    code: str
    category: str = "uncategorized"


def load_cases(filename: str) -> list[BenchmarkCase]:
    path = DATA_DIR / filename
    cases = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            cases.append(BenchmarkCase(**raw))
    return cases


def load_all_cases() -> list[BenchmarkCase]:
    """
    Load every `*_cases.jsonl` file in benchmark/data/, so adding a new
    exception family (e.g. attributeerror_cases.jsonl) is purely
    additive — no changes needed here or in run.py. Case IDs must be
    unique across ALL files combined; duplicates are a benchmark
    authoring bug, not something to silently allow.
    """
    all_cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for path in sorted(DATA_DIR.glob("*_cases.jsonl")):
        for case in load_cases(path.name):
            if case.id in seen_ids:
                raise ValueError(
                    f"Duplicate benchmark case id {case.id!r} found in {path.name} "
                    f"— case IDs must be unique across all dataset files."
                )
            seen_ids.add(case.id)
            all_cases.append(case)
    return all_cases


def run_case(case: BenchmarkCase) -> tuple[BaseException, Optional[types.TracebackType]]:
    """
    Execute the case's code in an isolated namespace and capture the
    real exception + traceback it raises. Raises AssertionError if the
    code doesn't actually raise (a broken benchmark case is a bug in
    the benchmark, not something to silently skip).
    """
    namespace: dict = {}
    try:
        exec(case.code, namespace)
    except Exception as exc:
        return exc, exc.__traceback__
    raise AssertionError(f"Case {case.id!r} did not raise an exception as expected")
