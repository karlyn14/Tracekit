# Viva Preparation — Six Core Questions

Short, direct answers. Each points at the specific evidence in the
repo rather than asserting a claim on its own.

---

**Q1. Why rule-based instead of ML?**

Interpretability and reproducibility. A rule's output can be traced to
an exact line of code and an exact piece of evidence — "edit distance
2, closest key 'Name'" — with no training data, no model drift between
runs, and no black-box behavior to defend in a viva. An ML classifier
would need labeled training data at a scale this project doesn't have,
and would replace "here is the evidence" with "the model said so,"
which is a weaker position for a tool whose entire value proposition
is trustworthy, explainable suggestions (see ADR 0002).

---

**Q2. Why only KeyError?**

Depth over breadth, deliberately. Three genuinely different diagnostic
strategies (fuzzy lexical, deterministic normalization, structural
analysis — KEY001/002/003) fully proven out, benchmarked, and
documented is stronger evidence for "this architecture generalizes"
than a shallow rule for five exception types with no evaluation rigor
behind any of them. Extending to AttributeError/IndexError/TypeError
is explicitly flagged as future work (README) — the registry and
context snapshot were already designed exception-type-agnostic, so
this is an additive change, not a redesign.

---

**Q3. Why edit distance?**

It's the standard, well-understood metric for "how different are two
short strings," and it's exactly the failure mode KEY001 targets:
typos. The real finding from using it (documented in "Lessons
Learned") is where it breaks down — it can't distinguish a genuine
typo from two deliberately different identifiers that happen to look
similar (`SERVER_HOST`/`SERVER_PORT`). That's an honestly reported
limitation, not a hidden one, and it's exactly why KEY002 and KEY003
don't use edit distance at all — they use deterministic checks
instead, once the benchmark showed what edit distance couldn't cover
reliably.

---

**Q4. Why abstain instead of guessing?**

Measured, not assumed: an early version of KEY001 picked an arbitrary
winner when two candidates tied for closest match (e.g. `'it'`
equidistant from `'id'` and `'ip'`), and benchmarking that directly
showed a 33% false positive rate on one dataset slice. Changing the
rule to abstain on exact ties dropped that to 0%, with precision and
coverage unchanged (ADR 0002, benchmark history table). Wrong,
confident advice is worse than no advice for a tool whose entire
pitch is trustworthiness — abstention is a first-class, deliberately
tracked outcome, not a fallback.

---

**Q5. Why benchmark-driven development?**

Because "it works on the examples I wrote it against" is circular —
it proves the rule matches its own test cases, not that it
generalizes. Every rule in this project was accepted the same way:
train/test split (rules never tuned against the held-out test data),
an explicit acceptance criterion (improve precision/coverage without
an unacceptable rise in false positives), and — for KEY003
specifically — ground truth written into the benchmark *before* the
rule existed, so the rule was built to satisfy a pre-committed spec
rather than the spec being written to match whatever got built (ADR
0003).

---

**Q6. Why do deterministic rules outperform heuristic ones?**

Because they have no equivalent source of uncertainty once a match is
found. KEY002 (case-fold equality) and KEY003 (exact key match one
level down) both hit 100% precision/coverage and 0% measured false
positives; KEY001 (fuzzy distance) sits at 100% precision@1 but ~25%
false positives on adversarial cases, because "close" is inherently a
matter of degree while "identical after normalization" or "present in
this exact nested location" is not. This is the project's central
engineering finding (see README "Results" and the hypothesis stated
there) — and it's a genuine tradeoff, not a flaw: heuristic matching
covers a broader class of real typos that deterministic checks
structurally cannot catch at all.

---

**Bonus — what would TraceKit 2.0 include?**

In priority order, each already flagged honestly as a boundary rather
than a surprise:
1. Additional exception types (AttributeError, IndexError, TypeError)
   using the same registry/benchmark discipline already proven here.
2. Frame-walking for upstream causal chains (v1 only diagnoses the
   raise site — documented limitation).
3. A declarative rule format, if/when rule count actually justifies
   the added complexity (ADR 0001 — deliberately not built prematurely).
4. `sys.excepthook` integration for zero-config drop-in use.
