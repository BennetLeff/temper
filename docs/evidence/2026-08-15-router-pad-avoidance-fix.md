# Router pad-avoidance fix — rotation omission in the write-path pad-position collector

**Date**: 2026-08-15
**Branch**: `fix/router-pad-avoidance-dead-shorts`
**Base**: `origin/main` @ `6285d6889`

## TL;DR

The router's A* pathfinding **was** treating foreign pads as obstacles (they are in
the obstacle map, blocked in every occupancy grid, and both the Rust A* kernel and
the Theta\*/Lazy-Theta\* searches check blocked cells correctly). The dead shorts came
from a different, write-path defect: the pad-position collector feeding the
zone-stitch writer computed world positions **without applying the component's
rotation**. For any rotated 2-pad component, each net's pad landed on the **other**
net's physical pad, so the stitch tracks for net X were emitted *from net Y's pad* —
204 `shorting_items` + 2 `tracks_crossing` on the 2026-08-15 routed board.

The fix delegates each resolved pin's world position to the rotation-aware SSOT
kernel (`temper_geometry.pin_world_position_at_py`), the same kernel the A*
waypoint path has always used.

## The DRC classification finding

`kicad-cli pcb drc` (10.0.5, `--all-track-errors`) on
`final-route-6layer-output.kicad_pcb` (the 2026-08-15 routed board):

| category | before |
|---|---|
| `shorting_items` | **204** |
| `tracks_crossing` | **2** |

Canonical example: **`w1_1`'s 5 mm stitch track starts at (150.29, 156.35) — RV1's
`ac_n` pad** — and `ac_n`'s 3 mm stitch starts at (157.79, 158.65) — RV1's `w1_1`
pad. The two nets' pads on RV1 (a varistor rotated 180°) were exchanged in the
writer's view.

## Root cause

### Mechanism — option (f): pads are obstacles; the WRITE path's pad positions are wrong

The task's Phase-1 hypotheses a–e were all checked and rejected:

- **(a) pads not in the obstacle map** — false. `build_obstacle_map` adds every pad
  (`obstacle_map.py` step 1), PTH pads to all signal layers, SMD pads to their own
  layer.
- **(b) pads only for the same net** — false. All nets' pads are obstacles; the
  routing net's own pads are re-opened per-net by `_unblock_net_pads`.
- **(c) wrong clearance/geometry** — a separate, pre-existing width-mismatch defect
  (see "Remaining shorts" below), not the pad-swap shorts.
- **(d) A\* ignores pads** — false. The Rust kernel (`temper-rust-router-core`
  `astar.rs`) blocks every cell that is not 0 or the routing net's id; the Python
  Theta\*/Lazy-Theta\* searches do the same; the line-of-sight check does too.
  Verified empirically: RV1's `ac_n` pad **is** a `-1` static obstacle in the F.Cu
  occupancy grid.
- **(e) PTH pads treated differently** — false. PTH pads block all layers correctly.

The actual mechanism: `_adapter_convert._write_routes_to_content` builds
`pad_positions` via `temper_orchestration.run_collect_pad_positions`, a faithful
port of the pre-migration Python body:

```python
positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
```

This sums `comp.initial_position + pin.position` with **no component rotation**.
For a component rotated 180° (quadrant 2), the correct world position is
`anchor + R(-π)·offset = anchor − offset`; the naive sum is `anchor + offset` —
the **mirror position across the anchor**, which for a 2-pad part is exactly the
**other pad**. Every pad of a rotated 2-pad component was therefore attributed to
the wrong net by exactly one pad.

`pin_world_position` / `pad_identity.net_pad_positions` — the rotation-correct SSOT
used by the A* waypoint path (`_pipeline_grid._net_pad_positions`) — never had this
bug. Only the write-path collector carried it, and it is the sole pad-position
source for the zone-pour emitter (`_stitch_isolated_pads` /
`_stitch_pads_to_each_other` / zone-hull construction), which emits the mains nets'
copper (`w1_1`, `w1_2`, `ac_n`, `ac_l`, ...) because those nets are excluded from
A* (zone nets).

Measured impact of the swap on the classified board (definitive analysis below):
**14 swap stitches** — track segments whose START point is a pad the board
attributes to a different net — were emitted from rotated 2-pad components:
`w1_1`↔`ac_n` (RV1), `w1_2`↔`power_in.ntc-no` (RT1), `+170V_BUS`↔
`power_in.ntc-no`↔`DC_BUS_RTN`↔`PWR_RTN` (the rectifier/bus parts), and
`tank.c_tank1-p2`↔`tank-out`. Each stitch's copper touches the foreign pad it
starts on, producing the `shorting_items` and `tracks_crossing` violations
(204 / 2 on the classified board). After the fix, no stitch can start on a
foreign pad, so this entire class is structurally impossible.

The rotation-omission was already known to the codebase in general — `pad_identity.py`
documents the 2026-08-08 "rotation-omission incident" (148/169 components have
nonzero `initial_rotation`) and lists `run_collect_pad_positions` as a deferred
first-match call site; the *rotation* half of that deferral is what this change
resolves (the occurrence-collapse half remains deferred).

## The fix

`packages/temper-orchestration/src/pipeline_route.rs::run_collect_pad_positions`:
when a pin resolves, its world position is now delegated to
`temper_geometry.pin_world_position_at_py` (the SSOT kernel behind
`core.pin_geometry.pin_world_position`: side mirror + R(-theta) with host libm),
instead of the naive anchor+offset sum. Missing `initial_rotation_quadrant` /
`initial_side` attributes default to 0 (no rotation / no mirror), so duck-typed
test stubs and rotation-0 components produce byte-identical results to before —
only rotated components' pads move (to their correct positions).

Re-pinned in the same commit (the PR #1207 re-pin standard: fix behaviour first,
prove the divergence is exactly the corrected positions, re-pin with evidence):

- `test_adapter_convert_marshal_rust_differential.py::_oracle_collect_pad_positions`
  — same mirror + R(-theta) formula; `_ORACLE_COLLECT_PAD_POSITIONS_SHA256`
  re-pinned; new `test_collect_pad_positions_rotation_aware` differential test
  added (180° and 90°+mirror stubs).
- `tests/router_v6/_adapter_convert_py_oracle.py` — the `_write_routes_to_content`
  pad-positions block re-pinned to the same formula;
  `scripts/oracle_hashes.json` entry updated.
- `test_pipeline_route_rust_differential.py::_BODY_DIGESTS["_write_routes_to_content"]`
  re-pinned.

Verification:

- Fixed collector on the classified board: `w1_1`'s RV1 pad is now (157.79, 158.65)
  (was ac_n's pad), `ac_n`'s is (150.29, 156.35) (was w1_1's pad), `w1_2`'s RT1 pad
  is (40.4, 210.1), `power_in.ntc-no`'s is (32.9, 210.1) — exactly matching the
  pcb file's own pad nets and `net_pad_positions`.
- 212 affected tests pass (marshal differential incl. the new rotation test,
  pipeline-route differential, adapter tests, marshal PBT/metamorphic).
- `cargo test -p temper-orchestration` passes (2 tests).
- `make extensions` rebuilt all 10 pyo3 crates fresh.

## Phase-3 measurement

Route command (identical to the DRC agent's recipe):
`route_board.py --net-batching --batch-size 10`.

### Before (buggy `run_collect_pad_positions`)

- Classification board (`final-route-6layer-output.kicad_pcb`, agent-final-6layer
  lineage): **204 shorting_items / 2 tracks_crossing** (DRC agent's measurement).
- Same-board re-run on this worktree's board (main lineage) with the pre-fix
  extension, identical recipe (`--net-batching --batch-size 10`):
  **16 swap stitches**, `tracks_crossing` **5** (run_drc) / **4** (direct
  kicad-cli), `shorting_items` **199–201** (at KiCad's per-report cap),
  total DRC violations **1666**.

### After (fixed extension)

Same board, same recipe, only the extension differs:

- **0 swap stitches** — the rotation defect is structurally gone.
- `tracks_crossing` **1** — down from 4–5; the one remaining crossing
  (`safety.ovp.r_adc_top1-p2` × `power_in.ntc-no` on In3.Cu) is the separate
  width-mismatch defect (present before the fix too).
- `shorting_items` **199–205** — still at KiCad's per-report cap; the count is
  dominated by the width-mismatch defect below, so the capped total does not
  visibly move even though every swap short is gone.
- total DRC violations **1638** (down from 1666); run_drc error count
  **1162** (down from 1190).
- Stitch geometry verified directly: `ac_n` now emits **zero** track segments
  (pure pour); `w1_1`'s trunk starts at its own C1/RV1 pads; `w1_2`'s trunk
  terminates at RT1 pad 1 (40.4, 210.1) — its own pad — instead of the swap
  stitch from power_in.ntc-no's pad; `power_in.ntc-no`'s In3.Cu connectors
  terminate at its own pads (32.9, 210.1) etc.

The swap-short class (e.g. `power_in.ntc-no` × `w1_2` at the RT1 pads, `w1_1` ×
`ac_n` at the RV1 pads) is zero after the fix; the residual shorts all belong to
the width-mismatch defect.

## Remaining shorts — a separate, pre-existing defect (NOT fixed here)

Decomposing the classified board's 204 shorts:

| mechanism | count | cause |
|---|---|---|
| pad swap (rotation omission) | 14 swap stitches (each shorting its foreign pad; the 2 `tracks_crossing` are swap stitches too) | fixed by this change |
| track-vs-track / track-vs-pad overlap | remaining (~190) | width-mismatch C-space (below) |

The remaining shorts are all on F.Cu in the dense escape region (e.g. `+15V_LS`
0.5 mm tracks overlapping `hb-gnd` pads/vias and `discharge.k_dis2-nc` tracks) and
along the `w1_1` 5 mm trunk. Mechanism: the occupancy grid's static-obstacle halo
is `default_trace_width_mm / 2 = 0.1 mm` (`OccupancyGridStage`) and every routed
track is marked with `default_trace_width_mm = 0.2 mm` (`_mark_route_blocked`),
while emitted widths are per-netclass up to **5 mm** (HighVoltage `trace_width=5.0`
exactly matches the emitted `w1_1` trunk; HighVoltageSignal 0.5 mm matches
`+15V_LS`). A 0.2 mm-width model lets later nets cross earlier 5 mm/0.5 mm trunks
and lets 0.5 mm tracks pass within ~0.2 mm of pads — actual geometric overlaps.

Fixing this soundly requires **per-net width- and clearance-aware C-space** at
route time (mark each routed path with the net's own width+clearance, and give
static obstacles a per-net halo). A global raised halo is unsound: covering the
widest A*-routed net (5 mm) plus HV clearance (2–6 mm) would block essentially the
whole board. The netclass widths ARE available at route time
(`design_rules.get_rules_for_net(net).trace_width_mm/clearance_mm`) and match the
emitted widths on this board, so the track-marking half is a small, local change;
the static-halo half is the architecturally significant piece. Scoped as a
follow-up — bundled here it would double the change surface of an already
re-pinned PR and cannot reach zero without the per-net halo.

## Phase-4 note: the Rust A* path

`temper-rust-router-core::astar` (and the Python Theta\* family) block foreign
cells correctly; the Rust `theta_star.rs` search kernel likewise operates on the
same occupancy grid and treats `-1`/foreign ids as blocked. The pad-avoidance
defect was never in the search — it was upstream in the write path, which is
exactly where this fix lands. The Python N-layer A* (`_astar_nlayer.py`) remains
the live production path (auto-selected when >2 routable signal layers exist —
`enable_nlayer_astar_spike` is only needed to force it on 2-layer boards), and it
was unaffected. No search-side change was needed; the Rust search kernels are
already correct.

## Files changed

- `packages/temper-orchestration/src/pipeline_route.rs` — rotation-aware
  `run_collect_pad_positions` (+ docstring).
- `packages/temper-placer/tests/router_v6/test_adapter_convert_marshal_rust_differential.py`
  — oracle re-pinned, digest, rotation-aware differential test.
- `packages/temper-placer/tests/router_v6/_adapter_convert_py_oracle.py` — writer
  oracle pad-positions block re-pinned.
- `packages/temper-placer/tests/router_v6/test_pipeline_route_rust_differential.py`
  — `_write_routes_to_content` body digest re-pinned.
- `scripts/oracle_hashes.json` — `_adapter_convert_py_oracle.py` hash re-pinned.
- `packages/temper-placer/src/temper_placer/core/pad_identity.py` — deferred-site
  note updated.
- `docs/evidence/2026-08-15-router-pad-avoidance-fix.md` — this document.

## Follow-ups

1. **Width/clearance-aware C-space** (the remaining ~190 shorts): per-net marking
   width+clearance at route time; per-net static-obstacle halo. See "Remaining
   shorts" above.
2. `run_collect_pad_positions` still uses first-match `comp.get_pin` (occurrence
   collapse on duplicate-pad footprints, e.g. K2/K3 relays) — the deferred half of
   the pad_identity SSOT note; benign for shorts (duplicate pads share a net) but
   wrong for connectivity of relay-coil nets.
