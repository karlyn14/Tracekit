"""
Benchmark runner.

Usage:
    python benchmark/run.py

Reports, on the TEST split only (rules are designed against TRAIN,
never tuned against TEST — see benchmark/README.md):
    - Precision@1: of cases where a rule fired, was the top candidate
      the expected one?
    - Precision@3: was the expected rule anywhere in the top 3?
    - Coverage: fraction of positive cases (expected_rule_id is not
      null) where the correct rule fired at all, at any rank.
    - False positive rate: of NEGATIVE cases (expected_rule_id is
      null, meaning no rule should fire), what fraction had TraceKit
      confidently produce a candidate anyway? This is the metric a
      benchmark full of only positive examples would never reveal.
    - Confidence calibration: for candidates in each 0.1-wide
      confidence bucket, what fraction were actually correct? (Only
      meaningful once there's enough data — flagged as low-N when
      thin.)
    - Average analysis time per case.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import tracekit.rules  # noqa: F401 - registers rules as a side effect
from tracekit.core.analyzer import analyze
from tracekit.core.registry import default_registry
from benchmark.dataset import BenchmarkCase, load_all_cases, run_case

TOP_K_FOR_PRECISION_AT_K = 3
CALIBRATION_BUCKET_WIDTH = 0.1


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


RESULTS_DIR = Path(__file__).parent / "results"


class _Tee:
    """Writes to both real stdout and an in-memory buffer, so the
    console output and the saved transcript are guaranteed identical."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _json_safe_stats(stats: dict) -> dict:
    """Strip non-JSON-serializable bits (booleans in calibration lists
    are fine, but keep this explicit and simple rather than fragile)."""
    return {
        "n_cases": stats["n_cases"],
        "total_positive": stats["total_positive"],
        "total_negative": stats["total_negative"],
        "matched": stats["matched"],
        "abstained": stats["abstained"],
        "abstention_rate": stats["abstention_rate"],
        "precision_at_1": stats["precision_at_1"],
        "precision_at_k": stats["precision_at_k"],
        "coverage": stats["coverage"],
        "false_positive_rate": stats["false_positive_rate"],
        "avg_time_ms": stats["avg_time_ms"],
        "rule_stats": {
            rule_id: {
                "fired": rs["fired"],
                "correct": rs["correct"],
                "false_positive": rs["false_positive"],
                "missed": rs["missed"],
                "avg_confidence": (
                    sum(rs["confidences"]) / len(rs["confidences"])
                    if rs["confidences"] else None
                ),
            }
            for rule_id, rs in stats["rule_stats"].items()
        },
    }


def summarize_ground_truth(all_cases: list[BenchmarkCase], known_ids: set[str]) -> dict[str, dict]:
    """
    Count train/test cases for every expected_rule_id that isn't
    registered yet, across the FULL dataset — not just the test
    split. This is the truthful picture: a rule can have ground truth
    cases entirely in train (not yet reportable via execution
    results), entirely in test, or both. The report should reflect
    that reality rather than the dataset being reshaped to make a
    report section look complete.
    """
    counts: dict[str, dict] = defaultdict(lambda: {"train": 0, "test": 0})
    for case in all_cases:
        if case.expected_rule_id and case.expected_rule_id not in known_ids:
            counts[case.expected_rule_id][case.split] += 1
    return dict(counts)


def print_ground_truth_summary(counts: dict) -> None:
    if not counts:
        return
    print("Ground-truth rules (specified in benchmark, not yet implemented)")
    for rule_id in sorted(counts):
        c = counts[rule_id]
        print(f"  {rule_id}")
        print(f"    Train: {c['train']}")
        print(f"    Test : {c['test']}")
        print(f"    Implemented: No")
    print()


def evaluate_pending_test_detail(cases: list[BenchmarkCase]) -> list[dict]:
    """
    For pending-rule cases that DO have test-split representation,
    run them and show exactly what (if anything) fired — useful
    detail beyond the summary counts above. Rules with zero test-split
    cases simply won't appear here, which is accurate, not a bug.
    """
    detail = []
    for case in cases:
        exc_value, tb = run_case(case)
        result = analyze(exc_value, tb)
        candidate_ids = [c.rule_id for c in result.candidates]
        detail.append(
            {
                "id": case.id,
                "expected": case.expected_rule_id,
                "observed": candidate_ids,
                "other_rule_fired": bool(candidate_ids),
            }
        )
    return detail


def print_pending_test_detail(pending: list[dict]) -> None:
    if not pending:
        return
    print("Pending-rule test-split observations")
    by_rule: dict[str, list[dict]] = defaultdict(list)
    for p in pending:
        by_rule[p["expected"]].append(p)
    for rule_id in sorted(by_rule):
        for p in by_rule[rule_id]:
            status = (
                f"unexpectedly matched by {p['observed']}" if p["other_rule_fired"] else "no rule fired (expected)"
            )
            print(f"  {p['id']}: expected {p['expected']}, observed {p['observed'] or 'None'} — {status}")
    print()


def evaluate_split(cases: list[BenchmarkCase]) -> dict:
    total_positive = 0
    total_negative = 0

    hits_at_1 = 0
    hits_at_k = 0
    covered = 0  # correct rule appeared at any rank
    false_positives = 0  # negative case, but something fired anyway
    abstained = 0  # nothing fired at all, positive or negative case

    calibration_buckets: dict[int, list[bool]] = defaultdict(list)
    total_time = 0.0
    rule_timings: dict[str, list[float]] = defaultdict(list)

    # Per-rule breakdown — once there are multiple rules, this is what
    # answers "which rule is responsible for most false positives"
    # without hunting through the dataset by hand.
    rule_stats: dict[str, dict] = defaultdict(
        lambda: {"fired": 0, "correct": 0, "false_positive": 0, "missed": 0, "confidences": []}
    )

    per_case_detail = []

    for case in cases:
        exc_value, tb = run_case(case)

        start = time.perf_counter()
        result = analyze(exc_value, tb, timing_sink=rule_timings)
        elapsed = time.perf_counter() - start
        total_time += elapsed

        candidate_ids = [c.rule_id for c in result.candidates]
        is_positive = case.expected_rule_id is not None

        if not candidate_ids:
            abstained += 1

        if is_positive:
            total_positive += 1
            if candidate_ids and candidate_ids[0] == case.expected_rule_id:
                hits_at_1 += 1
            if case.expected_rule_id in candidate_ids[:TOP_K_FOR_PRECISION_AT_K]:
                hits_at_k += 1
            if case.expected_rule_id in candidate_ids:
                covered += 1
            else:
                rule_stats[case.expected_rule_id]["missed"] += 1
        else:
            total_negative += 1
            if result.has_suggestion:
                false_positives += 1

        for c in result.candidates:
            rs = rule_stats[c.rule_id]
            rs["fired"] += 1
            rs["confidences"].append(c.confidence)
            if is_positive and c.rule_id == case.expected_rule_id:
                rs["correct"] += 1
            if not is_positive:
                rs["false_positive"] += 1

        for c in result.candidates:
            bucket = int(c.confidence * 10)  # 0..9 -> 0.0-0.1, ..., 0.9-1.0
            correct = is_positive and c.rule_id == case.expected_rule_id
            calibration_buckets[bucket].append(correct)

        per_case_detail.append(
            {
                "id": case.id,
                "source": case.source,
                "expected": case.expected_rule_id,
                "got": candidate_ids,
                "correct_at_1": (
                    is_positive and candidate_ids and candidate_ids[0] == case.expected_rule_id
                ),
                "false_positive": (not is_positive) and result.has_suggestion,
            }
        )

    n_cases = len(cases)
    return {
        "n_cases": n_cases,
        "total_positive": total_positive,
        "total_negative": total_negative,
        "matched": n_cases - abstained,
        "abstained": abstained,
        "abstention_rate": abstained / n_cases if n_cases else float("nan"),
        "precision_at_1": hits_at_1 / total_positive if total_positive else float("nan"),
        "precision_at_k": hits_at_k / total_positive if total_positive else float("nan"),
        "coverage": covered / total_positive if total_positive else float("nan"),
        "false_positive_rate": (
            false_positives / total_negative if total_negative else float("nan")
        ),
        "avg_time_ms": (total_time / n_cases * 1000) if n_cases else float("nan"),
        "calibration": calibration_buckets,
        "rule_stats": dict(rule_stats),
        "rule_timings": dict(rule_timings),
        "detail": per_case_detail,
    }


def print_report(stats: dict, split_name: str) -> None:
    print(f"=== TraceKit Benchmark — split: {split_name} ===")
    print(f"Cases: {stats['n_cases']} "
          f"({stats['total_positive']} positive, {stats['total_negative']} negative)")
    print(f"Matched:             {stats['matched']}")
    print(f"Abstained:           {stats['abstained']}")
    print(f"Abstention rate:     {stats['abstention_rate']:.1%}")
    print(f"Precision@1:         {stats['precision_at_1']:.0%}")
    print(f"Precision@{TOP_K_FOR_PRECISION_AT_K}:         {stats['precision_at_k']:.0%}")
    print(f"Coverage:            {stats['coverage']:.0%}")
    print(f"False positive rate: {stats['false_positive_rate']:.0%}")
    print(f"Avg analysis time:   {stats['avg_time_ms']:.2f} ms")
    print()
    print("Confidence calibration (bucket -> observed accuracy, n):")
    for bucket in sorted(stats["calibration"]):
        outcomes = stats["calibration"][bucket]
        low = bucket / 10
        high = low + CALIBRATION_BUCKET_WIDTH
        acc = sum(outcomes) / len(outcomes) if outcomes else float("nan")
        flag = "  (low N, indicative only)" if len(outcomes) < 5 else ""
        print(f"  [{low:.1f}-{high:.1f}): accuracy={acc:.0%}  n={len(outcomes)}{flag}")
    print()

    print("Rule statistics")
    for rule_id in sorted(stats["rule_stats"]):
        rs = stats["rule_stats"][rule_id]
        avg_conf = (
            sum(rs["confidences"]) / len(rs["confidences"]) if rs["confidences"] else float("nan")
        )
        print(f"  {rule_id}")
        print(f"    Fired:            {rs['fired']}")
        print(f"    Correct:          {rs['correct']}")
        print(f"    False positives:  {rs['false_positive']}")
        print(f"    Missed:           {rs['missed']}  (expected to fire, didn't)")
        print(f"    Avg confidence:   {avg_conf:.2f}")
        timings = stats["rule_timings"].get(rule_id, [])
        if timings:
            avg_t = sum(timings) / len(timings)
            p95_t = _percentile(timings, 0.95)
            print(f"    Avg exec time:    {avg_t:.3f} ms")
            print(f"    P95 exec time:    {p95_t:.3f} ms")
    print()

    failures = [d for d in stats["detail"] if not d["correct_at_1"] and d["expected"]]
    fps = [d for d in stats["detail"] if d["false_positive"]]
    if failures:
        print("Missed positives (expected a rule to fire correctly at rank 1):")
        for d in failures:
            print(f"  {d['id']} [{d['source']}]: expected {d['expected']}, got {d['got']}")
    if fps:
        print("False positives (expected NO rule to fire, but one did):")
        for d in fps:
            print(f"  {d['id']} [{d['source']}]: got {d['got']}")
    print()


def main() -> None:
    import io
    import sys

    # IMPORTANT: this writes to "latest", not to a version-tagged file.
    # Overwriting benchmark_v1.0.0.* every time someone runs the
    # benchmark (e.g. via demo.py) would silently mutate what's
    # supposed to be a frozen, citable release artifact — exactly the
    # kind of quiet history-rewrite this project has otherwise been
    # careful to avoid. To snapshot a real release, copy
    # benchmark_latest.* to benchmark_vX.Y.Z.* by hand at release time
    # and commit it deliberately (see docs/adr/0003 and the Releases
    # section in README.md).
    output_tag = "latest"
    buffer = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = _Tee(real_stdout, buffer)

    try:
        all_cases = load_all_cases()
        test_cases = [c for c in all_cases if c.split == "test"]
        train_cases = [c for c in all_cases if c.split == "train"]

        if not test_cases:
            raise SystemExit("No test-split cases found — cannot report honest metrics.")

        known_ids = default_registry.known_rule_ids()

        active_test = [
            c for c in test_cases if c.expected_rule_id is None or c.expected_rule_id in known_ids
        ]
        pending_test = [
            c for c in test_cases
            if c.expected_rule_id is not None and c.expected_rule_id not in known_ids
        ]

        print(f"TraceKit Benchmark — run tag: {output_tag}")
        print(f"(Rules were designed against {len(train_cases)} train-split cases; "
              f"metrics below are computed ONLY on the {len(test_cases)} held-out "
              f"test-split cases, never seen during rule design.)\n")

        stats = evaluate_split(active_test)
        print_report(stats, "test")

        ground_truth_counts = summarize_ground_truth(all_cases, known_ids)
        print_ground_truth_summary(ground_truth_counts)

        pending_detail = evaluate_pending_test_detail(pending_test)
        print_pending_test_detail(pending_detail)
    finally:
        sys.stdout = real_stdout

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"benchmark_{output_tag}.txt").write_text(buffer.getvalue())
    (RESULTS_DIR / f"benchmark_{output_tag}.json").write_text(
        json.dumps(_json_safe_stats(stats), indent=2)
    )
    print(f"\nSaved: benchmark/results/benchmark_{output_tag}.txt and .json")
    print("(To create a citable, frozen release snapshot, copy these to")
    print(" benchmark_vX.Y.Z.* by hand and commit them deliberately.)")


if __name__ == "__main__":
    main()
