---
title: "Gate subset blindness — a check that passes over a fraction of its input without saying so"
date: "2026-07-27"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a gate's include-list is a filename substring, a hand-maintained dict, or an opt-in sentinel file rather than a documented default-include/narrow-exclude rule"
  - "a gate prints a pass/fail verdict without also printing how many items it looked at"
  - "two mechanisms in the same codebase classify the same underlying data (a netlist, a set of modules, a set of requirements) independently"
  - "auditing whether a 'coverage' or 'traceability' gate's headline message is distinguishable from what it would print with zero real input"
tags:
  - gate-subset-blindness
  - denominator
  - coverage-ratio
  - vacuous-truth
  - check_vacuous_gates
  - check_domain_partition
  - check_traceability
---

# Gate subset blindness — a check that passes over a fraction of its input without saying so

## Context

`docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
catalogs four ways a CI check can exist, run, and still never fail —
including mechanism 4, `all([])` returning vacuously `True` on an **empty**
collection. A 2026-07-27 gate audit
(`docs/evidence/2026-07-27-gate-subset-blindness-audit.md`) found a fifth,
distinct shape: a gate whose input collection is **not empty**, scans a
real, non-trivial fraction of it, reports a clean verdict — and that
fraction is a silent, undisclosed minority of the true universe. Vacuous
truth is invisible because the collection is empty; subset blindness is
invisible because the collection *looks* substantial, so nobody thinks to
ask "substantial compared to what?" Three instances, escalating:

1. **`scripts/check_vacuous_gates.py`** — the anti-vacuous-truth gate
   itself. Scoped by a path-substring include-list, `SCOPE_TOKENS = ("gate",
   "valid")`, restricted to `packages/*/src` only. Measured against the real
   validator surface: **52 of ~585 candidate `.py` files (2 of 13 known
   validator modules)**. Structurally blind to `scripts/*.py` entirely — the
   glob never walked that directory — so the gate could not have found a
   defect in itself, or in `check_domain_partition.py`,
   `capacity_budget_gate.py`, `mpn_fabrication_gate.py`, or
   `check_derived_doc_drift.py`, regardless of what their filenames
   contained. Widened to a default-include/narrow-documented-exclude rule
   (every `.py` under `packages/*/src` + `packages/*/tests` minus
   test-file-named modules, plus top-level `scripts/*.py`): **526 files**,
   **13 real unguarded `all()` calls surfaced, across 6 files** — three of
   them CI gate scripts (`mpn_fabrication_gate.py`,
   `check_derived_doc_drift.py`, `import_linter_gate.py`) plus
   `ci_identity_check.py`, `spc_rules.py`, and two `temper-placer/src`
   modules. The gate is left red on purpose — narrowing the scope back to
   regain green would reintroduce exactly the blindness this pass exists to
   remove.
2. **The IEC 60335 clearance/creepage path** ran on **10 of 165 compiled
   nets**, via a second, hand-maintained `_NET_DOMAINS` dict in
   `_real_board_fixture.py` that had quietly drifted from
   `elec/domain_manifest.yaml` (39 declared nets at the time, since expanded
   to 47). The 10-net dict was a strict subset of the manifest, not an
   independent source — meaning the *already-known-sparse* manifest was
   sparser still by the time it reached the actual physical-clearance check.
   At full manifest-derived coverage (156/170 components classifiable, up
   from 127/170), `verify_iec60335_compliance` surfaces **17 violations
   across 9 component pairs**, worst pair **2.262 mm** measured against
   requirements that range **3.0–8.0 mm** depending on insulation class
   (BASIC clearance 3.0 mm through REINFORCED creepage 8.0 mm) — the worst
   pair fails even the lowest BASIC-clearance floor. Two of the nine pairs
   depend on this pass's own manifest expansion; the rest were findable
   under nets the manifest had already declared, just never fed to the
   validator that mattered. Full detail:
   `docs/evidence/2026-07-27-domain-classification-coverage.md`.
3. **`scripts/check_traceability.py`** printed `R3 gate passed: all
   requirements are covered.` while its R3 coverage check had evaluated
   **zero** non-deferred requirements — not "a narrow but real slice," zero,
   for two independent, stacked reasons: an opt-in `TRACEABILITY` sentinel
   file existed in exactly **1 of the repo's many directories**
   (`packages/temper-placer/tests/router_v6/`), and the one plan that
   sentinel could ever reach (`N10`, the only `status: active` plan of 11
   registered) structures its work as `### U1.`–`### U4.` headings that the
   `R<n>`-only requirement parser doesn't recognize, so it parsed to an
   empty requirement set regardless. Widening the scan to every registered
   plan's declared `scope` (196 files, 8 of 11 plans) did **not** surface a
   pile of newly-visible uncovered requirements the way `check_vacuous_gates`
   widening did — it surfaced that the one plan the old model could reach
   was itself unreadable to the parser, so the true historical
   checked-requirement count, under both models, was zero the whole time.
   Full detail: `docs/evidence/2026-07-27-traceability-scope-fix.md`.

**The rule that emerged, stated in the audit itself:** every gate that did
not print its denominator turned out to have one worth printing.
`scripts/check_domain_partition.py` — which reported `"Checked 39 declared
nets across 2 domains ... over 165 compiled nets / 170 components"` on
every run, pass or fail, from the day it was written — was the one gate in
the audit's table that needed no correction. It is cited in the audit as
"the reference example this whole audit is measured against," and its own
empty-manifest case (`domains: {}`) fails closed by explicit design rather
than passing vacuously.

## Guidance

1. **Print the denominator on every run, pass or fail — not just a
   pass/fail verdict.** `check_domain_partition.py`'s `"N declared / M
   compiled"` line is the template: it costs one `console.print` and turns
   "is this gate covering enough of the codebase" from an audit project
   into a five-second read of its own output.
2. **Distinguish "vacuous" from "subset."** `all([])` on zero items is
   loud once you know to check for it (`check_vacuous_gates.py` already
   catches this class). A gate that scans 10, 39, or 52 real items and
   passes with zero violations gives no such signal — the collection is
   non-empty, the logic runs, and the verdict is honestly computed *over
   what it was given*. The defect is entirely in what it was given, which
   only a stated denominator exposes.
3. **Prefer default-include with a narrow, documented exclude over any
   include-list** — a filename-substring token set, a hand-maintained
   per-file dict, or an opt-in sentinel file all share the same failure
   mode: they require a maintainer to remember to add every new
   module/net/plan to them, which is exactly the mechanism that produced
   2/13 validator coverage, a stale 10-net dict, and a 1-directory
   traceability sentinel. An exclude list only has to name what is
   *known not* to belong (test-file naming conventions, one frozen
   package) — everything else is in scope automatically, with no
   PR-invisible omission possible.
4. **When two mechanisms classify the same data independently, one of them
   is stale relative to the other and neither side can tell.**
   `_real_board_fixture.py`'s 10-net dict and `elec/domain_manifest.yaml`'s
   39 (now 47) declared nets both purported to describe the same netlist's
   voltage domains. Reuse one source of truth (the manifest-derived
   classifier now feeds both `check_domain_partition.py` and the clearance
   path) instead of letting a second copy drift.
5. **A "coverage" or "traceability" gate's pass message must be
   distinguishable from what it would print on zero real input.**
   `check_traceability.py`'s literal failure was that `"all requirements
   are covered"` was true and indistinguishable whether 1, 10, or 0
   requirements had ever been parsed. If a gate's entire purpose is
   proving coverage, its pass message needs the count baked in, not just
   the verdict.
6. **Falsify scope decisions by widening them, and report what widening
   finds even when it's inconvenient.** Both `check_vacuous_gates.py` and
   `check_traceability.py`'s widening passes were done against a stated
   falsifier ("widening finds nothing, so the narrow scope was adequate")
   that did not fire in either case — and the gates were left red/fail-closed
   rather than the scope quietly narrowed back to regain a green check.

## Why This Matters

None of these three gates were lying about what they measured — every one
computed an honest verdict over its own input. The defect in all three
cases was entirely in what that input was, and none of them said so. This
is a cheaper, more common failure than the vacuous-empty-collection case
`check_vacuous_gates.py` already guards against, because a nonempty,
plausible-looking scan count (52 files, 10 nets, 1 sentinel directory)
reads as coverage unless someone asks "out of how many." The worst
instance here — `check_traceability.py` — is a requirements-traceability
gate whose entire job is proving coverage, printing a message
indistinguishable from what it would print with zero real coverage,
because that was almost exactly the true state. `check_domain_partition.py`
shows the fix costs one line of output, printed unconditionally, and was
never the hard part.

## When to Apply

- Reviewing any gate whose scope is an include-list (filename token,
  hand-maintained dict, opt-in marker file) rather than a documented
  default-include/narrow-exclude rule.
- Before trusting any "N passed" or "all covered" message that doesn't
  also state the denominator it was computed against.
- When two independent mechanisms in the codebase both classify the same
  underlying data — check which one is the source of truth and whether the
  other has drifted from it.
- When widening a gate's scope as an audit exercise — state the falsifier
  first ("widening finds nothing new"), and if it doesn't fire, leave the
  gate reporting the real number rather than narrowing back to regain green.

## Examples

```python
# WRONG -- a plausible-looking scope hides its own smallness
SCOPE_TOKENS = ("gate", "valid")
def find_scope_files(packages_dir):
    for src_dir in packages_dir.glob("*/src"):   # never touches scripts/*.py
        for f in src_dir.rglob("*.py"):
            if any(tok in str(f).lower() for tok in SCOPE_TOKENS):
                yield f
# 52 files scanned, 0 violations, "gate passed" -- no line states 52 of what

# RIGHT -- default-include, narrow documented exclude, denominator always printed
def find_scope_files(packages_dir, scripts_dir):
    results = [f for src in packages_dir.glob("*/src") for f in src.rglob("*.py")]
    results += [f for f in scripts_dir.glob("*.py") if f.name != "__init__.py"]
    return results

violations, files_scanned = find_all_violations(...)
console.print(f"Scanned {files_scanned} file(s) in scope (...). {len(violations)} violation(s).")
if files_scanned == 0:
    sys.exit(1)  # a scan of zero files cannot report a meaningful pass either
```

```
# check_domain_partition.py's unprompted denominator -- the reference shape
"Checked 39 declared nets across 2 domains (HV, SELV) ... over 165 compiled
 nets / 170 components"
# printed on every run, pass or fail -- this is the one line every other
# gate in the 2026-07-27 audit was missing
```

## Related

- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
  — the four sibling mechanisms (continue-on-error, default-off flag,
  unwired code path, vacuous `all([])` on an empty collection) that leave a
  gate green without catching its target defect. Subset blindness is a
  fifth: the collection is nonempty and the logic runs correctly over it,
  but the collection itself is a silent minority of the true universe.
- `docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md`
  — documents `check_domain_partition.py` as "in flight" the day before this
  audit; it shipped and is now this audit's own reference example for
  honest denominator reporting.
- `docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
  — the sibling incident this audit's ten-gate catalog extends: a metric
  that cannot observe its target failure mode, rather than one that
  observes only a fraction of it.
- `docs/evidence/2026-07-27-gate-subset-blindness-audit.md` — the full
  per-gate table (16 gates surveyed) and the falsifier that did not fire.
- `docs/evidence/2026-07-27-domain-classification-coverage.md` — the
  10-of-165-net clearance-path finding, the 17-violation full-coverage
  result, and the manifest-expansion fix.
- `docs/evidence/2026-07-27-traceability-scope-fix.md` — the
  1-directory-sentinel finding and the registry-driven scope fix.
- `scripts/check_vacuous_gates.py`, `scripts/check_domain_partition.py`,
  `scripts/check_traceability.py` — the three gates this incident concerns.
