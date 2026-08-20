---
title: "DRC-ceiling re-measurements must land in the same PR as the board change — and why branch protection does not enforce it"
date: "2026-08-19"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a PR touches pcb/temper.kicad_pcb and the drc_ceiling.json re-measurement is being considered as a follow-up"
  - "deciding whether a red run of the Board, Provenance & Requirements Gates job blocks merging"
  - "editing .github/required-checks.json and evaluating whether the Board gate should become a required status check"
  - "auditing why a DRC-ceiling number drifted from its board"
tags:
  - drc-ceiling
  - provenance
  - branch-protection
  - same-pr-discipline
  - required-checks
---

# DRC-ceiling re-measurements must land in the same PR as the board change

`power_pcb_dataset/drc_ceiling.json` records DRC violation counts for
`pcb/temper.kicad_pcb` with a content-hash `provenance` block
(`scripts/check_measurement_provenance.py`). **Any PR that touches
`pcb/temper.kicad_pcb` must re-measure and update `drc_ceiling.json` in the
*same* PR, not as a follow-up.** The re-measurement is logically part of the
board change, exactly like the firmware codegen steps are part of their
manifest edits — it is not a separable chore for someone else to notice
later.

## Why same-PR is load-bearing, not ceremony

`check_measurement_provenance.py` fails closed the moment the board's
content hash no longer matches this file's recorded hash — it already
catches an unpaired board change, on the board-changing PR itself, before
merge. But it does not, by itself, stop that PR from merging. A red run of
the gate is only as good as the merge button's wiring to it.

## The branch-protection state (measured 2026-08-07)

As of 2026-08-07, `main` **does** have branch-protection required status
checks (`gh api repos/<org>/<repo>/branches/main/protection`
-> `required_status_checks.contexts: ["Required Python Tests"]`; this
superseded the earlier "no branch protection at all" state an earlier
version of this document's source text used to cite). But `Required Python
Tests` is an aggregator (`.github/workflows/required-checks.yml`, driven by
`.github/required-checks.json`) polling a fixed, named list of contexts,
and `Board, Provenance & Requirements Gates` — the job the provenance and
DRC-ceiling checks run in — is **not** one of them (see
`required_contexts` in `.github/required-checks.json`).

So the conclusion is sharper than "nothing blocks the merge button": it is
that the specific gate this discipline depends on is not wired into what
does. A red run of this job still does not block merging.

## The consequence

Landing the re-measurement inside the same commit is what actually prevents
the gap (there is no red window to begin with); a separate follow-up PR
only repeats the pattern this discipline exists to stop, and depends on a
person or agent remembering to open it before the board moves again. See
`docs/evidence/2026-07-30-drc-ceiling-remeasurement-cascade.md` for the
cascade incident that motivated this.

## The durable fix (a maintainer call)

Adding `Board, Provenance & Requirements Gates` to `required_contexts` in
`.github/required-checks.json` would wire the gate into the merge button —
but it changes what blocks every PR, not just DRC-adjacent ones, so it is a
maintainer decision, not applied by this document.
