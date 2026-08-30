<!-- provenance: commit=e5539273a01c030c0968006fcf61bb4bedba65be dirty=UNKNOWN -->

# Isolation-barrier-constrained Pumpkin placement, on the reconciled 168-component board

Reproduces and extends PR #1049's finding (`feat/board-sync-and-placement`,
closed for discarding all copper) that isolator **U6 is provably UNSAT
jointly with the other 7** isolators under the PD2/8.0mm barrier — this
time on the reconciled board (7 stale ZCD-opto components removed, 6
OCP-02/pan-probe components added; see the PR description for the full
reconciliation accounting), with an actual re-route following placement,
which #1049 never attempted.

## What's reused vs. new

Reused from `origin/feat/board-sync-and-placement` unmodified:
`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs`'s `"bounded"`
constraint type (one-sided linear bound on a single component's own
coordinate — the wire-format primitive
`temper_placer.placer.cp_sat.isolation_barrier`'s pure geometry helpers
need to express the barrier, since that module's own
`add_isolation_barrier_to_model` is OR-Tools `CpModel`-coupled and not
directly reusable against the standalone Pumpkin binary).

New in this PR: a `"fixed_rotation"` constraint type (pin one component's
`rot` domain variable to an exact 0..3 value, unscaled — the Pumpkin
analogue of `isolation_barrier.py`'s
`model.model_ref.Add(cvars.rot_ref == rot_value)`). `"bounded"`'s
`value_mm` field is always scaled by `to_units` before use; a rotation
index is a unitless selector, not a millimetre quantity, so reusing
`"bounded"` for it would silently scale the pin value by `SCALE` and pin
to nonsense — hence a separate constraint type rather than a `coord: "rot"`
case on `"bounded"`.

## Constraint model

Same two-layer constraint set `_encoder_core.encode_constraints` builds
(netclass-aware cross-class `SEPARATED` constraints via
`generate_netclass_separated_constraints`, backfilled with a flat
courtyard-tau `SEPARATED` pair for every remaining pair), reused directly
from `test_golden_board_pumpkin_real_board.py`'s own `_build_constraints`
— 9,647 netclass constraints + 12,301 courtyard-backfill pairs = 21,948
base constraints over the reconciled board's 168 components.

Isolation barrier added on top: PD2/8.0mm (`MIN_BARRIER_WIDTH_MM`, the
owner-settled bar per `docs/evidence/2026-08-11-pd2-decision-record.md`),
**horizontal** orientation (axis=Y — the orientation where all 8 of this
board's isolators clear the bare 8.0mm bar; vertical leaves at least one
infeasible before packing, matching #1049's finding for the prior
component set). Corridor centered on the board's own Y midline:
`[113.0, 121.0]` mm (board is 152×234mm).

## Isolator set: derived fresh from the reconciled netlist, not copied from #1049

`DomainPartition` classification (pad-level: a component is an isolator
iff it has ≥1 pad on an HV-classified net AND ≥1 pad on an SELV-classified
net, per `elec/domain_manifest.yaml`) on the reconciled board yields:

- **hv_only: 40, selv_only: 109, isolators: 8, unclassified: 11**
- **Isolators: C6, K1, K2, K3, PS1, T1, T2, U6**

This is *not* identical to the isolator set `isolation_barrier.py`'s own
docstring records for the pre-reconciliation board (`{C6, K1, K2, K3, PS1,
T1, U3, U7}`) — reconciliation removed U3 (one of the 7 stale ZCD-opto
components) and the new component set apparently no longer includes U7 as
an isolator either, while **T2** (the new OCP-02 current transformer, a
genuine domain-crossing sensor) enters the isolator set. Deriving this
fresh from the reconciled netlist, rather than assuming #1049's isolator
list still applies, is why T2's presence and U3's absence were caught
rather than silently carried over.

Per-isolator geometric feasibility at the bare 8.0mm bar, horizontal axis
(`evaluate_isolator_feasibility`, all 8 individually feasible):

| Isolator | achievable_gap_mm | chosen_rotation |
|---|---:|---:|
| C6 | 8.000 | 3 |
| K1 | 8.000 | 2 |
| K2 | 12.760 | 1 |
| K3 | 12.760 | 1 |
| PS1 | 35.500 | 3 |
| T1 | 9.100 | 0 |
| T2 | 9.100 | 0 |
| U6 | 8.100 | 1 |

## The joint-infeasibility finding, reproduced

- **All 8 isolators hard-constrained** (straddle + rotation pin), plus the
  full netclass/courtyard/domain-only-component barrier split: **Pumpkin
  returns `infeasible` in 3.17s** — a proof, not a 30s timeout.
- **Relaxing U6 alone** (skip its rotation pin and pad-cluster straddle
  constraint; U6's own domain-only pads are unconstrained, per
  `isolation_barrier.py`'s `relax_isolator_straddle` mechanism) — the
  identical model, otherwise unchanged, including the other 7 isolators
  still hard-constrained — **solves `optimal` in 2.6s.**

This independently reproduces #1049's central claim (U6 provably UNSAT
jointly with the other 7) on the reconciled board and a from-scratch
constraint build, not a copy of that PR's numbers.

## Write-back and validation

Positions written via the (now origin-corrected — see
`docs/evidence/2026-08-11-board-origin-write-path-fix.md`)
`_apply_placements_to_pcb(..., board_origin=board.origin)`, over a
copper-stripped board (existing copper was stripped before reconciliation
— see the PR description). Round-trip oracle: **PASS, 168 components, 521
pads verified** (checked against `board_origin`-adjusted absolute
positions, matching what was actually written — the oracle recomputes its
own expected geometry from whatever positions dict it's handed and does
not independently know about `board_origin`).

`scripts/check_board_containment.py`: **2 violations** out of 527 checked
pads (`L1` pad 3 fully outside the outline near the top edge; `R60` pad 1
straddling the bottom edge) — both small, individual near-edge placement
imperfections (a box-approximation CP-SAT model's edge-margin constraint
applies to the component's bounding box, not each pad's own exact copper
extent), not the systemic ~20mm-off-everything signature #1049's
un-fixed write path would have produced. Reported as a genuine, minor
residual, not silently ignored.
