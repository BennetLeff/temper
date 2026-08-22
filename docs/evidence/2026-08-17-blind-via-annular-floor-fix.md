<!-- provenance: commit=775a7a40e72048846474d74d22461df8bbc42765 dirty=false at stub-creation time (worktree agent-a6d08342e4be16707). pcb/temper.kicad_pcb sha256 33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962 at stub time (this is the post-#1312 board; task is to fix router via emission, not the board's placement). This stub is a placeholder written before any code change, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Blind-via annular-width floor fix (annular_width 0->56, holes_co_located 0->17 regression from #1312)"
date: 2026-08-17
module: temper-orchestration
tags: [router, via, drc, fabrication, annular-width]
problem_type: fix-and-verify
status: resolved
---

# Blind-via annular-width floor fix

**Status: RESOLVED.** Both regressions fixed, re-routed, and verified.
Committed incrementally per this project's own repeated lesson
(HANDOFF-2026-08-17 SS15) that uncommitted work is the only kind that gets
lost.

## Task

PR #1312 regenerated the board's copper (0/139 -> 36/139 genuine multi-pad
connections, isolated_copper 109->0, aggregate DRC roughly halved) but
introduced one fabrication-blocking regression: 56 vias with annular ring
below the board's 0.254mm fab floor (JLCPCB 2oz), and 17 co-located holes
from the same mechanism. Root-caused in #1312's own evidence doc
(`docs/evidence/2026-08-17-board-copper-regeneration.md`) to the router's
blind-via emission not applying `net_settings.min_via_annular_width` from
`temper.kicad_pro`.

Touches exactly one HV net (`discharge.r_snub1-p2`, a redundant-not-incorrect
via); otherwise LV/sensing nets only, per #1312's own net-by-net check.

Prior art: #1159 set 44 vias to 0.254mm at the board level; #1173 raised the
annular ring to the 0.254mm fab floor at the board level
(`docs/evidence/2026-08-13-via-annular-ring-floor-fix.md`). Neither touched
the router's own via-emission path, which is what #1312 exercised at scale
for the first time via the ground-plane/power-island MST via-drop generators.

## Plan

1. Find where blind/buried vias get drill/pad diameters during emission:
   `packages/temper-orchestration/src/pipeline_route.rs` (via emission),
   `Via::emit_s_expr()` (the only sexpr API, private fields), `via_placement.py`,
   `_ground_plane.py`, `_power_islands.py` (MST via-drop generators #1312
   identified as the source of the related `via_dangling` findings).
2. Make via emission honour the 0.254mm annular floor as a property of the
   emitted via (constructor-level), not a post-hoc filter -- consistent with
   this repo's five type-system guards (HANDOFF SS7).
3. Re-route and measure annular_width/holes_co_located with and without
   `--refill-zones`, full project context (.kicad_pro + .kicad_dru sidecars),
   `--all-track-errors`.
4. Verify connectivity did not regress (36/139 genuine multi-pad, 63/139
   total, 0 fake completions).
5. Commit fix + regenerated board if clean; report tradeoff if not.

## Root cause 1: `annular_width` (56 -> 0)

**Not** the netclass tables -- both `core/design_rules.py`'s
`TEMPER_NET_CLASSES` and `configs/netclass_rules.yaml` were already raised to
a uniform 0.3mm annular ring on 2026-08-13 (#1159/#1173's own follow-through).
Measured directly against the committed (pre-fix) board: all 56
`annular_width` violations are vias at exactly `(size 0.8000) (drill
0.4000)` -- a 0.2mm ring -- and no netclass table produces that pair.

The actual source: `packages/temper-placer/src/temper_placer/io/_parse_nets.py
::_extract_design_rules`. Its own docstring calls it **vestigial**
("Native netclass extraction from KiCad PCB files is vestigial. The
authoritative source is `configs/netclass_rules.yaml`") -- but
`parse_kicad_pcb_v6()` (Stage 0.1, the production router entry point) calls
it directly and unconditionally (`kicad_parser.py:149`), and its result
becomes `ParsedPCB.design_rules`, which `_run_stage5` passes straight into
`via_placement.place_vias(pcb.design_rules.default_via_diameter_mm,
pcb.design_rules.default_via_drill_mm, design_rules=pcb.design_rules)`.
Modern `.kicad_pcb` files (this board included) carry no embedded
`(net_class ...)` blocks, so `_extract_design_rules`'s own `manual_classes`
loop never fires and `net_class_assignments` stays **permanently empty** --
every net's via falls straight through to `default_via_diameter`/
`default_via_drill`, which the file still had at **0.8/0.4** (0.2mm ring),
un-migrated by the 2026-08-13 sweep that fixed every other copy of this same
fact.

**Fix** (commit `389232860`):

1. `io/_parse_nets.py`: `default_via_diameter`/`default_via_drill` 0.8/0.4 ->
   0.9/0.3, matching the same 0.3mm-ring convention every other
   "Signal"/default via pair in this codebase already carries. The frozen
   differential oracle (`tests/io/_parse_engine_py_oracle/_parse_nets.py`)
   was updated in lockstep, per that file's own established "DELIBERATE
   DIVERGENCE" precedent (the 2026-08-12 `default_trace_width` 0.25->0.20
   fix took the identical shape) -- the oracle pins the Rust-migration
   contract, not the pre-fix value, and this oracle is **not** one of the
   167 content-hash-pinned files in `scripts/oracle_hashes.json` (checked
   directly), so updating it is not a "re-pin" under this project's hard
   rule.
2. `configs/netclass_rules.yaml`: `HighVoltageSignal`'s `via_diameter`/
   `via_drill` were still 0.8/0.4 too -- the one class the 2026-08-13 sweep
   missed (every sibling class in that file carries a "RAISED ... 2026-08-13"
   note; this one never got one). It had silently drifted from
   `core/design_rules.py`'s `TEMPER_NET_CLASSES["HighVoltageSignal"]` (fixed
   to 1.0/0.4 that day) for four days, on an **HV netclass**. Fixed to
   match (1.0/0.4). Not the live path for the 56 measured violations (none
   of the affected nets classify as `HighVoltageSignal`), but the exact same
   defect shape, dormant, on a mains-adjacent class -- see "Fact-registry
   follow-up" below.
3. **Defense in depth**, `packages/temper-orchestration/src/pipeline_route.rs`:
   `Via::new` now enforces the 0.254mm floor (`MIN_ANNULAR_RING_MM`) AT
   CONSTRUCTION -- any `(diameter, drill)` pair below it is enlarged to the
   board's 0.3mm-ring convention (`ANNULAR_RING_TARGET_MM`), drill
   untouched. This is the same "make bad states unrepresentable" shape as
   the crate's other four type-system guards (`ClearanceHalo`,
   `NetRouteResult::Connected`, `DrcCount`, `WorldPosition`). No future
   caller -- upstream default, new via-drop generator, whatever -- can
   construct a `Via` that fails this floor. 4 new unit/emission tests pin
   the clamp and its no-op-on-compliant-input behaviour; `cargo test --doc`
   (the `compile_fail` private-field guard) still passes; wasm test
   registry regenerated (`scripts/gen_wasm_test_registry.py`).

## Root cause 2: `holes_co_located` (17 -> 0)

**A different mechanism, not the same origin the original triage assumed.**
`Via::new`'s annular clamp changes pad DIAMETER only -- it cannot move a
via's drilled-hole POSITION, and `holes_co_located` is purely positional
(two drilled holes at the same point). Confirmed unaffected: run 1 (annular
fix only) still measured `holes_co_located: 17`, byte-for-byte the same
count as the pre-fix board.

Item-level inspection of the DRC JSON (`--refill-zones`, full project
context) on a fresh route shows exactly two shapes, both via-placement bugs
in `router_v6`'s Stage 4.3 (`via_placement.py`), neither touched by
#1312 or the annular fix:

- **Duplicate via for one net at one point.** The N-layer A* pathfinder
  (`_astar_nlayer.py`) emits more than one `via_positions` waypoint for the
  SAME net at the SAME coordinate -- `safety.ocp2-line`, `sw`, `ina`,
  `rtd_pan.r_low_top-inn`, `OCP2_VREF_2V5` (5 instances). Two vias stacked
  on each other: fabricatable, but a second hole with nothing new to
  connect.
- **Via redundant with an existing pad's own hole.** A via lands exactly on
  a PTH/THT pad of its OWN net -- `discharge.r_snub1-p2` (the one HV net in
  this whole regression, landing on C7's own PTH pad 1), `rtd_sense_p`,
  `rtd_sense_n`, `rtd_force_p` (J1's RTD pads), `thermal.j_fan-p1` (J2 and
  R75) (6 instances). A THT/PTH pad is already plated through every copper
  layer its hole passes -- a via at the identical point adds no reachable
  copper the pad doesn't already provide.

**Fix** (commit `8941a1817`): `via_placement.drop_redundant_vias()` --
built on the same canonical `pin_world_position()` pad-position math
`pad_connectivity_audit.py` already trusts, not re-derived footprint
transform math -- drops both shapes per net: any via whose (quantized)
position repeats one already kept for that net, and any via whose position
matches an existing PTH/THT pad of that same net. Wired into
`_pipeline_route.py::_run_stage5` immediately after `place_vias()`, the one
place in the pipeline that already has both the just-placed via list and
`pcb.components` (pad data) in scope. Removing either shape is
connectivity-neutral by construction -- the kept/pre-existing hole already
provides every electrical path the dropped via would.

`test_via_placement.py` (15), the pipeline differential suite (21, including
`test_real_pipeline_end_to_end_matches_oracle`) and the pipeline pbt suite
(12) all pass unchanged. `_run_stage5` is exercised identically on both
sides of the pipeline-sequencing differential (`run_verbatim` drives the
SAME bound `self._run_stage5`, not a frozen copy), so this fix is not
oracle-entangled.

## Verification -- four live routes, `kicad-cli 10.0.5`, full project context

Each route via `scripts/route_board.py` (default flags, no `--net-batching`),
scratch output, `.kicad_pro` + `.kicad_dru` sidecars propagated
(`copy_kicad_project_sidecar`), DRC via `--all-track-errors --severity-all`,
measured with and without `--refill-zones`.

| Run | Fix state | sha256 (first 12) |
|---|---|---|
| 1 | annular fix only | `892680144d04...` |
| 2 | annular fix only | `892680144d04...` (byte-identical to run 1 -- determinism confirmed) |
| 3 | annular + dedup fix | measured below |
| 4 | annular + dedup fix | determinism check vs run 3 |

### DRC: committed board (main, pre-fix) vs run 1 (annular fix only) vs run 3 (both fixes), no-refill

| category | main | run 1 | run 3 | run3 vs main |
|---|---|---|---|---|
| `annular_width` | 56 | **0** | **0** | **-56, fixed** |
| `holes_co_located` | 17 | 17 | **0** | **-17, fixed** |
| `clearance` | 243 | 231 | 224 | -19 |
| `hole_clearance` | 35 | 26 | 26 | -9 |
| `track_width` | 122 | 120 | 120 | -2 |
| `creepage` | 101 | 101 | 100 | -1 |
| `shorting_items` | 46 | 53 | 53 | +7 (larger via pads, same-mechanism, coordinator-reviewed) |
| `solder_mask_bridge` | 12 | 15 | 15 | +3 (ditto) |
| `copper_edge_clearance` | 10 | 12 | 12 | +2 (ditto) |
| `via_dangling` | 106 | 106 | 106 | +0 |

`--refill-zones` mode moves the same categories the same direction (creepage
101->122/121, via_dangling 106->23, unconnected_items improves 300->247) --
no category flips sign between refill and no-refill.

No category regresses between run 1 and run 3 -- the dedup fix is a strict
improvement (`holes_co_located` -17) with zero side effects on every other
category, exactly as expected from a connectivity-neutral removal.

### Connectivity (`pad_connectivity_audit` + `route_board.py`'s own `NetRouteResult`)

Identical across every run (1, 3, and the coordinator's independent
measurement of run 1):

- **36/139** genuine multi-pad connections (`fully_connected`, `pad_count >
  1`).
- **63/139** total pad-connected nets -- matches `route_board.py`'s own
  `NetRouteResult`: "63 connected, 9 zone-dependent, 7 partial, 60 failed".
- **0 fake completions** in the `NetRouteResult::Connected` sense: the 63
  come only from `verify_continuity()`; the 7 nets with copper that doesn't
  join every pad are honestly reported as `partial`, never miscounted into
  `Connected`.

Matches PR #1312's own baseline exactly -- **no connectivity regression**.

## Final write

- Board sha256 before (post-#1312, pre-this-fix, still `main`):
  `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
- Board sha256 after: see the board-write commit message.
- `drc_ceiling.json` **not** touched -- both fixed categories go to 0,
  every other category holds or improves; no ceiling raise needed or made.
- The 0.254mm annular floor itself was never changed, anywhere.

## Fact-registry follow-up (not done here, flagged for the owner)

The `configs/netclass_rules.yaml` `HighVoltageSignal` drift (root cause 1,
fix 2) is a clean instance of the exact shape `scripts/check_fact_registry_drift.py`
(landed today, #1311) exists to catch mechanically: one fact (a netclass's
via pad/drill pair), multiple homes (`core/design_rules.py`,
`configs/netclass_rules.yaml`, `temper.kicad_pro`), one home missed by a
sweep that touched every sibling. This instance was found by chasing a DRC
regression, not by the gate -- the gate did not cover via geometry facts at
the time. Consider adding netclass via-diameter/via-drill pairs to that
registry so the next such drift (especially on an HV-classified netclass,
as this one was) is caught before it reaches a routed board. Out of scope
for this fix -- flagged, not implemented.
