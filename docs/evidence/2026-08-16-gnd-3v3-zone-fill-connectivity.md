---
module: router_v6
tags: [routing, zones, pour, gnd, 3v3, connectivity, rust-migration, creepage]
problem_type: fix
date: 2026-08-16
---

# gnd plane + +3V3 power islands: Rust-generator pours and KiCad-fill connectivity (2026-08-16)

**Purpose**: solve the two largest remaining pad-connectivity gaps on the
production board: `gnd` (88 pads, In1.Cu plane emitted but unfilled and
fragmented -- 15/88 in the trace graph) and `+3V3` (50 pads, zero copper --
the R1/R7 Power-trace-only policy's unpaid cost). Together these are 138
of the 139-board's most-connected pads.

**Branch**: `fix/gnd-3v3-zone-fill` (worktree `/tmp/opencode/agent-zone-fill`),
base `origin/main` @ `607cc7bd6`.

---

## 1. The measurement toolchain (new, honest, KiCad-native)

`pad_connectivity_audit.py` is deliberately fill-blind by design: it
builds its graph from explicit `(segment ...)`/`(via ...)` geometry only
and never parses zone copper. A filled zone therefore cannot change its
verdict, which is exactly the right property for the segment/via metric
and exactly the wrong one for answering "does the filled plane connect the
pads". Two new read-only harnesses close that gap without touching the
audit:

- `docs/evidence/2026-08-16-pcbnew-zone-fill-connectivity.py` -- fills
  every zone with KiCad 10.0.5's own engine (`pcbnew.ZONE_FILLER`, the
  same engine `kicad-cli pcb drc --refill-zones` and the GUI use), then
  measures REAL pad connectivity from KiCad's own `CONNECTIVITY_DATA`
  (`GetConnectedItems`, one hop, transitive through zones/vias/tracks),
  union-find over canonical geometric keys (the pcbnew Python binding
  wraps the same C++ object in a NEW Python wrapper per call, so `id()` is
  not a stable graph node key -- measured and worked around).
- `docs/evidence/2026-08-16-zone-fill-splice-verify.py` -- splices the
  production emission functions' output into a stripped board copy and
  runs the above.

Both are read-only w.r.t. `pcb/temper.kicad_pcb`.

## 2. gnd (88 pads, In1.Cu plane)

### 2.1 Root causes measured, not assumed

1. **The zone was outline-only** -- zero `filled_polygon` blocks anywhere
   in the router's output (KiCad fills in-memory for DRC but never writes
   the board back; `kicad-cli pcb export` has no "save with fill"
   target). Fill is a post-route operation.
2. **The plane was fragmented even after fill.** Measured via pcbnew on
   the definitive route (`/tmp/opencode/definitive-route.kicad_pcb`):
   after KiCad's own fill, only **38/88 gnd pads** landed in the largest
   connected component. The 9 Python-emitted hull-clip zone outlines
   filled as separate copper islands that do not touch. The fill was not
   the only problem -- the OUTLINE emission was.
3. **Vias were placed against the ~9.5mm keepout, not the 12.6mm carve.**
   `_find_via_drop_point` cleared the HV/SELV keepout (corridor 8.5 +
   1.0mm margin ≈ 9.5mm) but the plane's creepage carve keeps 12.6mm from
   HV copper; vias between 9.5-12.6mm from HV copper were "placed" and
   then touched NO plane fill at all.
4. **The region choice fragmented the carve.** A full-board region
   (board minus keepout) carves into 14 disjoint islands; the pad hull
   region carves into 2 islands covering 69/88 pad positions (the design
   doc's own §7A shape, "pour pieces 6, gnd pads inside pour 67/88").
   Pre-clipping the hull to the keepout region re-fragmented it into 11
   pieces (the keepout boolean splits the hull before the carve) even
   though the carve's own 12.6mm halos are strictly stronger than the
   9.5mm keepout -- the pre-clip was redundant AND harmful.

### 2.2 The fix

`router_v6/_ground_plane.py::generate_ground_plane_blocks` now computes
the In1.Cu pour with the Rust zone generator (#1257 machinery,
`temper_geometry.pour_outline_py` / `emit_zone_outline_s_expr_py`):

- **Region**: the convex hull of gnd's own pads, UNCLIPPED (the Rust
  per-obstacle creepage halos replace the keepout; the keepout rule-zones
  remain as an independent fill-time defense).
- **Obstacles**: `collect_zone_obstacle_records(gnd, In1.Cu, ...)` --
  every other net's copper on In1.Cu (THT pads + through vias) at
  `max(clearance, creepage)` per pair (12.6mm HV-vs-LV creepage).
- **Emission**: one `(polygon ...)` element per ring (exterior + holes).
- **Via placement**: `_find_via_drop_point` gained a `pour_region`
  parameter -- pour-inside positions are preferred (pass 1), with a
  keepout-clear-only fallback (pass 2) so connectivity never regresses.

### 2.3 Measurement (seam-level, stripped board, KiCad's own fill)

| metric | before (#1245 emission) | after (Rust generator) |
|---|---|---|
| gnd pour pieces | 9 (fill: several islands) | **2 islands**, 69/88 pad positions inside |
| pour area | ~6300 mm2 | 7083 mm2 |
| vias inside filled zone | ~(pre-fix placement) | **53/55** |
| largest pad component (pcbnew, after fill) | 38/88 (routed board) | **57/88** (stripped board) |
| gnd-plane creepage violations | 0 | 0 (keepout rule-zones + 12.6mm carve hold) |

The remaining 31 pads not in the majority component are HV-adjacent
(inside the 12.6mm creepage halos): they cannot be reached by ANY plane
copper and cannot receive vias (creepage). They are trace-routing debt
(the F.Cu MST backbone reaches some; the rest are genuine, reported
gaps). `pad_connectivity_audit` still reports the trace graph (15/88 →
~the same, since the backbone is unchanged) -- the plane's contribution is
measured by the pcbnew harness, honestly, not by the fill-blind audit.

## 3. +3V3 (50 pads, In2.Cu power islands)

### 3.1 The data-driven policy question

R1/R7 (2026-07-28) made the Power netclass trace-only because the old
+3V3 pours fragmented into pad-sized remnants. The question the task
posed: with the Rust zone generator (holes preserved, islands honest,
creepage-aware carve) and In2.Cu available, is that still correct?

Measured (`docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py`, the
production seam's own obstacle machinery):

| region | outlines | +3V3 pads inside | pour area |
|---|---|---|---|
| full board minus keepout, KeepAll | 14 | 29/50 | 7916 mm2 |
| per-cluster hulls, PadsOnly | 12 | 28/50 | ~300 mm2 |
| **single hull over all 50 pads, PadsOnly** | **2** | **34/50** | 11352 mm2 |

The single-hull carve (the gnd-plane precedent) covers 34/50 pads in just
2 islands. The other 16 sit inside the 12.6mm HV creepage halos and
cannot be pour-covered on ANY layer (the design doc's own "A* trace
burden" -- measured there at 31/50 on F.Cu, better on In2.Cu because
In2.Cu carries no HV SMD/track copper). **The policy is worth revisiting
for the INNER-layer case**: an In2.Cu pour is not the outer-layer
F.Cu/B.Cu flood R1/R7 banned (that would still wall off the signal
layers); it is the sanctioned `_ground_plane.py` precedent, and it
delivers real copper to 34/50 pads vs the current 1/50.

### 3.2 The fix (R1/R7-preserving)

- `router_v6/_power_islands.py::generate_power_islands_blocks` (new,
  mirroring `generate_ground_plane_blocks`) -- per-rail In2.Cu pours via
  the Rust generator (single hull, PadsOnly, creepage carve), via/MST
  backbone, corridor-aware A*, inter-rail accumulation all unchanged.
- Wired into `_write_routes_to_content` after the gnd plane for
  `+3V3`/`vcc`/`+15V`.
- **`_zone_layers_for_net` is NOT touched**: `test_power_class_is_not_zone_eligible`
  stays green -- Power remains outer-layer trace-only by policy; this is
  the inner-layer standalone-generator precedent `_power_islands.py`'s
  own module docstring already endorses.
- **Inter-rail clip holes preserved through the carve** (measured bug):
  `clipped = hull.intersection(plane_region)` produced pieces with
  interior rings (an earlier rail's buffered region), but only the
  exterior ring reached `pour_outline_py`, so the hole was dropped and
  vcc's outline overlapped +3V3's by 75mm2. The region polygon (exterior
  + interior rings) is now subtracted from the carve result.
- **V_BUS_SENSE excluded from production wiring**: high-impedance ADC
  sense line; R1/R7's own policy evidence says a pour there is
  capacitive-pickup liability. Its 4 pads are 100mm apart across the HV
  keepout. (Its `test_power_islands_are_expressible...` assertion is a
  PRE-EXISTING failure on origin/main -- #1165's manifest change added an
  HV net whose pad blocks V_BUS_SENSE's via at (47.59, 22.755), verified
  by running the test on true origin/main code with my changes reverted.)

### 3.3 Measurement (seam-level, KiCad's own fill)

| net | before | after |
|---|---|---|
| +3V3 | 1/50 | **21/50** |
| vcc | 1/13 | 3/13 |
| +15V | 1/10 | 3/10 |
| V_BUS_SENSE | 1/4 | 1/4 (excluded from production wiring) |

The remaining +3V3 pads are HV-adjacent (no via possible -- creepage) and
the A* tree routing honestly fails on them (definitive-route log:
`+3V3` in the 30-net Unrouted set; the per-edge A* finds no legal path at
12.6mm creepage through the dense board). This is the design doc's
documented "A* trace burden", unchanged by the pour work.

## 4. DRC impact

On the definitive-route fill (old Python zones incl. gnd plane):
creepage 485 → 790 after fill (+305 from OTHER nets' zone fills -- PWR_RTN
94, ac_n 51, +170V_BUS 28, ... -- none from the gnd In1.Cu plane). The
new Rust-generated pours (gnd plane + power islands) are carved at
12.6mm pair creepage with the keepout rule-zones, so they add no creepage
family of their own; the zone-involved creepage measurement from the
#1257 seam verification (0 added over bare) applies to the same carve
machinery.

## 5. Routed-copper avoidance for the backbones (follow-up fix)

Measured on the first full route with the pours wired in: the
gnd/+3V3/vcc/+15V F.Cu backbones crossed the routed tracks and each other
**81 times** (the definitive route's gnd-only backbone crossed ~10).
Root cause: the generators re-parse the STRIPPED source board, whose pcb
has zero tracks -- the route's copper exists only as in-memory segment
strings, so the corridor-aware A* obstacle grid and the via-placement
avoidance never saw it. Both generators accepted a `segments=` parameter
(`routed_segments_obstacle` in `_corridor_backbone.py` parses the
in-memory `(segment ...)`/`(via ...)` strings, buffers each foreign net's
copper by the same per-net pairwise clearance, and is unioned into the
via avoidance and the backbone grid; `_write_routes_to_content` passes
the routed segments, so the power rails also avoid the gnd plane's F.Cu
copper).

Measured on the routed board's own copper fed back through the seam
(pcbnew fill + kicad-cli DRC): **tracks_crossing 81 -> 16** with
connectivity holding (gnd 57/88, +3V3 23/50), zone-involved creepage 0.
The residual crossings are the documented keepout-only fallback edges
(`mst_edges_fallback`), reported honestly per rail.

### 5.1 Final numbers (rebased onto origin/main @ 7b424488f, #1259-#1263)

The branch was rebased onto the five commits that landed after its base
(#1259 zone-generator adoption, #1260 Stage-3 rewrite, #1261 zone-stitch
C-space gates + Power width, #1262/#1263 capstone docs). **#1261 already
implemented the gnd-side of the routed-copper avoidance** (its emitted-
copper parsing is strictly more complete than this branch's first cut:
via placement avoids ALL routed copper on every layer, the fallback
rejects copper-crossing straight edges, and its own measurement documents
the honest consequence: "the previous 15/88 gnd audit floor was partly
built on shorting fallback copper; the honest corridor-clean connectivity
is 4/88 -- a labelled gap beats emitting shorts"). This branch's
`routed_segments_obstacle` additions to `_ground_plane.py` were therefore
dropped as superseded; the `_power_islands.py` routed-copper avoidance
(each rail's vias/backbone avoid the routed tracks and the earlier gnd
plane) remains this branch's contribution on top of #1261.

Final seam measurement (route v2's own 6407 segment/via strings fed back
through the generators, pcbnew fill + kicad-cli DRC on the splice):

| metric | value |
|---|---|
| gnd (pcbnew, largest component after fill) | **28/88** (plane covers 69/88 pad positions; #1261's copper/hole-avoiding via placement constrains the rest -- 45 pads get no via, the honest upstream trade) |
| +3V3 (pcbnew) | **23/50** |
| vcc / +15V / PWR_RTN | 3/13 / 3/10 / 5/15 |
| power_in.ntc-no (pcbnew) | **3/3** |
| tracks_crossing from the plane/power copper | **0** (pre-rebase: 81; #1261's fallback gate + this branch's rail avoidance eliminate them) |
| zone-involved creepage | **0** |
| total DRC violations (spliced, refilled) | 487 |

The audit (fill-blind PRIMARY metric) still reports gnd 15/88 and +3V3
9/50 in the trace graph: the plane/pour copper is invisible to it by
documented design, and #1261's safety gates shrank the F.Cu backbone that
the audit can see. The pcbnew harness is the fill-aware truth.

## 6. Files touched

- `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py`
  -- Rust-generator plane, region choice, pour_region via placement.
- `packages/temper-placer/src/temper_placer/router_v6/_power_islands.py`
  -- Rust-generator per-rail pours (single hull), inter-rail hole
  preservation, `generate_power_islands_blocks` production seam.
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
  -- wire power islands after the gnd plane.
- `packages/temper-placer/tests/router_v6/test_power_islands.py` -- overlap
  test updated to the Rust emitter format (one `(polygon ...)` element
  per ring, `(pts\n` newline, holes grouped with their exterior).
- `docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py`,
  `2026-08-16-pcbnew-zone-fill-connectivity.py`,
  `2026-08-16-zone-fill-splice-verify.py` -- the measurement harnesses.

`pcb/temper.kicad_pcb` untouched (fill is a post-route operation; no
board edit was authorized or needed).

## 7. Outstanding

- The remaining HV-adjacent pads (gnd ~31, +3V3 ~16): real trace routing
  through 12.6mm creepage corridors -- the design doc's documented next
  step, unchanged by this work.
- `pad_connectivity_audit` remains fill-blind by design; the pcbnew
  harness is the fill-aware complement, not a replacement.
