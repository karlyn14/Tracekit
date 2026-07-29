# TraceKit v2.0 Retrospective — Before Starting IndexError

Written after closing the AttributeError family (ATTR001-003), before
touching a line of code for the next exception family. Purpose: bank
what actually worked and what actually cost time, so IndexError starts
from evidence rather than repeating the same discovery process.

## What parts of the architecture worked well?

- **The registry's confidence/priority/registration-order ranking**
  turned out to be sufficient for every ordering question that came
  up, including the ATTR002/ATTR003 interaction — without ever needing
  a single special case. Designed for KeyError, validated unmodified
  across two more rules in a second family.
- **`ExceptionContext` as a one-time snapshot** (no retained frame)
  needed zero changes to support AttributeError at all — `ctx.exc_value`
  already exposed everything ATTR001-003 needed via `AttributeError`'s
  own `.obj`/`.name` attributes. The snapshot design wasn't
  KeyError-specific by accident; it turned out to be genuinely general.
- **Crash isolation in the registry** meant every new rule family could
  ship with a "does this rule crash safely" test reusing the exact
  same pattern, with no new infrastructure.

## What slowed development?

Nothing slowed *implementation* — every accepted rule went from red
tests to green on the first attempt once its benchmark and design were
settled. What actually took time was upstream of coding:

- **ATTR003's design-contract step took real, deliberate time** before
  any benchmark case existed — and that time is exactly why it needed
  zero iteration afterward. Worth naming honestly: this wasn't
  wasted time, it was time moved from "iterate after a red benchmark"
  to "iterate on paper before writing a benchmark case." Cheaper to
  fix a wrong idea in a markdown file than in a rule plus its tests.
- **Two real mistakes were caught only by verifying the diff, not by
  the plan being followed correctly**: the benchmark run silently
  overwriting a "frozen" `v1.0.0` artifact (fixed by separating
  `benchmark_latest.*` from versioned snapshots), and a section header
  that got silently dropped during an earlier README edit. Neither was
  caught by design discipline — both were caught by actually reading
  output/diffs before committing. Lesson: the process guards against
  *design* mistakes well; it does not automatically guard against
  *editing* mistakes, which still need a real "did this actually do
  what I meant" check every time.

## Which ADRs proved most valuable?

- **ADR 0004 (Rule Independence Invariant)** — not because it prevented
  a bug, but because it prevented a *design conversation* from
  recurring. Without it, ATTR003's "how do I make sure ATTR002 wins"
  question would likely resurface verbatim for the next rule pair in
  the next family, each time requiring the same reasoning from
  scratch. Naming it once made "put them in different confidence
  tiers" the default answer going forward, not a rediscovery.
- **The confidence tiers (ADR 0004, extending ADR 0002)** — turned
  ATTR003's 0.88/0.80 into values with a stated justification instead
  of "chosen because it seemed right," which mattered directly when
  reviewing whether ATTR002 and ATTR003 could ever collide.

## Which benchmark practices should become mandatory (not optional) for IndexError?

- **Ground truth before implementation**, exactly as done for
  KEY003/ATTR001-003 — not just for the family's first rule, but for
  every rule in it. This is now the default, not a special case.
- **Verify, don't assume**, for every case added: actually run the
  snippet and confirm it raises the intended exception; actually
  compute edit distances (or whatever the rule's deciding metric is)
  rather than eyeballing "that looks like distance 1." This caught
  nothing dramatic in AttributeError, but it costs almost nothing and
  removes a whole class of "the benchmark case was wrong, not the
  rule" bugs before they can happen.
- **Adversarial negatives, not just convenient ones** — KEY001's
  `SERVER_HOST`/`SERVER_PORT`-style cases and ATTR003's `.id`/`.ip`/`.it`
  tie were the cases that actually taught something. A benchmark of
  only "obviously correct" and "obviously unrelated" cases would have
  missed the false-positive and ambiguity findings entirely.
- **Fix the report, not the dataset**, when a reporting gap appears
  (the ATTR002 train-only visibility issue). Reshaping data to make a
  status table look complete is a subtle but real temptation worth
  naming explicitly before IndexError's benchmark exists.

## What would change before starting IndexError?

- **Reserve the separate written design-contract step (like
  `docs/design/ATTR003.md`) specifically for whichever rule introduces
  heuristic/inferential reasoning into a family** — not necessarily
  for a family's first rule if that rule is deterministic (ATTR001
  didn't need one; it needed only the two-line design note already
  embedded in its benchmark ground truth). Don't over-apply the
  heaviest process step to every rule by default.
- **Watch the `_levenshtein` duplication.** It now exists, copy-pasted,
  in both `rules/keyerror/rules.py` and `rules/attributeerror/rules.py`.
  Two occurrences isn't yet a strong enough signal to justify a shared
  utility module (see ADR 0001's reasoning against premature
  abstraction) — but if IndexError's first heuristic rule needs the
  same function a third time, that's the point to actually extract it,
  not before.
- **Keep the "only two files for implementation" discipline** — it has
  held for six rules across two families with zero exceptions, and
  there's no evidence yet that IndexError needs anything different.

## What's next

Start IndexError from the same lifecycle validated twice now:
Design (if the rule is heuristic) → Benchmark ground truth → Red tests
→ Implementation → Benchmark → Accept/Reject. No shortcuts assumed
just because the process has worked before — each rule still earns
its acceptance on its own evidence.
