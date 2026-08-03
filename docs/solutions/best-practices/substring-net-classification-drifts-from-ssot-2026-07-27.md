---
title: "A hand-maintained keyword list beside an SSOT will drift from it -- and substring matching fails silently in both directions"
date: "2026-07-27"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a net, pin, or signal's safety-relevant electrical domain (HV/SELV, mains/isolated) is decided by testing whether a keyword is a substring of its name"
  - "two independent mechanisms in the same codebase both answer 'is this net HV/SELV/safety-relevant' -- one of them a canonical, human-reviewed declaration, the other a keyword list"
  - "a code comment asserts 'substring match is safe for these' next to a keyword list"
  - "auditing a codebase for one instance of a defect class and deciding whether to also search for siblings"
  - "a module's docstring calls it 'the single source of truth' and a second, near-identical module exists elsewhere"
  - "a substring-classification gate reports a file as clean, and the question that file's code answers (routability, layer classification, trace width) differs from the domain the gate's own keyword vocabulary was scoped to"
tags:
  - net-classification
  - substring-matching
  - word-boundary
  - ssot-drift
  - fail-silent-both-directions
  - ast-based-gate
  - systemic-fix
  - vocabulary-scope-gap
---

# A hand-maintained keyword list beside an SSOT will drift from it -- and substring matching fails silently in both directions

## Context

`elec/domain_manifest.yaml` is this project's canonical, human-reviewed
declaration of which compiled nets are HV (mains-adjacent) and which are
SELV (isolated low-voltage). Three independent places in the placer/router
codebase also decided the same question, by hand, with a keyword list
tested via Python's plain `in` substring operator -- and all three were
wrong, twice in each direction, before this pattern was recognized as one
defect class rather than three unrelated bugs:

1. **`creepage_check.py`** (fixed in merge `5076e715`) -- FALSE POSITIVES.
   `broad_keywords` contained `"L1"`, `"L2"`, `"LINE"`, tested via
   `kw in name_upper`, directly under a comment claiming "substring match
   is safe for these". `"L1"` matched `COIL1`, `"L2"` matched `COIL2`
   (SELV relay-coil-drive nets), `"LINE"` matched `safety.ovp-line` (a
   SELV fault-interlock signal, explicitly documented as SELV in the
   manifest with a multi-paragraph justification). **All 24 reported
   creepage violations on the live board were false positives on SELV
   nets** -- the real mains nets `ac_l`/`ac_n` matched no broad keyword at
   all, because the real bug (missing coverage for them) was masked by 24
   noisy false alarms drowning it out.
2. **`clearance_check.py`** (fixed in merge `466c7724`) -- FALSE
   NEGATIVES, the mirror image, found the same day. HV was classified by
   four substrings (`AC_`, `HV_`, `HIGH_VOLTAGE`, `MAINS`) that, on this
   board's actual net names, matched *only* `ac_l`/`ac_n`. **Eleven real
   HV-domain nets declared in the manifest** (`DC_BUS_RTN`, `+170V_BUS`,
   `PWR_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`, `+15V_LS`, `w1_1`, `w1_2`,
   `zcd`, `a`) **silently fell through to a 0.127mm default** instead of
   the true IEC 60335 3-14mm requirement. One confirmed pair moved from
   0.127mm to 14.0mm once fixed. On a mains-connected appliance this is a
   safety gap, not a cosmetic one.
3. **`clearance_engine.py`** -- a third instance, found by asking "does
   this same shape exist anywhere else" rather than treating the first
   two as isolated incidents. Auditing every net-name classifier in the
   codebase for the identical AST shape (a keyword compared via `in`
   against an uppercased net name, drawn from a small hand-maintained
   list) surfaced **six more live instances** the same day, including a
   *duplicate module* (`core/net_classification.py`) whose own sibling
   (`router_v6/net_classification.py`) both claim, in their own
   docstrings, to be "the single source of truth" -- while carrying the
   identical unfixed bug (`HV_NET_PATTERNS`'s bare 2-character `"PE"`,
   which as a substring matches any net name containing "SPEED", "TYPE",
   "OPEN", ...). See
   `docs/evidence/2026-07-27-net-classification-gate.md` for the full
   nine-instance list, each with a differential proof.

## The pattern

**A hand-maintained classification mechanism living beside an authoritative
SSOT will drift from it.** This is not a claim about carelessness -- every
one of these keyword lists was written by someone reasoning correctly
about the board's net names *at the time*. The SSOT (`elec/domain_manifest.yaml`)
gets updated when the design changes (a net renamed, a new HV rail added,
an isolation barrier redesigned); the keyword list, living in a separate
file with no mechanical link to the SSOT, does not get updated in step,
because nothing forces it to. Two mechanisms answering the same question
independently is not redundancy -- redundancy implies they're checked
against each other; here, neither was ever compared to the other until an
incident forced someone to look.

**Substring matching fails silently in BOTH directions, and neither
failure announces itself:**

- **Over-matching** (a keyword accidentally present as a substring of an
  unrelated, non-matching net name) produces **confident false alarms** --
  the check runs, reports violations, and looks like it's doing its job.
  Nobody escalates a false alarm as a *coverage* problem; they escalate it
  as a *tuning* problem, or worse, they start ignoring the check's output
  because "it's noisy." 24-for-24 false positives on the real board looked
  like an aggressive, working check, not a broken one.
- **Under-matching** (a real HV net whose name doesn't happen to contain
  any listed keyword) produces a **silent safety gap** -- the check runs,
  reports zero violations, and looks like a clean bill of health. Nothing
  distinguishes "genuinely no violations" from "didn't know to look."
- **Neither direction fails loud.** Both look exactly like a working
  gate: it runs, it produces a verdict, the verdict is internally
  consistent. The only way to tell the two error modes apart from a
  genuinely correct classification is to independently re-derive which
  nets *should* have matched and diff against what the code actually
  matched -- which is exactly what the SSOT the code should have been
  reading from already contains.

**A keyword length under ~4 characters is a strong prior for substring
collision risk in this specific domain.** `"L1"`, `"L2"`, `"HV"`, `"AC"`,
`"PE"` all collided with real, unrelated net-name fragments on this board.
Longer, more specific keywords (`"HIGH_VOLTAGE"`, `"MAINS_240V"`) carry
much lower risk simply because there are fewer plausible unrelated strings
that happen to contain them -- but "lower risk" is not "no risk"; `"LINE"`
(4 characters) still collided with `safety.ovp-line`. The fix is not
"only anchor the short keywords" -- it is anchor all of them, uniformly,
the same way the already-correct `AC`/`HV` regex checks in
`creepage_check.py` did before the rest of that function caught up.

## Guidance

1. **When a canonical SSOT for a classification exists, read from it
   first, and treat any independent heuristic as a defense-in-depth
   fallback, not a competing source of truth.** Every fixed function in
   this incident now checks `elec/domain_manifest.yaml` membership before
   falling back to a keyword heuristic (`clearance_check._classify_net_class`
   already did this after merge `466c7724`; the other eight instances
   found the same day did not, and needed the same treatment). See
   `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
   for the sibling lesson about trusting a name at all, even the SSOT's
   own recorded name, without tracing what it actually connects to.
2. **Never use a bare `in` (Python's string containment operator) to
   classify a name into a safety-relevant category.** It is *always* an
   unanchored substring test with no concept of a word boundary. Use
   `re.search(r"(?:^|_)KEYWORD(?:$|[\d_])", upper)` (delimited by `_` or
   start/end of the uppercased name) instead -- the technique this
   codebase had already invented once, for the `AC`/`HV` checks in
   `creepage_check.py`, before the incident that forced applying it
   everywhere else it should have been from the start.
3. **On confirming a new instance of a defect class, ask "where else does
   this shape occur" before declaring the fix complete.** The third
   instance in this incident (`clearance_engine.py`) was found by asking
   exactly that question about the first two, and asking it again after
   fixing the third surfaced six more, including a duplicate "single
   source of truth" module. A defect class confirmed twice is a
   *pattern*, not two coincidences; treat the third occurrence as
   evidence there may be a fourth, fifth, and ninth, and build the
   mechanical check that finds them (see next point) rather than fixing
   only the specific line that was reported.
4. **A defect class confirmed more than once earns a gate, not just a
   fix.** `scripts/check_net_classification.py` was built specifically
   because "fix the reported line" does not prevent the same shape from
   being written again next week, in a tenth file. It uses AST-level
   detection (tracking `for`/comprehension loop-variable bindings and
   same-file constant assignments) rather than regex-over-source-text,
   because the AST shape (a keyword loop-bound `Compare(in)` against an
   uppercased name) is exactly what makes this defect class mechanically
   detectable, independent of formatting. It also caught an instance
   *while being built* that manual audit had missed: a duplicate module
   whose `patterns` parameter the gate could not statically resolve, which
   it correctly reported as `UNRESOLVED` (not silently safe) rather than
   dropping -- checking it by hand then found the ninth confirmed
   instance.
5. **"Discovered nothing to check" must be a gate failure, not a pass.**
   This repo has a documented history of gates that silently checked an
   empty or partial set and reported success (see
   `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` and
   `gate-neutering-mechanisms-2026-07-26.md`). `check_net_classification.py`
   treats zero files or zero `in`-operator call sites discovered across
   the entire scan as a hard tool error (exit 5), and reports the
   discovered/resolved/unresolved/candidate/violation counts on every run
   -- a "0 violations" verdict is only trustworthy next to a denominator
   proving real work was done.
6. **A `Compare(in)` AST match is not proof of a real substring-collision
   bug -- it's a candidate that needs a human decision, and a justified
   allowlist is the right release valve for it, not a reason to avoid
   building the gate.** `check_net_classification.py`'s own detector
   cannot statically distinguish `x in some_dict` (exact key membership)
   from `x in some_string` (substring test) -- both are the same AST
   node. Rather than either under-detecting (missing real instances to
   avoid any false positive) or building a much more complex type-aware
   detector, the gate accepts a bounded false-positive rate and resolves
   it via `.net-classification-allowlist`, exactly like
   `.undeclared-imports-allowlist`: every entry scoped to one function in
   one file, with a written justification a reviewer can check.
7. **A gate scoped by vocabulary, not just by file, can still miss the exact
   file it should have caught -- check whether "not found" means "not
   present" or "not in the word list."** `check_net_classification.py`'s
   `SAFETY_VOCAB` was deliberately restricted to HV/SELV mains-adjacent
   keywords, by design, per its own docstring: "GND/VCC/VDD/POWER-style
   low-voltage-domain checks are out of scope." On 2026-07-28, a **fourth**
   instance of this exact defect shape was found in
   `_parse_board.py:132-137` -- `"GND" in zone.netName or "VCC" in
   zone.netName or "+" in zone.netName or "PWR" in zone.netName` -- sitting
   in an already-scanned file (`packages/temper-placer/**/*.py`), matching
   the detector's own AST shape exactly, and invisible anyway, because
   `GND`/`VCC`/`PWR`/`"+"` were never in the vocabulary. This is a
   **different question from the one the gate was built to answer** ("does
   this net's copper make its layer non-routable," not "is this net HV or
   SELV") sharing only the AST shape, not the domain -- so the original
   scoping decision was reasoned, not careless, and still proved too
   narrow. Widening `SAFETY_VOCAB` to include `GND`/`VCC`/`PWR`/`"+"`
   surfaced **five more, already-partially-fixed-but-left-bare** live
   instances in the same pass (`_constraint_types/config.py`,
   `clearance_check.py`, `routing_demand.py`,
   `trace_width_assignment.py`, plus one correctly allowlisted dict-key
   match in `design_rules.py`) -- each in a file whose *other* keyword
   branches (HV/gate-drive) had already been anchored in the 2026-07-27
   sweep, left bare specifically for the vocabulary this gate didn't yet
   cover. Full detail, including the bug's routing consequence (excluding
   both outer copper layers from the router's grid) and the before/after
   gate output proving the widened vocabulary would have caught it:
   `docs/evidence/2026-07-28-zone-layer-classification-fix.md (evidence doc never merged to main; finding reproduced inline)`.

## Why This Matters

A false-positive safety check and a false-negative safety check look
identical from the outside: both are a script that runs and prints a
verdict. The only thing that distinguishes "24 real violations" from "24
false alarms drowning out the two real gaps" is independently re-deriving
what the correct answer should have been -- which is precisely the work a
canonical, human-reviewed manifest already does, if the code actually
reads from it. A keyword list that duplicates that manifest's job by hand,
using a substring test that has no concept of what a net name actually
*is* versus what it merely *contains*, will drift from the manifest every
time the design changes and the manifest is updated but the list is not --
and the drift will not announce itself in either direction until someone
goes looking, on a board where "someone goes looking" is the only thing
standing between a design and a mains-adjacent safety hazard reaching
production.

## When to Apply

- Before writing (or reviewing) any function that decides a net's,
  pin's, or signal's electrical safety domain (HV/mains vs.
  SELV/isolated) from its name.
- When a codebase has a canonical declaration file for a safety property
  (a manifest, a domain partition, a certified-parts list) and you're
  about to write a second mechanism that answers the same question a
  different way.
- When reviewing a "fix" for a reported false positive or false negative
  in a net/pin classifier -- check whether the fix is anchoring an
  existing substring test, or merely adjusting which keywords are in the
  list (the latter does not close the underlying defect class).
- When a defect is confirmed a second time in the same shape -- stop
  fixing individual lines and build the mechanical check.

## Examples

```python
# WRONG -- plain substring test, matches "COIL1"/"COIL2" (SELV), not just
# real "L1"/"L2" mains phases:
broad_keywords = ["L1", "L2", "LINE"]
if any(kw in name_upper for kw in broad_keywords):
    return True

# RIGHT -- word-boundary anchored, delimited by "_" or start/end:
for kw in broad_keywords:
    if re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", name_upper):
        return True
```

```python
# RIGHT -- SSOT-first, anchored keyword as defense-in-depth fallback:
def _classify_net_class(net_name: str) -> str:
    if net_name in hv_manifest_nets:          # elec/domain_manifest.yaml
        return "HV"
    if _is_hv_keyword_match(net_name.upper()):  # anchored, not "in"
        return "HV"
    return "SIGNAL"
```

## Related

- `docs/evidence/2026-07-28-zone-layer-classification-fix.md (evidence doc never merged to main; finding reproduced inline)` -- the
  2026-07-28 fourth instance: `_parse_board.py`'s bare `"GND"`/`"VCC"`/
  `"+"`/`"PWR"` substring test excluded whole copper layers from the
  router's grid, missed by `check_net_classification.py`'s vocabulary
  scope rather than its file scope, and the five sibling instances the
  widened vocabulary then found in the same pass.
- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  -- the sibling lesson: even the SSOT's own recorded net name can be
  wrong relative to the node's actual topology; this doc's lesson is
  about a *second, independent, hand-maintained* classifier drifting from
  the SSOT, not about the SSOT's own name being stale.
- `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` and
  `gate-neutering-mechanisms-2026-07-26.md` -- the anti-vacuous-truth and
  denominator-reporting discipline `check_net_classification.py` follows.
- `docs/evidence/2026-07-27-net-classification-gate.md` -- the full
  nine-instance list, differential proofs, falsifier, and the
  manifest-only-vs-hybrid-classification trade-off discussion.
- `packages/temper-placer/src/temper_placer/router_v6/creepage_check.py`,
  `clearance_check.py`, `clearance_engine.py` -- the fixed instances, each
  carrying an in-code bug-history comment.
- `scripts/check_net_classification.py` -- the gate.
