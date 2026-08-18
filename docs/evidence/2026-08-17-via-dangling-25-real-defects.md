<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=true (worktree agent-a8db6291c83b445c0, branched from origin/main at fa067a952; dirty = this task's own uncommitted fix to via_placement.py + 2 test files, committed alongside this doc. pcb/temper.kicad_pcb was never written by this task -- every kicad-cli run below executes against a byte-for-byte scratch copy under a caller-supplied temp directory; sha256 verified unchanged before and after, sec 1.) -->

# The 25 `via_dangling` defects: characterization, root cause, and fix (2026-08-17)

**Task**: handoff `docs/HANDOFF-2026-08-17.md` §4/§9.4, following on from PR
#1298 (`docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md`),
which disproved the handoff's own assumption that `via_dangling` was an
artifact of the DRC runner never passing `--refill-zones`. PR #1298 measured
the true count as **25** (not 11) and showed it is **identical with and
without `--refill-zones`** — a real, measured null result, cross-validated
by a positive control (`track_dangling` and `isolated_copper` DID move under
the same experiment). This document characterizes all 25, finds a single
root cause covering all of them, fixes the root cause in the via-emission
code, and measures the honest before/after effect on the committed board.

**Scope discipline**: `pcb/temper.kicad_pcb` was never modified.
sha256 `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`,
verified unchanged before and after this task (sec 1). Every DRC
measurement below runs against a scratch copy. My lane per the task brief
is via emission and stitching (`_zone_pour_stitch.py`,
`packages/temper-orchestration/src/pipeline_route.rs`,
`packages/temper-placer/src/temper_placer/router_v6/via_placement.py`, the
`Via` type); zone generation (`zone_generator.rs`) is a sibling agent's
lane and is only read here, never edited.

## 0. Bottom line

- All 25 `via_dangling` findings share **one root cause**: a via placed by
  `via_placement.py::_place_vias_for_path` for a route whose own copper
  never leaves a single external layer. The via-layer-pair derivation
  (`packages/temper-geometry/src/via_clearance.rs::via_layer_pair`) has no
  genuine transition to compute in that case and silently falls back to a
  hardcoded `("F.Cu", "B.Cu")` pair — fabricating a through-via with no
  basis in the route's real geometry. **Fixed** in
  `via_placement.py::_place_vias_for_path`: a single-layer path now gets
  zero vias, with unit + differential-oracle test coverage (sec 4).
- **2 of the 17 affected nets are on the HV domain**
  (`elec/domain_manifest.yaml`): `hb.gate_hs.driver-p1-1`
  (`HighVoltageIsolated` netclass) and `discharge.k_dis1-nc`
  (`HighVoltageSignal` netclass) — see sec 2.1, flagged first.
- The defect is bigger than "one via is dangling": for **all 17** affected
  nets, the routed copper this via belongs to **never reaches any of the
  net's own pads anywhere on the board** (sec 3). Deleting the dangling via
  does not fix that — it cannot, by itself; a real fix needs actual
  routing/pad-connection work, out of scope for via emission. Measured
  directly (sec 5): removing the 25 via records from a scratch copy makes
  `via_dangling` read 0, but **~23 of the 25 reappear as `track_dangling`
  at the same coordinates** (the track that used to end at the via now
  ends at nothing) — a category shift, not an elimination, and this
  document reports that plainly rather than presenting via-deletion as a
  clean win.
- Genuine, unambiguous side effects of removing the 25 non-functional vias
  (measured, not category-shifted): `shorting_items` −19, `creepage` −14 to
  −19, `hole_clearance` −24, `hole_to_hole` −2, `drill_out_of_range` −2,
  `copper_edge_clearance` −1, `unconnected_items` unchanged (424→424,
  421→421). These are real: the phantom vias' own copper discs and drilled
  holes were creating incidental clearance/creepage/hole conflicts against
  neighbouring nets' copper, independent of which DRC category names the
  loose end.

## 1. Board identity

`pcb/temper.kicad_pcb` sha256, checked before this task started and again
at the end: `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`
— unchanged, matches the handoff's corrected value and PR #1298's
measurement. Every `kicad-cli pcb drc` invocation below runs against a
byte-for-byte scratch copy (verified identical sha256 to the committed file
before any edit), with its `.kicad_pro` sidecar copied alongside it
(`ensure_resolvable_kicad_project`'s requirement — an unresolvable project
silently drops the `creepage`/`track_width` DRU rules and would under-report
a safety category) and a `.kicad_dru` regenerated from
`scripts/generate_kicad_dru.py::generate_dru()` (the same SSOT
`ci_check_drc.py` regenerates before every real measurement), so the DRU
rules in force match production exactly. `kicad-cli` version `10.0.5`
(matches the ceiling's recorded provenance), single-threaded
`KICAD_CONFIG_HOME` pin (`_single_threaded_kicad_env`'s determinism
protocol), `--all-track-errors` on every run.

## 2. Characterization of all 25

Every one of the 25 items is a through via (`layers "F.Cu" "B.Cu"`) whose
kicad-cli item description reads *"Via is not connected or connected on
only one layer."* Cross-referencing each violation's `uuid` against the
board's own `(via ...)` records (not just position, which turned out to be
unreliable for the net **name** — sec 2.2) gives:

| # | net (board's own `(net N "...")`, ground truth) | x | y | via size/drill | HV domain? | netclass |
|---|---|---|---|---|---|---|
| 1 | `safety.fault_or3-b2` (127) | 125.885 | 77.48 | 1.0/0.4 | no | Default (unassigned) |
| 2 | `safety.fault_or3-b2` (127) | 130.835 | 80.02 | 1.0/0.4 | no | Default (unassigned) |
| 3 | `safety.fault_or-a2` (123) | 78.645 | 248.53 | 1.0/0.4 | no | Default (unassigned) |
| 4 | `rtd_pan.r_high_top-inp` (97) | 62.095 | 251.04 | 1.0/0.4 | no | Default (unassigned) |
| 5 | `rtd_pan.r_high_top-inp` (97) | 90.0725 | 247.59 | 1.0/0.4 | no | Default (unassigned) |
| 6 | `safety.thermal-line` (141) | 85.915 | 176.94 | 1.0/0.4 | no | Default (unassigned) |
| 7 | `safety.thermal-line` (141) | 83.595 | 253.61 | 1.0/0.4 | no | Default (unassigned) |
| 8 | `safety.uvlo_logic.mon-outa` (145) | 21.0625 | 150.0 | 1.0/0.4 | no | Default (unassigned) |
| 9 | `power_in.q_relay_drv-g` (89) | 124.7725 | 126.81 | 1.0/0.4 | no | Default (unassigned) |
| 10 | `power_in.q_relay_drv-g` (89) | 168.1275 | 140.29 | 1.0/0.4 | no | Default (unassigned) |
| 11 | `i2c_scl_ui` (62) | 160.885 | 185.43 | 1.0/0.4 | no | Default |
| 12 | `ina` (64) | 21.25 | 21.985 | 1.0/0.4 | no | Default (unassigned) |
| 13 | `sclk` (147) | 101.705 | 47.13 | 0.8/0.2 | no | Default (unassigned) |
| 14 | `y` (161) | 63.055 | 250.23 | 1.0/0.4 | no | Default (unassigned) |
| 15 | `y` (161) | 43.3725 | 151.59 | 1.0/0.4 | no | Default (unassigned) |
| 16 | `safety.coil_thermal.comp-inp` (119) | 146.8825 | 23.5 | 1.0/0.4 | no | Default (unassigned) |
| 17 | `safety-line-2` (108) | 116.585 | 76.36 | 1.0/0.4 | no | Default (unassigned) |
| 18 | `WDT_KICK` (24) | 165.3775 | 192.1 | 1.0/0.4 | no | Default |
| 19 | **`hb.gate_hs.driver-p1-1`** (58) | 38.905 | 188.86 | 1.0/0.4 | **YES** | **HighVoltageIsolated** |
| 20 | **`hb.gate_hs.driver-p1-1`** (58) | 127.22 | 159.71 | 1.0/0.4 | **YES** | **HighVoltageIsolated** |
| 21 | **`discharge.k_dis1-nc`** (36) | 153.96 | 117.06 | 1.0/0.4 | **YES** | **HighVoltageSignal** |
| 22 | **`discharge.k_dis1-nc`** (36) | 49.1875 | 91.11 | 1.0/0.4 | **YES** | **HighVoltageSignal** |
| 23 | `RTD_SDI` (19) | 158.88 | 26.7 | 0.8/0.2 | no | FinePitch |
| 24 | `safety.ovp.r_adc_top2-p2` (138) | 81.7925 | 242.26 | 1.0/0.4 | no | Default (unassigned) |
| 25 | `safety.ovp.r_adc_top2-p2` (138) | 167.7575 | 191.65 | 1.0/0.4 | no | Default (unassigned) |

17 distinct nets, 25 via instances (8 nets have both of their board vias in
this list; 9 nets have one of two). "Default (unassigned)" means the net has
no entry in `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`
and matches no `netclass_patterns` glob, so it falls through to KiCad's
`Default` (0.2mm) class — a separate, pre-existing gap
(`scripts/check_hv_netclass_coverage.py` PROPERTY 1/3 territory) not
investigated further here; none of these 15 nets are HV-domain per
`elec/domain_manifest.yaml`, so the gap has no safety bearing for this
finding specifically.

### 2.1 HV nets — flagged first, per the task brief

**`hb.gate_hs.driver-p1-1`** and **`discharge.k_dis1-nc`** both appear in
`elec/domain_manifest.yaml`'s `HV` domain net list (27 entries) and are
independently classified `HighVoltageIsolated` / `HighVoltageSignal` in
`pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` — two
independent SSOTs agree. `hb.gate_hs.driver-p1-1` is the high-side
gate-driver output (floats on the switch node); `discharge.k_dis1-nc` is
the tank-discharge relay's normally-closed contact (the bleeder path that
discharges the resonant tank capacitor when the relay de-energizes — a
safety-relevant path under IEC 60335-1). Both nets have **all** of their
board vias in the dangling list (2/2 each), and — as sec 3 shows — their
entire routed copper does not reach any of their own pads on the committed
board. This is a bigger issue than the DRC category name suggests: it is
not "this via needs a fix," it is "this HV-domain net's routed copper is a
disconnected island, full stop." Flagging for the router/routing owner;
fixing it is out of scope for via emission (sec 3, sec 6).

### 2.2 A separate, small finding: kicad-cli's own net-name label is unreliable for 3/25

Matching each violation's item `uuid` (not just its `(x, y)`) against the
board's `(via ...)` records surfaced a real kicad-cli quirk: for 3 of the 25
items, the free-text `"Via [NAME] on F.Cu - B.Cu"` description names a
**different** net than the via's own `(net N "...")` attribute in the same
file, for the identical `uuid`:

| via uuid (matches board record exactly) | board's own net | kicad-cli's reported net label |
|---|---|---|
| `5b53767e-...` | net 123 `safety.fault_or-a2` | `vcc` (net 158) |
| `b2a73bd3-...` | net 145 `safety.uvlo_logic.mon-outa` | `gnd` (net 13, `PWR_RTN`) |
| `aa2fdf0c-...` | net 147 `sclk` | `cs_n` |

This does not change the count (25 is still 25) or which physical vias are
affected, and none of the true nets involved is HV-domain, so it has no
safety bearing here — but it means kicad-cli's own violation *description*
text is not a trustworthy source for "which net" on a via_dangling item;
the item's `uuid`, resolved against the board file's own records, is. Noted
as a secondary, out-of-scope-to-fix observation (this is `kicad-cli`'s
internal connectivity/reporting behaviour, not a project code path); the
characterization table above uses the board's own ground-truth net, not
kicad-cli's label.

## 3. Root cause: one mechanism, one code path, no exceptions

### 3.1 Every affected net is confined to a single external copper layer

For all 17 nets, every `(segment ...)` record on the whole board is on
exactly one layer:

| net | layer | # segments | net | layer | # segments |
|---|---|---|---|---|---|
| `safety.fault_or3-b2` | B.Cu | 10 | `y` | B.Cu | 107 |
| `safety.fault_or-a2` | B.Cu | 15 | `safety.coil_thermal.comp-inp` | B.Cu | 15 |
| `rtd_pan.r_high_top-inp` | B.Cu | 36 | `safety-line-2` | B.Cu | 53 |
| `safety.thermal-line` | B.Cu | 11 | `WDT_KICK` | B.Cu | 83 |
| `safety.uvlo_logic.mon-outa` | B.Cu | 32 | `hb.gate_hs.driver-p1-1` | **F.Cu** | 32 |
| `power_in.q_relay_drv-g` | B.Cu | 35 | `discharge.k_dis1-nc` | B.Cu | 104 |
| `i2c_scl_ui` | B.Cu | 61 | `RTD_SDI` | **F.Cu** | 91 |
| `ina` | B.Cu | 40 | `safety.ovp.r_adc_top2-p2` | B.Cu | 103 |
| `sclk` | **F.Cu** | 98 | | | |

14 nets are B.Cu-only, 3 are F.Cu-only. Zero mixed-layer segments exist for
any of the 17. This was checked exhaustively (every `(segment ...)` line on
the board, not a sample).

### 3.2 Every one of the net's own pads is on the *other* layer

Every component footprint touching these 17 nets is placed
`(layer "F.Cu")` with SMD pads on `F.Cu` only (verified for all pads of all
17 nets, e.g. `R31.1`, `U27.19`, `K2.4`, `U6.16`, `U7.1`, ...). For the 14
B.Cu-only-routed nets, that means **no pad of the net has any B.Cu copper
at all**; for the 3 F.Cu-only-routed nets, the pads match the route's
layer, but (sec 3.3) the routed copper still never reaches them.

### 3.3 The routed copper is an island, not connected to any pad

Distance from each of the 44 board vias (not just the 25 dangling ones) to
the nearest same-net pad's world position (footprint placement + rotation
applied) ranges 1.7mm–230mm, with the overwhelming majority in the
tens-to-hundreds-of-mm range — i.e. these are not via-in-pad or
near-pad launch vias, they sit in the *middle* of nowhere relative to the
net's own components. Bounding-box cross-check on the two HV nets
specifically: `hb.gate_hs.driver-p1-1`'s 32 F.Cu segments span
y:159.71–207.25mm; its 4 pads (`C17`, `C22`, `U6.16`, `U7.1`) sit at
y≈118–189mm — `C17` and `U6` fall entirely outside the routed segment's own
bounding box. `discharge.k_dis1-nc`'s 104 B.Cu segments span
x:20.75–167.35, y:21.45–148.35; two of its three pads (`R14` at
y≈249.6, `R7` at y≈194.8) are outside that range entirely; the third
(`K2`) is within range but the nearest via is still 4.6mm away — a real
gap, not a touching connection. **This is the deeper defect**: these 17
nets' routed copper (all their segments plus both their vias) is a
disconnected fragment that never reaches any of the net's own pads,
independent of the via_dangling question. `unconnected_items` (KiCad's
ratsnest/ISO check) does not move when the via is removed (sec 5) — strong
evidence these islands were never being credited as a connection by KiCad's
own connectivity engine in the first place.

### 3.4 Why the via is F.Cu/B.Cu regardless: the `via_layer_pair` fallback

`via_placement.py::_place_vias_for_path` derives each via's layer pair by
calling into `packages/temper-geometry/src/via_clearance.rs::via_layer_pair`
(exposed as `via_layer_pair_py`):

```rust
pub fn via_layer_pair(
    vx: f64, vy: f64,
    seg_xs: &[f64], seg_ys: &[f64], seg_layers: &[String],
) -> (String, String) {
    match via_segment_index(vx, vy, seg_xs, seg_ys) {
        Some(vi) if vi + 1 < seg_layers.len() => (seg_layers[vi].clone(), seg_layers[vi + 1].clone()),
        _ => ("F.Cu".to_string(), "B.Cu".to_string()),
    }
}
```

`via_segment_index` matches a `via_positions` entry against `route_path`'s
own `segments` list by exact `(x, y)` (within `1e-4`). When the match fails
(no coincident segment point) **or** succeeds but has no successor (the
via's position is the path's own *last* point — the single most common
shape a stale/terminal waypoint takes), the function falls back to a
hardcoded `("F.Cu", "B.Cu")` pair — unconditionally, regardless of what
layers the path's segments actually occupy.

Reproduced directly (this task, before the fix):

```
>>> path = RoutePath3D(net_name="TEST",
...     segments=[(0,0,"B.Cu"), (5,0,"B.Cu"), (10,0,"B.Cu")],
...     via_positions=[(10.0, 0.0)], path_length=10.0)
>>> _place_vias_for_path("TEST", path, 0.6, 0.3)
[Via(position=(10.0, 0.0), from_layer='F.Cu', to_layer='B.Cu', ...)]
```

A route that is 100% B.Cu still gets an `F.Cu`/`B.Cu` via, because the
fallback has no way to know (or check) that F.Cu never appears anywhere in
`seg_layers`. Since (sec 3.1) **every** affected net's `via_positions` entry
sits at a point with no genuine layer-changing successor, this fallback is
what produced every one of the 25 (and, per sec 5, an additional 11
structurally-identical vias on the same 17 nets that happen not to be
flagged by kicad-cli today — same bug, not yet in the DRC-visible count).

This traces cleanly through **my lane** (via emission): the segment-match
scan and layer-pair derivation are exactly the kernel this task's brief
named (`_zone_pour_stitch.py`'s neighbour, `via_placement.py`, feeding
`pipeline_route.rs`'s `Via::emit_s_expr`). It does **not** touch zone
generation (`zone_generator.rs`) — the affected nets have no zones at all
(`grep '(zone (net ' pcb/temper.kicad_pcb` lists 13 net numbers; none of
the 17 are among them).

## 4. The fix

`packages/temper-placer/src/temper_placer/router_v6/via_placement.py`,
`_place_vias_for_path`: before deriving any via's layer pair, check whether
the path's own segments ever leave a single layer. If not, place **zero**
vias for that path — a single-layer route has no genuine transition for any
via to represent, so the fallback (which cannot be right for it) is never
reached:

```python
if len(set(seg_layers)) <= 1:
    return vias
```

This is intentionally the smallest correct fix: it does not touch
`via_layer_pair`/`via_clearance.rs` itself (that kernel's fallback is still
correct for a genuinely multi-layer path whose specific via position
happens not to match a segment — case 3/6/8 in the test matrix below), and
it does not touch zone generation.

### Test coverage

`packages/temper-placer/tests/router_v6/test_via_placement.py` — new
`TestSingleLayerPathNeverGetsAVia`: the exact defect shape (terminal-point
match, no successor), the mismatch shape (no match at all), a regression
guard that a genuine multi-layer transition still gets its via, and the
degenerate empty-segments case. All pass.

`packages/temper-placer/tests/router_v6/test_via_clearance_tier2_rust_differential.py`:
this file's whole purpose is proving the Rust-backed shim is byte-identical
to a **pinned, verbatim, pre-migration** Python reference (`_oracle_*`,
frozen at commit `f1ffc013`, "do NOT edit"). This fix is a **deliberate**
behaviour change, not a migration artifact, so exact parity is expected to
break for exactly the cases this fix targets — and does not
(deliberately/legitimately) elsewhere. Per this repo's own oracle-fixing
discipline ("fix behaviour first, prove every divergence conservative
across an exhaustive sweep, then re-pin with the evidence"): both
`test_via_layer_pair_matches_oracle_path3d` (the 8-case fixed matrix) and
`test_randomized_via_layer_pair_parity` (300 randomized cases,
`random.Random(0x51AC1E4A)`) were updated to assert the shim returns `[]`
**exactly** when `len(set(seg_layers)) <= 1`, and to keep the byte-exact
parity assertion for every other case unchanged. The randomized test
additionally asserts the single-layer bucket is neither empty nor the
whole 300 (a check that the generator + assertion are actually exercising
both branches). The oracle file itself was not edited (its own
"verbatim copy, do not edit" contract and the separate
`test_oracle_is_verbatim_copy` check are both preserved).

Full result, this task's touched files plus every test file that imports
`via_placement`, `via_clearance` (`temper_geometry.via_clearance` Rust
kernels), or `pipeline_route.rs`'s via emission path:

```
test_via_placement.py .......... .....          15 passed
test_via_placement_rust_differential.py          13 passed
test_via_placement_pbt.py                         5 passed
test_via_clearance_tier2_rust_differential.py    34 passed  (2 updated, not weakened -- see above)
test_via_clearance_tier2_pbt.py                  22 passed
test_astar_route_multilayer_via_fallback.py       6 passed
test_coverage_paydown_v17.py                    126 passed
test_pipeline_route_rust_metamorphic.py           7 passed
test_pipeline_route_rust_differential.py         40 passed
test_pipeline_route_rust_pbt.py                  13 passed
test_adapter.py                                 102 passed, 1 skipped
test_adapter_convert_rust_differential.py        15 passed
```

## 5. Measured before/after (scratch copy, `--refill-zones` both ways)

Method: byte-for-byte scratch copy of `pcb/temper.kicad_pcb` (sha256
verified identical to the committed file), a second scratch copy with
exactly the 25 dangling `(via ...)` lines removed (matched by `tstamp`
uuid, nothing else touched), `.kicad_pro` sidecar + freshly regenerated
`.kicad_dru` (`scripts/generate_kicad_dru.py`) alongside both, `kicad-cli
pcb drc --all-track-errors [--refill-zones] --format json`, single-threaded
`KICAD_CONFIG_HOME` pin, kicad-cli 10.0.5. The no-refill/original-board row
reproduces the committed ceiling and PR #1298's own 5-run measurement
exactly (`shorting_items` 183, `hole_clearance` 90, `track_dangling` 44,
`via_dangling` 25, `creepage` 271, cross-validating this measurement's
protocol before trusting the "fixed" columns).

| category | orig, no-refill | orig, `--refill-zones` | 25-vias-removed, no-refill | 25-vias-removed, `--refill-zones` | note |
|---|---|---|---|---|---|
| `via_dangling` | 25 | 25 | **0** | **0** | target category: eliminated |
| `track_dangling` | 44 | 43 | **67** | **66** | **+23 both modes** — see below, this is NOT a net win |
| `shorting_items` | 183 | 190 | 164 | 171 | **−19 both modes**, real (≪199 cap) |
| `creepage` | 271 | 465 | 257 | 446 | **−14 to −19**, real (uncapped category) |
| `hole_clearance` | 90 | 90 | 66 | 66 | **−24**, real |
| `hole_to_hole` | 3 | 3 | 1 | 1 | **−2**, real |
| `drill_out_of_range` | 4 | 4 | 2 | 2 | **−2**, real |
| `copper_edge_clearance` | 4 | 4 | 3 | 3 | **−1**, real |
| `isolated_copper` | 0 | 111 | 0 | 128 | **+17 under `--refill-zones` only** — flagged, not chased (sec 5.2) |
| `unconnected_items` | 424 | 421 | 424 | 421 | **unchanged**, both modes — see sec 5.1 |
| `clearance` | 499 (capped) | 499 (capped) | 499 (capped) | 499 (capped) | capped both sides, not measured true count |
| `track_width` | 199 (capped) | 199 (capped) | 199 (capped) | 199 (capped) | capped, not measured |
| `silk_overlap` | 199 (capped) | 199 (capped) | 199 (capped) | 199 (capped) | capped, not measured |
| everything else | identical | identical | identical | identical | `lib_footprint_issues` 168, `missing_courtyard` 5, `silk_over_copper` 42, `solder_mask_bridge` 132/133, `silk_edge_clearance` 1, `courtyards_overlap` 1, `tracks_crossing` 1 |

### 5.1 The honest headline: via deletion mostly *renames* the defect, it does not eliminate it

Matching the 23 *new* `track_dangling` positions (present after removal,
absent before) against the 25 removed via coordinates: **13 match within
0.01mm exactly**, and inspecting the rest shows the same pattern at looser
tolerance (KiCad reports the *track segment's own endpoint*, which sits a
few hundredths of a mm from the via centre once chamfering is applied, not
the via's exact coordinate) — effectively all 23 are the same locus as a
removed via. **This is expected, not a surprise**: sec 3.1 already showed
every dangling via touches real copper on exactly one layer (a degree-1
node in the same-net, same-layer segment graph). Deleting the via leaves
that segment's endpoint terminating at nothing — which is precisely what
`track_dangling` also detects. `via_dangling` (−25) and `track_dangling`
(+23) are two DRC categories reporting **the same underlying disconnected
copper**, not two independent facts, so simply deleting the via does not
fix the net's real problem (sec 3.3: the copper still never reaches a
pad) — it only changes which category names the loose end. This document
does not claim via-deletion as a "fix" for the committed board on that
basis, and the fix that lands (sec 4) is the code-level one, not a board
edit (`pcb/temper.kicad_pcb` is never touched regardless).

`unconnected_items` (424→424 no-refill, 421→421 refill, exactly unchanged)
is the one number in this table that argues the deletion was still
harmless in the strict sense the hard rule requires ("prove connectivity
is preserved"): KiCad's own ratsnest/ISO check did not consider these
islands connected to anything before OR after removing the via, so nothing
that was providing real connectivity got removed.

The genuine, non-category-shifted wins (`shorting_items` −19, `creepage`
−14 to −19, `hole_clearance` −24, `hole_to_hole` −2, `drill_out_of_range`
−2, `copper_edge_clearance` −1) come from a different mechanism: the
phantom via's own physical copper disc and drilled hole were creating real
geometric conflicts against *other* nets' nearby copper — a via that
serves no bridging purpose is still real copper occupying real board area,
and removing genuinely non-functional copper reduces genuinely real
clearance/creepage/hole pressure on its neighbours, independent of which
category flags the dangling end at its own net.

### 5.2 `isolated_copper` regression under `--refill-zones`, flagged not chased

`isolated_copper` rises 111→128 (`+17`) under `--refill-zones` after via
removal, but is 0→0 (unchanged) without it. None of the 17 affected nets
have a zone (sec 3.4), so this is not a direct same-net effect; the most
likely mechanism is that one or more removed vias' copper discs incidentally
sat inside a *different* net's zone-fill area and the filler's geometry
came out differently without them (an artifact of the fill algorithm, not
of this fix's own net). This is `--refill-zones`-only, and the production
DRC runner does not pass that flag today (PR #1298), so it has zero effect
on any current, real ratchet measurement — but it is a genuine, measured
side effect against a hypothetical future `--refill-zones` runner, reported
here rather than hidden. Chasing the exact mechanism further would mean
auditing the Rust zone filler/generator's geometry, which is the sibling
agent's lane (`zone_generator.rs`), not this task's; flagged for whoever
picks that up next alongside PR #1298's own recommendation to re-baseline
`isolated_copper` as its own ceiling entry before any `--refill-zones`
switch.

## 6. What remains (owner/routing follow-up, out of scope here)

- **17 nets, including 2 HV-domain nets, have routed copper that never
  reaches their own pads** (sec 3.3). This is the real underlying defect;
  via_dangling was only its most visible symptom in the current DRC
  category set. Fixing it means actually routing these nets end-to-end
  (or re-deriving the router's pad-terminal handling for them) — a
  pathfinding/routing task, not a via-emission fix. The two HV nets
  (`hb.gate_hs.driver-p1-1`, `discharge.k_dis1-nc`) should be prioritized
  given the mains-adjacent safety context.
- **11 structurally-identical, currently-unflagged vias** exist on the same
  17 nets (44 total board vias − 25 dangling − 8 genuinely dual-layer =
  11): same fallback mechanism, same lack of real function, just not
  currently caught by kicad-cli's `via_dangling` heuristic (sec 3.4/5.1
  shows the mechanism is deterministic but not simply "one via per
  disconnected pair gets reported" — no further pattern was established for
  why kicad-cli picks one of a pair over the other). The code fix (sec 4)
  prevents this class from being emitted at all on any future route
  regeneration for these or any other net; it does not retroactively touch
  the committed board.
- **`isolated_copper` under `--refill-zones`** (sec 5.2) — flagged for
  whoever owns zone generation / the eventual `--refill-zones` runner
  switch.
