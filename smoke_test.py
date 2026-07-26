"""
Manual end-to-end proof: trigger a real KeyError with a typo,
run it through the full pipeline, print the formatted result.
"""

import sys

import tracekit.rules  # noqa: F401 - registers rules as a side effect
from tracekit.core.analyzer import analyze
from tracekit.output.formatter import format_result


def buggy_function():
    data = {"Name": "Ada", "Age": 36, "City": "London"}
    return data["Nmae"]  # typo: should be "Name"


def main():
    try:
        buggy_function()
    except Exception as exc:
        result = analyze(exc, exc.__traceback__)
        print(format_result(result))
        print()
        print("=== Raw AnalysisResult (for inspection) ===")
        print(f"candidates: {result.candidates}")


if __name__ == "__main__":
    main()
