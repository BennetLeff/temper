<!-- provenance: commit=d510f4ede1ce0f3db343776f024c0f8a36085675 dirty=false -->

# Evidence index — 2026-07-29/30 PD3/isolation session

This indexes the analysis and evidence documents produced during the
2026-07-29/30 PD3-creepage / mains-isolation investigation session, which
had scattered across ~15 unpushed local branches (one per sub-question, one
worktree each) before being consolidated onto this branch. **Documents
only** — the same session also produced code (`scripts/measure_cross_domain_creepage.py`,
`scripts/check_copper_net_consistency.py` changes, tests) and board edits
(`pcb/temper.kicad_pcb` F.Fab outline fixes) on some of these branches;
those are deliberately **not** included here and remain on their source
branches for separate review (see the consolidation commit message for the
full list).

Each entry gives the source branch and one-line headline. **Superseded**
entries are marked — the original document is kept as a dated record with a
supersession note at its top pointing to the correction; nothing was edited
or deleted.

## PD3 (12.6mm reinforced creepage) — part selection and feasibility

Investigates whether real, orderable, agency-certified parts can clear the
12.6mm PD3 creepage figure for the isolators currently short of it (C6, K1,
K2, K3, T1, U3, U7).

- [`2026-07-29-pd3-part-selection-survey.md`](./2026-07-29-pd3-part-selection-survey.md)
  (branch `docs/pd3-creepage-part-selection`) — Initial part survey: TE
  `RT114012` found for K2/K3 (+1.22mm margin); TDK `B81123C1222M000` claimed
  to PASS for C6; no ≥12.6mm optocoupler or gate-driver package found for
  U3/U7. **SUPERSEDED (C6 finding only)** — see
  `2026-07-30-pd3-part-selection-k1-c6-t1.md` §2.1.
- [`2026-07-29-pd3-part-selection-verification.md`](./2026-07-29-pd3-part-selection-verification.md)
  (branch `docs/verify-pd3-part-selection`) — Re-verified K2/K3
  (`RT114012`) and C6 (`B81123C1222M000`) against manufacturer-authoritative
  sources; declared C6 "CONFIRMED, more solidly than the survey itself
  established" at exactly 12.600mm. **SUPERSEDED (C6 finding only)** — same
  false-solve correction as above; K2/K3 verification stands.
- [`2026-07-30-pd3-part-selection-k1-c6-t1.md`](./2026-07-30-pd3-part-selection-k1-c6-t1.md)
  (branch `research/pd3-part-selection-k1-c6-t1`) — K1 solved with real
  margin (TE Schrack `RT33K012`, +5.0mm); **corrects** the two docs above:
  C6's 12.600mm "pass" is a zero-margin boundary result that fails
  (12.2mm) at the part's own ±0.4mm lead-spacing tolerance — a false solve.
  A 5.6nF alternative (`B81123C1562M000`) clears creepage with margin but
  its §2.5 rough touch-current estimate flagged it as plausibly exceeding
  the 1.35mA budget. **PARTIALLY SUPERSEDED (touch-current hedge only)** —
  see next entry.
- [`2026-07-30-c6-touch-current-budget-and-part2-routes.md`](./2026-07-30-c6-touch-current-budget-and-part2-routes.md)
  (branch `research/c6-leakage-touch-current`) — Corrected, full
  leakage-current budget. **Reverses** the touch-current hedge above: the
  5.6nF `B81123C1562M000` clears both creepage (+7.1mm) and touch current
  (9-15% headroom) under the corrected accounting. Headline: **PD3 is
  reachable** for C6 via this part, pending the caveats listed in the
  document's own "UNVERIFIED" section.
- [`2026-07-30-pd3-isolation-mechanism-alternatives.md`](./2026-07-30-pd3-isolation-mechanism-alternatives.md)
  (branch `explore/pd3-isolation-mechanisms`) — Explores isolation
  *mechanisms* (not just part swaps) for U7/U3. U7: a real, orderable
  digital-isolator package clears 12.6mm with 1.9mm margin. U3: no
  ≥12.6mm mechanism found in-budget; recommends deletion, with a documented
  (unused) fallback mechanism if deletion is ever reversed.
- [`2026-07-30-pd3-board-expansion-measurement.md`](./2026-07-30-pd3-board-expansion-measurement.md)
  (branch `experiment/pd3-board-expansion-measurement`) — Headline: **NO**,
  expanding the board does not make 12.6mm CP-SAT-feasible, with current
  parts or even after the K2/K3/C6 substitutions — the blocker is
  structural (per-isolator shortfall), not board area. Self-flags the same
  C6 zero-margin/tolerance caveat later confirmed as a false solve above;
  left as originally written since the document's own headline conclusion
  (board expansion doesn't help) does not depend on that caveat's outcome.
- [`2026-07-30-pd3-inter-component-creepage-board-expansion.md`](./2026-07-30-pd3-inter-component-creepage-board-expansion.md)
  (branch `experiment/pd3-inter-component-measurement`) — Measures the 196
  cross-domain creepage violations at 12.6mm on the real board (75 groups /
  68 inter-component / 7 intra-component isolator shortfalls); board
  expansion buys most but not all of the inter-component violations.

## Cross-domain creepage / REQ-SAFE-01

- [`2026-07-29-cross-domain-creepage-pd2-vs-pd3.md`](./2026-07-29-cross-domain-creepage-pd2-vs-pd3.md)
  (branch `docs/req-safe-01-102-triage`) — Pairwise measurement of the real
  cost of moving PD2 (8.0mm) to PD3 (12.6mm): 195 of 21,437 cross-domain
  pairs fail at 12.6mm vs. 0 at 8.0mm on the base board state measured.
- [`2026-07-30-req-safe-01-102-triage.md`](./2026-07-30-req-safe-01-102-triage.md)
  (branch `docs/req-safe-01-102-triage`) — Triages the 102 REQ-SAFE-01
  violations un-masked by the rotation-convention sign fix (PR #479):
  enumerates overlap with the 60-pad-pair tool, classifies remedies, and
  identifies three footprint unknowns (RT1's F.Fab/F.CrtYd fixed in this
  document as documentation-only, no copper/net/constant change).

  Note: two other files originally on branch `docs/req-safe-01-102-triage`
  (`2026-07-29-cross-domain-creepage-rotation-convention.md` and
  `2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md`) are **not**
  duplicated here — they already landed on `main` via PR #479 with
  identical content and are omitted to avoid a path collision.

## Relay / IEC 60335-1 certification

- [`2026-07-29-relay-60335-1-certification-resolution.md`](./2026-07-29-relay-60335-1-certification-resolution.md)
  (branch `docs/relay-60335-compliance-survey`) — No orderable relay across
  every family checked (TE RT1/RT2, TE T9A/OEG, Hongfa HF115F/HF115FK, Song
  Chuan T92, Zettler AZSR) carries an independently-issued IEC 60335-1
  certificate; a bare IEC 61810-1 mark cannot settle the question alone.
  TE `RT114012` remains the best PCB-geometry candidate (12.6mm margin) but
  needs a human compliance decision on the certification gap, not further
  part search.

## PCB compartment / thermal / enclosure

- [`2026-07-30-pcb-compartment-thermal-bound.md`](./2026-07-30-pcb-compartment-thermal-bound.md)
  (branch `analysis/pcb-compartment-thermal-bound`) — Steady-state thermal
  bound for a sealed/partitioned PCB compartment: marginal — viable at
  normal-to-warm kitchen ambient (~50-55°C), not comfortably viable at the
  repo's own worst-case 55-70°C ambient band without added mitigation;
  two die-level parts run hottest.
- [`pcb-compartment-pd2-partition-design.md`](../brainstorms/2026-07-30-pcb-compartment-pd2-partition-design.md)
  (`docs/brainstorms/`, branch `brainstorm/pcb-compartment-pd2-enclosure`) —
  Ranks three concrete partition designs against both the cl. 29.2
  pollution-exclusion test and the thermal bound above; no single option
  wins outright, tradeoffs stated per design.
- [`2026-07-29-001-feat-isolation-barrier-crossing-reduction-plan.md`](../plans/2026-07-29-001-feat-isolation-barrier-crossing-reduction-plan.md)
  (`docs/plans/`, branch `brainstorm/isolation-barrier-crossings`) —
  Requirements-only plan for reducing the *number* of mains<->SELV
  isolation-barrier crossings (deletion-first), not per-crossing footprint
  geometry; largest theoretical reduction direction recorded as the
  recommended focus, pending human decision.

## ZCD / protective impedance

- [`2026-07-30-zcd-protective-impedance-viability.md`](./2026-07-30-zcd-protective-impedance-viability.md)
  (branch `docs/zcd-protective-impedance-analysis`) — Verdict: **reject**.
  Protective impedance is electrically viable in isolation but does not, by
  itself, establish that U3's ZCD crossing can be deleted under this
  board's actual cross-domain proximity; touch-current stays 1.8x under
  budget but 12.6mm achievability is not claimed.

## Net annotation / C27

- [`2026-07-30-c27-net-annotation-stale-briefing.md`](./2026-07-30-c27-net-annotation-stale-briefing.md)
  (branch `fix/c27-net-annotation-resync`) — The C27 board-vs-netlist
  mismatch described in the task brief that spawned this branch does not
  exist on the current board: it existed once, was already found and fixed
  by PR #459 the same day, and the brief was working from a stale
  characterization. Closes the freshness-check gap that let the stale
  finding look current.

## PR triage / merge sequencing

- [`2026-07-30-open-pr-triage-and-merge-sequencing.md`](./2026-07-30-open-pr-triage-and-merge-sequencing.md)
  (branch `triage/pr-sequencing-2026-07-30`) — Read-only inventory and
  conflict matrix of every open PR against `origin/main` post-#479
  (rotation-convention fix): exactly one open PR (#460) substantively
  collides with #479; recommends closing #465/#467 as superseded by #474
  and gives a merge order for the rest.

## Provenance

Every file above carries a `provenance: commit=<sha> dirty=<bool>` stamp
(or the equivalent JSON/comment form) citing the commit it was originally
measured/written at on its source branch — not rewritten to this branch's
history, per `docs/METHODOLOGY.md` Sec 5 and `scripts/check_evidence_provenance.py`.
Those commits are reachable in this repository (verified via `git cat-file`)
because the source branches still exist; they were not rebased or squashed
during consolidation.
