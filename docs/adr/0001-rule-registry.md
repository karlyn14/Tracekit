# ADR 0001: Rule Registry — Compiled Python Classes, Not Declarative YAML

## Status
Accepted (v1.0.0)

## Context
Rules could be expressed as plain Python classes, or as a declarative
format (YAML/JSON) loaded at runtime. A declarative format is easier
to validate, diff, and let non-programmers contribute to; a compiled
class is simpler to build, debug, and test, and imposes no schema or
parser to maintain.

## Decision
v1 uses plain Python classes (`Rule` subclasses), registered once at
import time into a `RuleRegistry` indexed by exception type for O(1)
lookup.

## Rationale
At the time of this decision, v1 had roughly 10 rules across 3
exception-diagnosis strategies. There was no evidence a declarative
schema was necessary at this scale — introducing one would have added
a parser, a validator, and a plugin-loading mechanism to solve a
problem the project didn't yet have. The `Rule` interface was
deliberately kept narrow (`RULE_ID`, `exception_types`, `matches()`)
so a `Rule.from_dict()` constructor could be added later without
requiring a rewrite of the registry or any existing rule.

## Consequences
- Adding a rule requires writing one class and one registration line
  — no schema changes, no changes to existing code.
- Contributors need to write Python, not just data — an accepted
  tradeoff for a project this size, revisited if/when the rule count
  or contributor base grows enough to justify the added complexity of
  a declarative loader.
- Tie-breaking for equal-confidence candidates is fully deterministic:
  `priority` field, then registration order — documented rather than
  left arbitrary.
