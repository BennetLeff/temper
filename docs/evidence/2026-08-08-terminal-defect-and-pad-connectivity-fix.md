<!-- provenance: commit=cda628a898d33459069d983995ff9e4a96933772 dirty=UNKNOWN -->

# Fix: wrong-pad routing terminals, and pad connectivity as the completion metric

**Date:** 2026-08-08

**Task:** Fix the Stage 3/4 defect where a net's routing terminal can land
on a pad belonging to a different net (found by the pad-connectivity audit
on `spike/nlayer-via-astar`, evidence:
`docs/evidence/2026-08-08-nlayer-via-astar-spike.md`), and promote pad
connectivity to the project's completion metric.

## Safety finding, stated first

**No confirmed HV↔SELV crossing.** Checked all 28 affected nets (§1)
against `elec/domain_manifest.yaml`'s explicit domain declarations. Two
pairs are same-domain HV↔HV miswires (`GATE_HS`↔`hb.power_loop.q_high-g`,
`tank-out`↔`tank.c_tank1-p2`) -- wrong copper, but not an isolation-barrier
breach. No pair combines an explicitly-declared HV net with an
explicitly-declared SELV net.

One pairing is flagged for human review rather than confirmed: the net
`boot` (undeclared in the manifest, no exact-literal entry) collides with
`+15V`, which the manifest explicitly declares SELV. By component role
(a 2-pin passive between a half-bridge gate-driver IC and what is very
likely a bootstrap capacitor), `boot` is plausibly an HV-domain floating
node, but the manifest's stated convention is "every entry is an exact,
literal net name... never inferred from a naming convention," and `boot`
has no literal entry either domain's list. This report does **not** claim
`boot` is HV -- that would be exactly the kind of naming-based inference
the manifest instructs against -- but flags it because the alternative
(silently treating an unclassified net as "presumably fine") is the wrong
default for a mains-connected board. Recommend a human with the schematic
add `boot` to the manifest under its correct domain.

Several other collisions pair a declared-HV net (`ac_l`, `PWR_RTN`,
`+170V_BUS`, `discharge.k_dis2-nc`) against an undeclared net whose name
suggests it is an internal node of the same HV divider/snubber chain
(`power_in.r_zcd_top1-p2`, `discharge.r_snub1-p2`, `discharge.r_dis1a-p2`,
`discharge.r_dis2a-p2`). These read as same-domain (HV-internal) miswires
on inspection, not isolation breaches, but are listed as undeclared in
§1's table rather than asserted, for the same reason as `boot` above.

## 1. Affected-net enumeration

Two independent, real defects were found and fixed. Both are measured
directly against `pcb/temper.kicad_pcb`, not hypothesized.

### 1a. The mechanism that actually drives production behaviour: `_net_pad_positions` ignored component rotation

`_pipeline_grid._net_pad_positions` (feeding both `fallback_channel_path`
and `expand_channel_path_terminals` as the router's "ground truth" pad
positions) computed `comp.initial_position + pin.position` directly,
never applying `comp.initial_rotation`. `pin.position` is the pad's LOCAL,
pre-rotation offset (`parse_engine.rs`: stored pad-centroid-relative,
rotation applied separately) -- correct only for a component at rotation
index 0.

Measured: **148 of 169 components (87.6%)** on `pcb/temper.kicad_pcb` have
a nonzero `initial_rotation`.

This is the mechanism that is actually live under the production
`--net-batching` configuration (the exact command the cited spike used):
instrumenting a real run confirmed `run_net_batched_stage3`'s
`Stage3Output.topology_graph` has 110/110 `net_topologies`, but
`map_topology_to_channels` converts **zero** of them into usable channel
paths (neither `uses_channels` nor `path_graph` carries data Stage 4 can
use) -- so every net, including 2-pad nets, takes
`fallback_channel_path`'s `waypoints = pads` branch. `expand_channel_path_terminals`
is never reached at all under this configuration. Whatever `_net_pad_positions`
computed became the terminal directly, unfiltered.

A routing-free scan (no SAT solve, seconds not minutes) of every 2-pad net's
pre-fix `_net_pad_positions` output against every net's true
(`pin_world_position`-computed) pad position found:

**28 of 49 two-pad nets (of 110 total nets)** whose pre-fix pad coordinate
lands exactly on a **different net's real pad**:

| Net | Own pad | Wrong (pre-fix) coordinate | Lands on | Foreign net | Domain (own / foreign) |
|---|---|---:|---|---|---|
| boot | C10.1 | (105.505, 27.04) | C10.2 | sw | undeclared / undeclared |
| boot | U4.6 | (119.068, 148.13) | U4.3 | +15V | undeclared / **SELV** |
| discharge.r_snub1-p2 | C7.1 | (122.72, 244.66) | C7.2 | PWR_RTN | undeclared / HV |
| ac_l | R6.1 | (140.888, 59.73) | R6.2 | power_in.r_zcd_top1-p2 | HV / undeclared |
| thermal.j_fan-p1 | J1.1 | (101.08, 138.26) | J1.2 | gnd | undeclared / SELV |
| discharge.r_dis1a-p2 | R11.2 | (55.71, 174.09) | R11.1 | +170V_BUS | undeclared / HV |
| discharge.r_dis2a-p2 | R14.1 | (24.11, 77.96) | R14.2 | discharge.k_dis2-nc | undeclared / HV |
| DISCHARGE_CTRL | R17.1 | (36.408, 36.16) | R17.2 | discharge.q_dis_drv-g | SELV / undeclared |
| RELAY_CTRL | R2.1 | (148.238, 252.12) | R2.2 | power_in.q_relay_drv-g | SELV / undeclared |
| **GATE_HS** | **R23.1** | **(44.678, 115.35)** | **R23.2** | **hb.power_loop.q_high-g** | **HV / HV** |
| PWM_HS | R25.1 | (24.775, 145.91) | R25.2 | ina | SELV / undeclared |
| PWM_LS | R26.1 | (105.955, 21.24) | R26.2 | inb | SELV / undeclared |
| tank-out | R30.2 | (49.1, 124.48) | R30.1 | tank.c_tank1-p2 | HV / HV |
| RTD_SDI | R36.1 | (165.595, 46.22) | R36.2 | sdi | SELV / undeclared |
| sdi | R36.2 | (167.245, 46.22) | R36.1 | RTD_SDI | undeclared / SELV |
| RTD_CS_N | R37.1 | (31.415, 31.02) | R37.2 | cs_n | SELV / undeclared |
| cs_n | R37.2 | (33.065, 31.02) | R37.1 | RTD_CS_N | undeclared / SELV |
| sdo | R38.1 | (158.525, 33.1) | R38.2 | RTD_SDO | undeclared / SELV |
| RTD_SDO | R38.2 | (160.175, 33.1) | R38.1 | sdo | SELV / undeclared |
| safety.ovp.r_div_top2-p2 | R53.1 | (82.9475, 242.27) | R53.2 | safety.ovp.comp-inp | undeclared / SELV |
| safety.ovp.r_adc_top1-p2 | R57.1 | (166.358, 174.44) | R57.2 | safety.ovp.r_adc_top2-p2 | undeclared / undeclared |
| safety.ovp.r_adc_top2-p2 | R57.2 | (169.283, 174.44) | R57.1 | safety.ovp.r_adc_top1-p2 | undeclared / undeclared |
| power_in.r_zcd_top1-p2 | R6.2 | (143.813, 59.73) | R6.1 | ac_l | undeclared / HV |
| OVP_VREF_2V5 | U10.5 | (38.8275, 219.85) | U10.3 | +3V3 | undeclared / SELV |
| rtd_pan.low_window-out | U11.1 | (156.783, 98.5) | U11.4 | rtd_pan.r_low_top-inn | undeclared / undeclared |
| rtd_pan.low_window-out | U13.1 | (122.493, 62.56) | U13.4 | y | undeclared / undeclared |
| rtd_pan.high_window-out | U12.1 | (40.973, 62.56) | U12.4 | refin_n | undeclared / undeclared |
| WDT_KICK | U20.4 | (119.668, 141.43) | U20.1 | gnd | SELV / SELV |

`GATE_HS`/R23 (bolded) is the exact net the cited spike measured: a 2-pad
HV net whose emitted copper started at the position of "R23's other pin,
belonging to a different net" -- confirmed here down to the designator and
coordinate, with the root cause identified as `_net_pad_positions`'
rotation bug rather than the SAT/topology path (which never runs under
net-batching -- see above).

### 1b. The defect as directed by this task: `expand_channel_path_terminals` trusted a SAT waypoint unchanged

Independently real and fixed (§2), though not the mechanism that produced
§1a's 28 instances under this board's `--net-batching` configuration
specifically: `expand_channel_path_terminals` returned a 2-pad net's
SAT/channel-derived path unchanged, with no check that its endpoint
resolves to the routed net's own pad. This remains live wherever Stage 3
actually does populate `uses_channels`/`path_graph` for a net (the
non-batched path, or a future fix to net-batching's topology conversion),
and is closed by §2's fix regardless.

## 2. The fixes

### 2a. `_pipeline_grid._net_pad_positions` (`packages/temper-placer/src/temper_placer/router_v6/_pipeline_grid.py`)

Delegates to `pin_world_position` (`temper_placer.core.pin_geometry`) --
"the single source of truth for all pad-position computation" per its own
module docstring, and the function `pad_connectivity_audit._pads_by_net`
already uses correctly. This is the same class of bug a parallel
investigation found in `ParseResult.pads` (Rust `extract_pads_pure`) -- a
separate occurrence in a different code path, not touched here.
`capacity_check.py` and `bundle_analyzer.py` carry their own copies of the
same pre-fix logic; both are out of scope for this change (unrelated call
paths, not exercised by terminal resolution) and are flagged here as a
related follow-up.

### 2b. `channel_mapping.expand_channel_path_terminals` (`packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py`)

A 2-pad net's path endpoints are now validated against `pads` (this net's
own true pad positions, already passed into the function) and corrected
via nearest-pairing (identity vs swap assignment of the two true pads to
the path's first/last waypoint, whichever minimizes total displacement)
when they don't match. Interior waypoints (channel-skeleton routing
guidance) are untouched.

**Why snap to the pad rather than fail the net closed:** `pads` gives the
exact, already-known-correct answer -- there are only ever two candidates
for a 2-pad net and both are known exactly, so this is not a guess the way
picking an arbitrary nearby pad would be. Declining the net instead would
discard real, achievable completion for no correctness benefit. Failing
closed remains the right call when the correct terminal is genuinely
unknown; it is not, here.

## 3. Regression tests, demonstrated failing then passing

- `packages/temper-placer/tests/router_v6/test_pipeline_grid_net_pad_positions.py`
  (3 tests) -- reproduces the GATE_HS/R23 shape directly with a rotated
  2-pin component. **2 of 3 failed** against `git show 7ac299be`'s
  pre-fix `_pipeline_grid.py`; **3 of 3 passed** after the fix.
- `packages/temper-placer/tests/router_v6/test_channel_mapping_terminal_validation.py`
  (7 tests, including a `hypothesis` property test asserting a 2-pad net's
  terminal endpoints always resolve to that net's own pads) -- **5 of 7
  failed** against the pre-fix `channel_mapping.py`; **7 of 7 passed**
  after the fix.
- Targeted existing suites (`test_stage4_result_pbt`,
  `test_stage4_monolith_parity`, `test_stage4_golden_parity`,
  `test_stage4_route_pbt`, `test_all_pad_tree_routing`,
  `test_channel_mapping`, `test_pad_connectivity_audit`) and the full
  `router_v6` suite (4787 passed) show no regressions from either fix;
  the 15 pre-existing failures in the full run are environment-only
  (missing `kicad-cli` binary, a numpy/Rust buffer-ABI mismatch unrelated
  to these two files, and a source-text literal check in an unrelated
  module) -- none touch `channel_mapping.py` or `_pipeline_grid.py`.

## 4. Pad connectivity: the primary completion metric

`scripts/route_board.py` now calls `audit_pad_connectivity()` (wrapping
`pad_connectivity_audit.audit_pcb_file`) on every routed board and prints
the fully-pad-connected count alongside the existing routed/attempted and
`nets_carrying_copper`-style numbers, labelled **PRIMARY metric** in the
output, plus the fake-completion net list when non-empty -- so a
fake-completion regression (the `b39b382d` shape) is visible in normal
routing output, not only under a separate manual audit.

## 5. Before/after pad connectivity

Measured with `pad_connectivity_audit.audit_pcb_file()` against a fresh
`--net-batching --batch-size 10` route on each side (baseline =
`git show 7ac299be` unmodified; fixed = this branch), both boards freshly
routed in this task:

Both boards routed fresh in this task, same command
(`uv run --no-sync python3 scripts/route_board.py --pcb pcb/temper.kicad_pcb
--net-batching --batch-size 10 --output ...`), run concurrently on the same
machine from separate worktrees (baseline = `git show 7ac299be`'s worktree,
unmodified; fixed = this branch).

| | Raw completion (Stage 4 A*) | Segments | Vias | Fully pad-connected (of 139 audited) | Fake completion | Honest gap |
|---|---|---:|---:|---:|---:|---:|
| baseline (pre-fix) | 52/104 (50.0%) | 2579 | 50 | **31** | 48 | 60 |
| fixed (this branch) | 61/104 (58.7%) | 3264 | 24 | **48** | 40 | 51 |

Baseline is byte-identical to the cited spike evidence doc's own baseline
figures (52/104, 2579 segments, 50 vias) -- confirms this worktree/board/
command combination is still exactly `6121c49f`/`7ac299be`'s deterministic
baseline, and that this run is a genuine apples-to-apples comparison, not a
different starting point.

**`fully_connected` gained +17 nets (31 -> 48), zero lost** -- verified by
direct set comparison (`baseline_fully_connected_set ⊆ fixed_fully_connected_set`,
not just matching counts): `DISCHARGE_CTRL`, `OVP_VREF_2V5`, `boot`,
`discharge.r_snub1-p2`, `hb.gate_hs.driver-p1`, `input`,
`power_in.r_zcd_top1-p2`, `rtd_pan.high_window-out`, `rtd_pan.low_window-out`,
`safety.fault_or-a2`, `safety.fault_or-b2`, `safety.fault_or3-b2`,
`safety.fault_or3-y2`, `safety.ovp.r_adc_top2-p2`, `safety.ovp.r_div_top1-p2`,
`sclk`, `tank-out`. `fake_completion` fell 48 -> 40 and `honest_gap` fell
60 -> 51 -- both moved in the honest direction, not just the
fully-connected count.

Both the primary metric (pad connectivity, +17) and the raw/naive metric
(58.7% vs 50.0% completion) improved together here -- this fix did not
need to trade one for the other, though the task's framing (a fix is a good
outcome even if it *only* holds or improves true connectivity while raw
copper falls) would still apply if it had.

**`GATE_HS` itself: terminal-correct, still not fully pad-connected, for a
different, unexamined reason.** The routing-free scan (§1a) confirms
`GATE_HS`'s waypoint no longer lands on R23's foreign pad after the fix,
and Stage 4 A* now reports `✓ GATE_HS routed successfully`. It nonetheless
still appears in the fixed board's fake-completion list -- its copper
reaches one pad but not the other for a reason this task did not trace
further (candidates: grid-quantization snap tolerance vs.
`pad_connectivity_audit`'s 0.02mm match tolerance, or a residual capacity/
clearance constraint independent of the terminal defect). The
wrong-net-bridging safety defect this task was scoped to fix is closed;
full routability for every individual net is not claimed and was never
this task's scope.

**Baseline denominator note.** This task's own brief states "Real
completion on this board is 31/110." The `31` is exactly reproduced above;
`110` is `nets_carrying_copper()`'s denominator (total board nets), not
`pad_connectivity_audit`'s (139 -- every net with at least one physical
pad, the same denominator the cited evidence doc used throughout its own
§3.3 table). Reported here as `31/139` / `48/139` to match the actual
audit tool's own accounting rather than mixing the two metrics'
denominators.
