# ADR 0004: Rule Independence Invariant

## Status
Accepted (formalized during ATTR003 design; implicit in the
architecture since ADR 0001, made explicit here)

## Context
While designing ATTR003, a requirement surfaced that ATTR003 should
"never even run" if ATTR002 already matched the same case (e.g.
`[].add()` should always be diagnosed by ATTR002, never by ATTR003's
typo-detection fallback). The literal way to implement that is for
ATTR003 to ask "did ATTR002 already match this?" — which requires one
rule to inspect another rule's behavior.

## Decision
**Rules must not inspect or depend on the outputs of other rules.**
Every `Rule.matches(ctx)` call is independent and stateless with
respect to other rules. Conflicts between rules that both match the
same case are resolved *solely* by the registry's existing ranking:
confidence, then priority, then registration order (see ADR 0001,
`RuleRegistry.evaluate`).

## Rationale
Rule-to-rule coupling doesn't stay contained to one pair. If ATTR003
is allowed to ask "did ATTR002 match?", the next exception family's
rules will want the same capability — e.g. a hypothetical `INDEX002`
asking whether `INDEX001` already matched. Each such special case adds
a hidden dependency edge between rules that were designed to be
independently addable, independently testable, and independently
removable. Left unchecked, this turns a registry of isolated rules
into a dependency graph that has to be reasoned about as a whole —
exactly the maintenance burden this architecture was built to avoid
(see ADR 0001's rationale for compiled-but-simple rules).

The actual requirement — "ATTR002 should win when both match" — is
already fully satisfiable by the mechanism that already exists:
setting each rule's confidence within a tier such that a more certain
diagnostic strategy's floor sits strictly above a less certain one's
ceiling (see the Confidence Tiers below, formalized in ADR 0002). No
new coordination mechanism was needed; the existing ranking already
does the job.

## Confidence tiers (formalizes ADR 0002 for use across all future rules)

| Tier | Confidence range | Meaning |
|---|---:|---|
| Structural fact | 0.98-1.00 | Runtime directly proves the diagnosis (e.g. ATTR001: the object literally is `None`) |
| Deterministic lookup | 0.93-0.97 | Known, curated mapping with no ambiguity once matched (e.g. KEY002, ATTR002) |
| Strong heuristic | 0.80-0.90 | Likely, inferred from similarity — not certain (e.g. KEY001 at low edit distance, ATTR003) |
| Weak heuristic | <0.80 | Probably shouldn't auto-recommend without more corroborating evidence |

Assigning every new rule to one of these tiers — rather than picking
an arbitrary-feeling number — is itself what keeps the independence
invariant enforceable in practice: as long as tiers don't overlap
(e.g. no "deterministic lookup" rule ever below 0.93, no "structural
fact" rule ever below 0.98), any two rules from different tiers
resolve correctly through ranking alone, with no coupling required.

## Consequences
- No rule may import, call, or reference another rule's class or
  registration.
- Any future case where "rule A should always beat rule B" must be
  solved by placing A and B in tiers with non-overlapping confidence
  ranges — never by A or B inspecting the registry's other contents
  or each other's results.
- This invariant is checked, not just stated: `test_attr002_*` and any
  future `test_attr003_*` interaction tests assert on ranked registry
  output (confidence-based ordering), not on one rule querying another.
- If a genuine case ever arises where confidence-tier separation truly
  cannot resolve an ordering requirement, that is a signal the two
  "rules" are actually one rule with two branches — not a signal to
  add rule-to-rule coupling.
