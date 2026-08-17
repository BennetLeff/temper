---
module: pcb
tags: [netclass, hv, creepage, kicad-pro, classification, drc]
problem_type: bug
date: 2026-08-16
---

# HV netclass assignment fix — 8 nets unassigned in kicad_pro (2026-08-16)

**Status**: merged into `fix/classification-and-fab-rules` (commits
e7b47b424, 31b2d275e), base `origin/main` @ 593d9ab24.

## Defect shape

`elec/domain_manifest.yaml` declares 27 nets under the `HV` domain (the
hand-reviewed SSOT for domain membership). 19 of them had entries in
`pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` — the mapping
`kicad-cli`'s DRC actually reads — and 8 did not:

| net | correct class | why |
|---|---|---|
| `discharge.k_dis1-no` | HighVoltageSignal | same contact bank as already-declared `k_dis1-nc` |
| `discharge.k_dis2-no` | HighVoltageSignal | same contact bank as already-declared `k_dis2-nc` |
| `discharge.r_dis1a-p2` | HighVoltageSignal | half-bus-1 bleed string mid-node, both ends HV |
| `discharge.r_dis2a-p2` | HighVoltageSignal | half-bus-2 bleed string mid-node, both ends HV |
| `discharge.r_snub1-p2` | HighVoltageSignal | K2 NC-COM snubber mid-node, both ends HV |
| `discharge.r_snub2-p2` | HighVoltageSignal | K3 NC-COM snubber mid-node, both ends HV |
| `hb-gnd` | HighVoltage | compiled name of `hb.dc_bus.hv_minus` = DC_BUS_RTN analogue |
| `input` | HighVoltageSignal | UCC21550 LS driver output pre-rg_on, analogue of `hb.power_loop.q_high-g` |

Unassigned nets fall through to KiCad's `Default` class (0.2mm clearance,
0.0mm creepage) — invisible to every HV↔LV clearance/creepage rule. The
8 nets were also absent from `TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`), the
Python-side classification SSOT, so `scripts/check_hv_netclass_coverage.py`
(PROPERTY 1 + 3) was red on `main` with exactly these 8 nets.

## Measured DRC effect (the surprising half)

The naive expectation — "fixing classification makes the false 12.6mm
creepage charges disappear" — is only half the story. Measured on
`origin/main` @ 593d9ab24 (kicad-cli 10.0.5, custom DRU regenerated from
`scripts/generate_kicad_dru.py`):

| | before fix | after fix | delta |
|---|---|---|---|
| creepage errors mentioning the 8 nets | 34 | 53 | — |
| creepage, total (one sample) | 295 | 314 | +19 |

Breakdown of the +19:

* **34 false charges cleared**: pairs between two HV nets (e.g. `hb-gnd`
  vs `+15V_LS`, `discharge.k_dis2-no` vs `DC_BUS_RTN`) that DRC read as
  HV↔Default-LV and charged 12.6mm against. Same-domain after the fix, no
  rule fires.
* **53 real violations surfaced**: pairs between the 8 nets and genuine
  LV neighbours (`+3V3`, `RTD_SDI`, `SHUTDOWN_N`, `GND`, ...) that were
  invisible before because Default-LV ↔ LV pairs trip nothing. These are
  REAL HV↔LV crossings (U6's `hb-gnd`/`input` pins 0.5-8mm from SELV
  copper) that the misclassification was masking — an instance of the
  handoff's "instruments that under-report" mechanism (mechanism 4).

So the fix does NOT reduce the DRC creepage count — it makes the count
honest. 295 → ~314 is the true number with correct classification. This
is the "already-investigated, attributed, deliberate change" category of
ceiling rise; the ceiling update in `power_pcb_dataset/drc_ceiling.json`
carries a `Ceiling-Approval:` trailer and 120-sample measured-live
provenance (see the `_march` entry).

## What was changed

1. `packages/temper-placer/src/temper_placer/core/design_rules.py`:
   8 entries added to `TEMPER_NET_ASSIGNMENTS` (classes above, with
   per-net wire-tracing comments citing the manifest).
2. `pcb/temper.kicad_pro`: same 8 entries appended to
   `net_settings.netclass_assignments` (107 total now).

`scripts/sync_kicad_netclass_assignments.py --write` could not be used:
it refuses to run at all because the pre-existing PWR_RTN protection now
"resolves to a declared kicad_pro netclass" (HighVoltage) — a human
decision per its own docstring, unrelated to this change. The kicad_pro
edit was made by hand in the sync script's exact output format.

## Verification

`scripts/check_hv_netclass_coverage.py`: PROPERTY 1 (unclassified HV
nets) 8 → 0; PROPERTY 3b (unassigned in kicad_pro) 8 → 0; PROPERTY 3c
(wrong safety category) 0. The gate's only remaining failures are the two
pre-existing SELV-domain gaps (`s1`, `safety.ocp2-line`) — documented,
out of this task's scope.

Note: adding these assignments does NOT touch `pcb/temper.kicad_pcb` (the
board file) — its content hash is unchanged, so the DRC ceiling's input
hash remains valid.

## Follow-ups

* The 2 SELV-domain nets (`s1`, `safety.ocp2-line`) remain unassigned in
  kicad_pro (PROPERTY 4 red). Their manifest entries trace them as the
  SELV twin of `hb-gnd` (T2's secondary, feeds the TLV3201 comparator);
  they need LV-class assignments in a separate change.
* `scripts/sync_kicad_netclass_assignments.py` remains blocked on the
  PWR_RTN/CGND protection — an owner decision (order-of-magnitude blast
  radius, documented in its module docstring).

---

# Part 2 — fab-rule violations (annular_width, holes_co_located, via_dangling)

Routed-board DRC (kicad-cli 10.0.5, `--all-track-errors`, DRU regenerated
from `scripts/generate_kicad_dru.py`), before → after on routes from the
same base (origin/main e81196c87 + this branch's classification fix):

| family | task baseline (capstone route) | my route pre-fix (v1) | my route post-fix (v2) |
|---|---|---|---|
| annular_width | 68 | 69 | **0** |
| holes_co_located | 60 | 48 | **0** |
| via_dangling | 44 | 95 unfilled / 11 refilled | 95 unfilled / 11 refilled |

## annular_width 68 → 0 (fixed)

**Root cause — three missed via-default homes.** The 2026-08-13 fab-floor
sweep raised every via template to a 0.3mm annular ring (≥ the board's
`min_via_annular_width` 0.254) but missed three homes, two of them live:

1. `configs/netclass_rules.yaml` `HighVoltageSignal`: 0.8/0.4 (0.2mm ring)
   — the file the router consumes at route time (69 of the capstone
   route's vias were HighVoltageSignal-classed). `TEMPER_NET_CLASSES` in
   `core/design_rules.py` already had 1.0/0.4 — the two homes had drifted
   (handoff mechanism 1). Raised to 1.0/0.4; `pcb/temper.kicad_pro`'s
   class template fixed to match (DRC reads the board's actual via
   geometry, the class template is a GUI default — kept consistent so the
   homes cannot disagree again).
2. `io/_parse_nets.py` `default_via_diameter/default_via_drill` 0.8/0.4 —
   the defaults `parse_kicad_pcb` bakes into `pcb.design_rules`, which the
   route's via placement actually reads for nets with no netclass
   assignment (34 annular violations on my route, all blind vias on
   unassigned nets: safety.ocp2-line, sw, boot, fb, i2c_scl_ui...).
   Raised to 0.9/0.3.
3. `netclass_rules_manifest.yaml` `via_diameter` default 0.6 → 0.9 (the
   netclass_rules_gen.py model default + temper-drc-rs board.rs, both
   regenerated via `scripts/gen_domain_models.py`) — the fallback the
   temper-design-bundle loader uses when a class omits via_diameter
   (0.15mm ring). `via_placement.place_vias` direct-caller defaults
   raised the same way.

**Gate fix**: `scripts/check_fab_capability_floor.py` gains P2b
(netclass_rules.yaml — P2 only checked design_rules.py, which is how the
drift stayed green for months) and P2c (io/_parse_nets.py's via
defaults). Mutation tests pin the exact pre-fix shapes. The gate now
covers every home that can size an emitted via.

## holes_co_located 48 → 0 (fixed)

**Root cause — two via-placement defects in `router_v6/via_placement.py`
`_place_vias_for_path`** (measured on my route: 12 stacked positions, 25
vias):

1. **Stacked duplicate vias**: the pathfinder's `via_positions` can
   contain the same (x, y) several times (consecutive waypoint segments
   anchoring at a shared point / a 3D search doubling a transition),
   emitting N byte-identical vias at one position. KiCad DRC flags every
   coincident drilled hole pair as `holes_co_located`. Fix: dedupe by
   (position rounded to 4dp, unordered layer pair) — one via carries the
   identical electrical function, the extras were pure DRC debt.
2. **Vias dropped inside same-net THT pad holes** (12 measured): the
   plated THT hole already spans every layer, so the via adds nothing and
   KiCad flags the coincident holes. Fix: new `tht_holes_from_pcb(pcb)`
   helper (mirroring `_ground_plane.py`'s own hole collection, so the two
   emitters cannot drift) threaded through `place_vias`/`_run_stage5`;
   vias whose position falls inside a same-net THT pad hole are skipped
   (fail-closed: connectivity cannot regress).

The randomized 300-path differential sweep in
`test_via_clearance_tier2_rust_differential.py` caught the dedupe as the
only divergence — re-pinned per the PR #1198 convention: the frozen
oracle stays verbatim at the pin; the parity claim is now "live == frozen
reference after the documented dedupe", with `set(deduped) == set(oracle)`
asserted to prove the dedupe removes ONLY duplicates. 5 new unit tests in
`test_via_placement.py`, 3 in `test_ground_plane.py`.

## via_dangling — measurement artifact, documented (not a router defect)

**The repo's DRC runner does not pass `--refill-zones`** (verified in
`_drc_api.run_drc`, and confirmed by minimal reproductions: two same-net
pads joined only by a KiCad-authored thermal zone report "unconnected"
without refill). Every zone connection is therefore invisible to every
DRC measurement this repo has ever taken — the ceilings, the gates, the
routed-board diagnostics. Consequences, measured:

* **With the honest refilled measurement**, my routed board's
  via_dangling is **11** (not 95): the ground-plane/power-island drop
  vias ARE connected to the plane; the 95 were the unfilled artifact. The
  committed board's 25 via_dangling are the same shape.
* **Refilling also surfaces what the unfilled measurement hides**:
  committed-board creepage 289 → **483** (+194 real violations the
  ceilings have never counted), shorting 183 → 190, and a new category
  `isolated_copper` 116. This is the handoff's "instruments that
  under-report" mechanism at the measurement-runner level.
* The 11 residual refilled dangling vias are gnd drop vias in spots where
  the carved plane genuinely does not reach them (inside clearance-carved
  holes near other components' halos) — 7% of vias, warning-level.

**Why this task did not change the runner**: adding `--refill-zones` to
`run_drc` would re-base EVERY ceiling number (creepage +194 on the
committed board), change the nondeterminism characterization, and roughly
double per-sample runtime — a deliberate measurement-methodology change
with a full ceiling re-baseline, which belongs to an owner decision (like
the PWR_RTN classification), not a fab-rules task. The finding is
recorded here with the measured numbers; the router-side pour-strict fix
below is the part that is unambiguously correct either way.

**Router-side improvement that DID land** (`_ground_plane.py`): the
drop-via search previously fell back to a keepout-clear-only point when
no pour-inside point existed — a via outside the carved In1.Cu pour
touches no plane copper and dangles. The fallback is removed when a pour
region exists (the pad keeps its F.Cu MST backbone connection either way,
so the skip costs no connectivity the fallback via would have provided —
it only removes a DRC violation). 3 new unit tests pin the behavior
(pour-inside used, no fallback outside pour, no-pour keeps old behavior).

## Fab-rule verification method

Each route: `route_board.py` from the branch HEAD (~7 min, 24-core host),
then `kicad-cli pcb drc --all-track-errors --refill-zones` on the output
(the refilled measurement is the honest one — see above). Final route v2:
annular_width **0**, holes_co_located **0**, via_dangling **11 (refilled)**,
creepage 139, shorting 49, hole_clearance 19 — the fab families the task
named are closed; the remaining categories are the pre-existing
placement/DRU debt documented in the ceiling's saturation_hazard notes.
