---
title: "A plan's 'single home' premise and its headline number are claims, not facts — verify both against the code and the artifacts before building on them"
date: "2026-09-17"
category: best-practices
module: zapote
problem_type: best_practice
component: workflow
severity: high
applies_when:
  - "a plan asserts that some term or rule 'lives in one place', or names the module that owns it"
  - "a plan quotes a headline number and derives scope, thresholds, or unit boundaries from it"
  - "a plan's acceptance threshold is stated as a range without a committed measurement or derivation behind it"
  - "reviewing or enriching a requirements-only plan into an implementation-ready one"
tags:
  - plan-verification
  - single-source-of-truth
  - duplicated-implementation
  - acceptance-threshold
  - provenance
  - planning-workflow
---

# A plan's "single home" premise and its headline number are claims, not facts

## Context

A requirements-only plan set out to replace an input bridge's assumed
forward-drop band with a curve-integrated loss. Two of its premises were false,
and both were only caught when planning went to the code.

**Premise 1 — "the constant-drop term lives in one place."** The plan's
requirement said the integrated loss "replaces the constant-drop term in its
existing location", and a key decision asserted the premise was implemented in
one place. Grep found **four** bridge-loss homes:

| Home | Form |
| --- | --- |
| `zapote-harness/src/pfc_loss_budget.rs:577` | constant `2.0 * 1.05 * rectified_mean_a` |
| `zapote-harness/src/pfc_candidates.rs:213` | `bridge_constant_drop_w` delegating to `diode_w` |
| `zapote-thermal/src/joint_model.rs:567` | `fixed_vf_loss_estimate_w` |
| `zapote-thermal/src/physical_model.rs:546` | already integrated linear `V(i)` |

Three were constant-drop forms; one was already current-dependent, which also
made the plan's "the constant-drop premise" wording imprecise. A fifth home was
waiting: the shared kernel the plan wanted to add, if placed in the module that
merely *consumed* the term, would have become one more.

**Premise 2 — the headline number came from the module the plan named.** The
plan quoted **28.30 W** as the bridge term and derived its comparison from it.
That figure is produced by `pfc_loss_budget.rs`, not by the `pfc_candidates.rs`
screen the plan's scope was written around. The two are different consumers with
different keys and different test coverage; correcting one would not have moved
the other.

**Premise 3 — the acceptance bar had no source.** The plan carried a
"5–15 W candidate difference" bar that appears in no committed measurement,
closeout, or screen output. The committed anchors were different and much
tighter: the bridge term at 28.30 W against the switching term at 26.76 W —
about **1.5 W**. A threshold with no provenance makes the plan's central
pass/fail decision unfalsifiable, and here it was also wrong by an order of
magnitude in the permissive direction.

## The pattern

**A plan's structural premises are testable, and the cheap tests are greps.**
"Lives in one place", "is the only caller", "is produced by X" are all
checkable against the code in seconds. When they are wrong, every unit built on
them inherits the error: here, scope boundaries (which consumers to edit),
requirement wording (R6's "exactly one owner" was literally unsatisfiable while
two out-of-scope homes remained), a definition-of-done clause, and the
verification gate were all downstream of premises nobody had checked.

**A headline number's provenance is part of the number.** Two modules can
compute a superficially identical quantity under different keys and different
conditions. Quoting the value without binding it to its producer means the
plan's scope and its arithmetic can point at different code, and a change that
satisfies one leaves the other untouched — the ordinary two-homes drift,
introduced at planning time rather than at implementation time.

**An acceptance threshold without a committed source cannot fail.** If the bar
is invented, no result can violate it; the plan will "pass" regardless of what
the work finds. Repo policy already says a figure must be measured or inherited
and never assumed; that rule binds plan thresholds too, not only computed terms.

**A discrepancy between two models is conditional, not a correction factor.**
A related finding from the same arc: an independent vendor model disagreed with
the analytic model by ~1.45× on one switching term. Reporting it as a "~30%
correction" would have licensed scaling unrelated quantities. The honest form is
the ratio at the tested device and conditions, its direction stated explicitly
(the analytic model predicted *more* loss, so it was pessimistic about
efficiency, not optimistic), and nothing extrapolated beyond what was compared.

## Guidance

1. **Grep before asserting a home.** A plan that claims single ownership should
   name the owner *and* the count it verified. "One home" written without a grep
   is a guess; in this case four homes existed and one was already the thing the
   plan proposed to add.
2. **Bind a headline number to the file that produces it.** Quote the producing
   module and the key, not just the value. When scope is written around one
   consumer, check whether the number in the prose came from another.
3. **Give every acceptance threshold a committed provenance.** Cite the
   measurement, closeout, or derivation it came from; if none exists, compute
   one from committed anchors before the plan is marked implementation-ready.
   A bar nobody can fail is worse than no bar.
4. **Scope a single-owner requirement to the consumers the unit will actually
   touch,** and name the exempt ones with a follow-up. An absolute "no consumer
   keeps a private model" that the plan itself exempts two of is unsatisfiable
   and invites a reviewer or implementer to either widen scope or sign off
   falsely.
5. **Classify a requirement's wording as a claim.** "Specifies a measurement"
   and "performs a measurement" are different requirements with different
   deliverables; a document-only unit cannot discharge an executed-measurement
   requirement.
6. **Report a model-versus-model discrepancy as a conditional finding.** State
   the ratio, the device and conditions tested, and the direction. Never convert
   it into a factor applied elsewhere.

## Related

- `docs/solutions/best-practices/datasheet-curves-hide-in-plots-raster-traces-can-mislead-2026-09-17.md`
  — the measurement half of the same arc.
- `docs/plans/2026-09-17-001-feat-pfc-bridge-loss-pinning-plan.md` — the plan
  these corrections landed in, with the Product Contract preservation note
  recording the R6 re-point and the R10 rebase.
- `zapote/power-entry/loss-budget/campaign/LOSS-ACCOUNTING-AUDIT.md` — the
  audit that produced the committed 28.30 W / 26.76 W anchors.
