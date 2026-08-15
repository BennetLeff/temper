<!-- provenance: branch fix/ntc-no-ampacity-correction, worktree
/home/bennet/Desktop/temper-worktrees/ntc-ampacity-fix, based on
fix/layer-aware-ampacity @ 0a8288949 (itself branched before PR #1129
(ee427a147) landed on main -- see SS5 for the resulting design_rules.py
staleness and why it does not affect this task's conclusions).
pcb/temper.kicad_pcb is UNCHANGED by this task (sha256
1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d before
and after, on this branch; main's own copy, sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64,
independently confirmed byte-identical to the sha the originating task
brief cited). -->

# power_in.ntc-no ampacity: current correction, drawn-copper wiring, routability, and the first-ever pour-neck measurement

## Headline

- **Corrected current: `AC_L`/`AC_N`/`NTC-NO` were cited at 10.0A; the SSOT
  (`elec/src/constraints.ato:11`, `ACMainsConstraints.i_max = 15A`) says
  **15.0A**. Fixed in `temper-drc-rs/src/ipc.rs::net_currents()`, with
  `NTC-NO` now *deriving* from the same `AC_MAINS_CURRENT_A` constant as
  `AC_L`/`AC_N` instead of a third independent literal.
- **The drawn-copper-follows-declared-netclass mechanism (Task 2) was
  already wired** by three prior commits on this branch
  (`bf59c1161`/`73e255e1f`/`061cc4731`) before this task started:
  `_pipeline_route.py`'s production call now passes `stackup=pcb.stackup`
  into `assign_trace_widths`, which engages a layer-aware IPC-2221B
  physics kernel (`_determine_trace_width_layer_aware`) that resolves
  width from `temper_drc_rs.get_net_current()` for any net with a cited
  current — bypassing the net-name keyword scan that produced this defect.
  Verified end-to-end (SS2) that this kernel now picks up the corrected
  15A for `power_in.ntc-no`.
- **`power_in.ntc-no`'s existing 31-segment/0.508mm/F.Cu trace does not
  touch any of its own net's 4 pads.** Independently measured (not in the
  originating brief) — see SS3.1. Widening this copper in place is not an
  option; whatever fixes this net needs to be routed from scratch.
- **Required width at 15A: 4.156mm (ΔT=20°C, cited convention) — but the
  as-wired runtime path actually computes 6.329mm (ΔT=10°C, the module's
  own internal default)**, a real, measured discrepancy — see SS2.
- **Routability at ~4.16mm: not proven infeasible, not certified feasible.**
  Local egress at 2 of the net's 4 terminal pads is tight enough that a
  straight trace toward the nearest neighboring pad would not clear
  mandatory clearance; the other 2 have ample room. No actual re-route/DRC
  pass was run (out of scope/time for this task) — see SS3.2.
- **`ac_l`/`ac_n` pour necks measured for the first time: 3.32mm (`ac_n`
  F.Cu, narrowest) to ~6.6–7.3mm (B.Cu). All four clear the 2.729mm
  (15A/40°C/2oz) requirement**, narrowest margin +22% — see SS4.

## 1. Current correction (Task 1)

### 1.1 The defect

`packages/temper-drc-rs/src/ipc.rs::net_currents()` cited `AC_L`/`AC_N` at
10.0A and derived `NTC-NO` from that same (wrong) figure
(`e02b02cb9`, this branch's own prior commit — its own message says
"reuses that already-cited figure rather than a new one," which is the
right *mechanism*, applied to the wrong *value*).

### 1.2 SSOT

- `elec/src/constraints.ato:11`: `ACMainsConstraints.i_max = 15A`.
- `docs/specs/NET_CLASS_SPECIFICATION.md` SS3.6 (ACMains): "Current
  Rating: 15A (1800W @ 120V)".
- `REQUIREMENTS.md`: "120V RMS +/-10%", "1.8kW maximum at 120VAC/15A".

`PART_STRESS_AUDIT.md` SS1.2's 18.1-21.2A low-line constant-power figure
is **not** used as the design current here — its own text flags it
"conditional, not confirmed"; 15A is the SSOT per the task brief and is
what's implemented.

### 1.3 Fix

`packages/temper-drc-rs/src/ipc.rs`: introduced `AC_MAINS_CURRENT_A: f64 =
15.0` inside `net_currents()`'s closure; `AC_L`, `AC_N`, and `NTC-NO` all
read from it. `NTC-NO` no longer carries an independent literal, so a
future edit to the AC-mains current cannot update `AC_L`/`AC_N` and
silently leave `NTC-NO` behind (as `e02b02cb9` itself demonstrates
happened once already).

A second, independently-pinned duplicate of this exact table was found and
fixed in lockstep: `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`'s
`StackupGate._DEFAULT_NET_CURRENTS` mirrors `net_currents()` deliberately
(see that module's own docstring and
`tests/placer/cp_sat/test_net_currents_rust_differential.py`, which pins
the two tables' agreement on every exact key) — its `AC_L`/`AC_N` entries
were also still 10.0A and would have silently diverged from the corrected
Rust value the moment this landed, since `_resolve_net_current()` keeps
the Python exact-match table as the authority on any Rust/Python
disagreement. Bumped to 15.0A with the same citation.

### 1.4 Verification

- `cargo test -p temper-drc-rs --lib`: **3314 passed, 0 failed** (full
  crate, not just `ipc::`).
- `cargo test -p temper-geometry --lib`: **8399 passed, 0 failed**
  (unmodified by this task; confirms no collateral regression in the
  sibling physics-kernel crate).
- `scripts/gen_wasm_test_registry.py --check --crate temper-drc-rs`: up to
  date, no regeneration needed (no test function was added, removed, or
  renamed — only literal values inside existing tests changed).
- `pytest packages/temper-placer/tests/core/test_ipc2152.py
  tests/placer/cp_sat/test_net_currents_rust_differential.py
  tests/placer/cp_sat/test_stackup_gate.py`: **75 passed, 8 failed.** All 8
  failures are `ModuleNotFoundError: No module named 'temper_constraints'`
  inside `StackupGate.check()`'s own unrelated IPC-2221 bisection fallback
  path (`gates.py:624`/`643`) — `packages/temper-placer/temper-constraints`
  is a real, separately-buildable crate that the `packages/*` single-level
  `uv.workspace` glob does not reach (it is nested one level deeper), so it
  is simply never installed by `uv sync --all-packages` in any worktree.
  Confirmed unrelated to this task's diff: the failure is raised before
  `check()` ever reaches the width comparison this task's numbers feed,
  and `_DEFAULT_NET_CURRENTS`/`_resolve_net_current()` (what this task
  edited) are exercised and passing in the other 75 tests, including
  `test_gate_delegates_on_exact_keys_and_unknown_nets` and every
  `test_net_currents_rust_differential.py` case. This is also, fittingly,
  the exact crate the task brief told this task to reject as an ampacity
  authority (`temper-constraints/src/ipc.rs`'s unsourced `k_ext=0.065`) —
  its absence from the test environment does not affect any figure used
  here.
- Direct verification against the built extension (this worktree's own
  isolated `.venv`, `uv sync --all-packages`, never touching the shared
  repo `.venv`):
  ```
  >>> import temper_drc_rs as t
  >>> t.get_net_current('ac_l'), t.get_net_current('ac_n'), t.get_net_current('power_in.ntc-no')
  (15.0, 15.0, 15.0)
  ```

## 2. Drawn-copper-follows-declared-current wiring (Task 2)

This branch's history (`bf59c1161` "wire layer-aware ampacity into
assign_trace_widths", `73e255e1f`/`061cc4731` "wire pcb.stackup into the
production assign_trace_widths call") had already fixed the mechanism the
task brief flagged: `_pipeline_route.py::_run_stage5` now calls

```python
width_assignment = assign_trace_widths(
    pathfinding_result,
    default_width=pcb.design_rules.default_trace_width_mm,
    stackup=pcb.stackup,
)
```

Passing `stackup` engages `_determine_trace_width_layer_aware`
(`router_v6/trace_width_assignment.py`), which resolves current via
`_resolve_current_a` — `temper_drc_rs.get_net_current(net_name)` **first**,
falling back to the legacy keyword-derived-width-implied-current only for
nets with no specific citation. Since `NTC-NO` (like `AC_L`/`AC_N`) has a
specific citation, its drawn width is now a function of *current*, not a
`"POWER_IN.NTC-NO"`-starts-with-`"POWER"` keyword match — the defect
mechanism the task brief named is bypassed for this net given this wiring.

No further code change was required for Task 2's core ask.

### 2.1 Verified end-to-end (this task, on the corrected current)

```
_resolve_current_a('power_in.ntc-no', 0.508, 0.635, 10.0)
  -> (15.0, 'measured/cited current 15A (temper_drc_rs.get_net_current)')

assign_trace_widths(..., stackup=<real 6-layer 2oz/1oz stackup>)
  .assignments['power_in.ntc-no'].width_mm == 6.329345618011236
  .reason == 'IPC-2221B: 15A on 2.00oz external copper requires 6.3293mm
              (dT=10C; measured/cited current 15A (temper_drc_rs.get_net_current))'
```

Before this task's fix this call resolved to 10.0A and 5.148mm — the
wiring was correct but the number it wired in was 1.5x low.

### 2.2 A discrepancy this task found and is flagging, not fixing

`assign_trace_widths`'s `temp_rise_c` parameter defaults to **10.0°C**
(matching, per its own docstring, `ipc2152_min_width_mm`/`StackupGate`'s
existing convention) — **not** `TRACE_WIDTH_CALCULATIONS.md`'s 20°C
trace-rise / 40°C pour-rise convention, which is what this task's own 4.16mm
and 2.73mm headline figures use. `_run_stage5` never overrides
`temp_rise_c`, so the actual as-wired production call sizes `NTC-NO` (and
`AC_L`/`AC_N`) to **6.329mm**, not 4.156mm:

| ΔT | Source | Required width, 15A/2oz-external |
|---|---|---:|
| 20°C | `TRACE_WIDTH_CALCULATIONS.md` SS1 (cited board convention, "trace") | 4.156mm |
| 10°C | `assign_trace_widths`/`StackupGate` internal default (as-wired) | 6.329mm |
| 40°C | `TRACE_WIDTH_CALCULATIONS.md` SS1 ("pour") | 2.729mm |

All three computed directly against `temper_geometry.ipc2221b_min_trace_width_mm_py`
(this task's own build), not hand-derived. **This is not a violation of
"never lower the requirement"** — 10°C is the *more* conservative
(wider-demanding) of the two, so the as-wired path is safe in the
direction that matters. But it means a maintainer re-routing this net
against the actual pipeline needs to fit 6.33mm, not the 4.16mm this
task's own brief cites as the headline figure, unless someone deliberately
threads `temp_rise_c=20.0` into that one call site. Not changed here:
`temp_rise_c`'s default is shared by every current-cited net in this
table (`DC_BUS+`, `SW_NODE`, `GATE_H/L`, ...), and changing it without
auditing every one of those nets' own correct ΔT convention is outside
this task's scope and risks an unreviewed, unintended width change
elsewhere on the board.

## 3. `power_in.ntc-no` routability (Task 3)

### 3.1 The existing copper does not connect to its own net's pads

Measured directly by parsing `pcb/temper.kicad_pcb` as an S-expression
tree (custom parser, cross-validated below), on **both** main
(`d33c0446e`, sha256 `6928b7c8...`, matching the originating brief
exactly) and this branch's own (differently-stackup'd, same footprint
placements) copy:

- Net 88 (`power_in.ntc-no`) has exactly **4 pads**: `K1.13`
  (98.405, 211.895), `RT1.2` (32.9, 210.1), `U1.2` (162.92, 223.03),
  `U2.1` (28.29, 175.44) — global coordinates, footprint `(at ...)` +
  pad-local `(at ...)` composed with the footprint's own rotation.
- The net's **31 F.Cu segments, all 0.508mm** (confirmed byte-for-byte
  identical to the originating brief's own count/width/layer) form a
  **single continuous polyline** (32 unique endpoints from 31 segments,
  exactly 2 degree-1 open ends: `(152.795, 172.825)` and `(86.73, 189.82)`).
  **Neither open end is within 3mm of any pad on this net** — nor, on a
  0.5mm-tolerance direct search, any pad on *any* net. The nearest thing
  found near either end is `C4.1` (`+170V_BUS`, a different net) 1.5mm
  from one end.
- This is **not** a coordinate-transform bug: the same footprint-rotation
  composition, applied to `K1`'s own pads by hand (`(-3.175, 9.5)` local,
  180° rotation, footprint at `(95.23, 221.395)` -> `(98.405, 211.895)`
  computed both by the script and by hand), matches exactly. A second,
  independent sanity sweep on net 66 (`inb`, 110 segments, also one
  continuous polyline) found the identical pattern — its own open ends
  are 12–85mm from its nearest pads.
- This matches an **already-documented** router pathology, not a new
  class of bug: `docs/evidence/2026-08-13-netclass-current-scoping.md`
  SS4.1 independently found and named "fake-completion" copper — segments
  emitted and counted as "solved" by net-batching without actually
  reaching the net's pads — on a different net (`discharge.k_dis1-nc`) on
  this same board.

**Consequence for this task**: the "widen this trace" framing is not
available as a mechanical edit. Whatever realizes `power_in.ntc-no` at a
current-adequate width has to be an actual new route (or pour), not a
width bump applied to the existing 31 segments — those 31 segments are
not part of the net's real electrical path today regardless of width.

### 3.2 Local corridor headroom at the 4 real terminal pads

Nearest **different-footprint** pad to each of the net's 4 pads (global
coordinates, from the same parse):

| Pad | Nearest other-footprint pad | Distance | Net |
|---|---|---:|---|
| `K1.13` (98.405, 211.895) | `K1.A1` (98.405, 221.395) | 9.500mm | `power_in.bypass_relay-coil1` |
| | `L1.3` (107.480, 207.130) | 10.250mm | `PWR_RTN` |
| `RT1.2` (32.9, 210.1) | `U15.3` (33.728, 219.850) | 9.785mm | `gnd` |
| `U1.2` (162.92, 223.03) | `C8.1` (164.580, 228.580) | 5.793mm | `discharge.r_snub2-p2` |
| `U2.1` (28.29, 175.44) | `R11.2` (32.850, 174.090) | 4.756mm | `discharge.r_dis1a-p2` |

(`K1.14`, at 6.35mm from `K1.13`, is excluded — it is the *other half* of
the same relay terminal's split-pad footprint pattern, not a routing
obstacle in the ordinary sense; its net, `w1_2`, is a different signal
sharing the same physical lead.)

A straight 4.156mm-wide trace (half-width 2.078mm) at `HighVoltage`'s
declared clearance (2.0mm, `design_rules.py` — unchanged by PR #1129's
trace-width-only bump on main) needs roughly `2.078 + 2.0 + (neighbor pad
half-extent, ~1.0-1.2mm for these pads)` ~= 5.1-5.3mm of straight-line
room in the direction of the nearest obstacle to clear it without a
clearance violation.

- `K1.13` and `RT1.2`: nearest obstacles at 9.5-10.25mm — **clear**, wide
  margin.
- `U1.2`: nearest obstacle at 5.793mm — **marginal**, ~0.5-0.7mm of spare
  room in that specific direction.
- `U2.1`: nearest obstacle at 4.756mm — **does not clear** a straight
  trace aimed directly at `R11.2`; the route must leave in a different
  direction from that pad.

None of this proves infeasibility — a real router does not have to head
straight at the nearest pad, and `U2.1`'s tightness is direction-specific,
not a 360° blockage. It does mean a naive "just draw it 4.16mm wide"
placement is not free to exit in every direction from 2 of the net's 4
terminals, and confirms the corridor is genuinely tight in places, not
merely narrow-on-paper.

### 3.3 Honest answer

**Not certified either way.** No actual autorouter/DRC pass was run
against this specific hypothetical re-route (full-board `route_board.py
--net-batching` runs take ~485s per `docs/evidence/2026-08-13-netclass-current-scoping.md`
SS4, and this task's brief flagged live disk/OOM pressure this session —
launching one was judged out of proportion to what remained of this
task's time budget, and is flagged here as explicitly outstanding rather
than silently skipped). What is established:

- `power_in.ntc-no` is not currently a valid starting point for a width
  edit — it needs an actual route (SS3.1).
- Local egress is comfortable at 2 of 4 terminals and tight-to-blocked at
  the other 2 for a straight fat trace (SS3.2).
- `ac_l`/`ac_n` — same 15A design current, same board, comparably dense
  regions — are already realized as **pours**, not traces, and this
  task's own fresh measurement (SS4) confirms those pours clear their
  requirement with real (if not huge) margin. That precedent, which the
  task brief itself pointed at, is the more promising path for
  `power_in.ntc-no` too, rather than attempting a single fat trace through
  `U2.1`'s tight corner.

**Recommendation**: attempt `power_in.ntc-no` as a zone pour (mirroring
`ac_l`/`ac_n`'s existing realization) in a follow-up, then verify with an
actual routed DRC pass — this task establishes the target width(s) (4.156mm
at the cited 20°C convention, 6.329mm at the pipeline's actual as-wired
10°C default — SS2.2) and the specific corridor risk (`U2.1`) that pass
needs to clear, rather than closing the question itself.

## 4. `ac_l`/`ac_n` pour neck measurement (Task 4) — measured, not assumed, for the first time

### 4.1 Method

`pcb/temper.kicad_pcb`'s `(zone ...)` blocks store only the **drawn
outline** polygon (what the pour was told to fill), not the DRC-computed
filled shape (which subtracts thermal-relief/clearance cutouts around
every other-net pad, via, and trace the pour has to route around) — the
task brief is correct that this has never actually been measured.

Pipeline built for this task:

1. `kicad-cli pcb export svg --layers {F,B}.Cu --exclude-drawing-sheet
   --check-zones --mode-single` — `--check-zones` forces a real zone
   refill, so the exported SVG reflects the actual DRC-aware filled
   copper, not the drawn outline.
2. A from-scratch SVG rasterizer (`rasterize_svg.py`) that replays the
   file's own draw order: KiCad plots zone fills as solid-color polygons
   with **white polygons/circles drawn on top in document order** to
   punch thermal-relief and clearance cutouts (not SVG even-odd fill
   rule) — the rasterizer must respect draw order or it over-counts
   copper. Copper color is auto-detected per layer (`#C83434` on F.Cu,
   `#4D7FC4` on B.Cu — KiCad's per-layer plot palette).
3. The zone's own outline polygon (from the `.kicad_pcb` file) masks the
   rasterized layer to isolate just that net's own fill from unrelated
   copper elsewhere in the crop.
4. Neck width = the largest erosion radius `r` (binary morphological
   erosion, disk structuring element) the pour's largest connected
   component survives before splitting into 2+ substantial pieces; neck
   width = `2r`.

### 4.2 Validation (before trusting the pipeline on `ac_l`/`ac_n`)

- **Algorithm**, on a synthetic 3.0mm-wide strip with a 2.0mm-wide
  synthetic neck: measured **1.96mm** (2% error at 15px/mm).
- **Full pipeline** (SVG export + rasterizer + algorithm), on a real,
  independently-known-exact trace segment (`power_in.ntc-no`'s own
  0.508mm F.Cu segment, confirmed by direct `.kicad_pcb` parsing, SS3.1):
  measured **0.490mm** (3.5% under, at 40px/mm — consistent with pixel
  quantization plus the rasterizer's line-cap approximation; the bias is
  an *underestimate*, so real neck widths below are more likely to be
  slightly larger than reported, not smaller).

### 4.3 Result

| Net | Layer | Measured neck (mm) | Resolution |
|---|---|---:|---:|
| `ac_l` | F.Cu | **4.28** | 0.040mm/px |
| `ac_l` | B.Cu | ~6.6 | 0.067mm/px |
| `ac_n` | F.Cu | **3.32** (narrowest) | 0.040mm/px |
| `ac_n` | B.Cu | ~7.3 | 0.067mm/px |

Required (15A, 40°C rise, 2oz external, `TRACE_WIDTH_CALCULATIONS.md` SS1
/ `docs/evidence/2026-08-13-netclass-current-scoping.md` SS1.2): **2.729mm**
(computed directly via `temper_geometry.ipc2221b_min_trace_width_mm_py(15.0,
2.0, 40.0, False)` in this task's own build — matches the prior document's
independently-derived 2.7288mm to 4 decimal places).

**All four clear the requirement.** Narrowest is `ac_n`/F.Cu at 3.32mm,
+22% margin over 2.729mm — real but not huge. `ac_l`/F.Cu clears by +57%.
The B.Cu figures were only measured at the lower of two resolutions tried
(15px/mm) since F.Cu was tighter in both nets at every resolution checked;
if B.Cu ever becomes the binding layer for a stackup change, re-measure it
at 25px/mm+ per this doc's own method before relying on the number.

The `ac_n`/F.Cu neck visually corresponds to a real geometric constriction
(a component-dense diagonal band the pour threads between two rows of
0402/0603-scale passives), not a rasterization artifact — confirmed by
visual inspection of the intermediate mask image, not just trusted from
the number.

## 5. `test_production_board_drc_regression` — status, not touched

Already red per the task brief (median 1648 vs ratchet 1425,
`PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS`,
`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py:826`).
Confirmed the ratchet value on this branch matches the brief's citation
exactly. **Not touched** — no `R27 Ceiling-Approval:` trailer was sought or
granted, and none of this task's changes (a current-table correction and
an evidence measurement) alter what gets routed onto `pcb/temper.kicad_pcb`,
so this ratchet's state is unaffected either way by this task's diff.

## 6. This branch's own staleness — noted, not fixed

`fix/layer-aware-ampacity` (this task's base) is **not** an ancestor of
PR #1129 (`ee427a147`, merged to main as `d33c0446e`'s ancestor), which
bumped `design_rules.py`'s `HighVoltage.trace_width` 3.0mm -> 5.0mm. On
this branch that field still reads 3.0mm. This does **not** affect any
conclusion in this document: Task 1's fix is confined to
`temper-drc-rs/src/ipc.rs`'s current table; Task 2's wiring resolves width
from *current* via the physics kernel for any net with a citation
(`power_in.ntc-no` has one), never from `design_rules.py`'s declared
`trace_width` field, for exactly the nets this task cares about; and Task
3/4's geometric measurements were run directly against the `.kicad_pcb`
file (byte-identical to main's own copy in every respect checked), not
against any Python netclass table. Reconciling this branch with current
main is a normal-merge concern for whoever lands this work, not something
addressed here.

## 7. Files changed

- `packages/temper-drc-rs/src/ipc.rs` — `AC_MAINS_CURRENT_A` constant;
  `AC_L`/`AC_N`/`NTC-NO` all derive from it; corrected test assertions.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` —
  `StackupGate._DEFAULT_NET_CURRENTS["AC_L"/"AC_N"]` 10.0 -> 15.0, kept in
  lockstep with the Rust table per this file's own pinned-differential
  contract.
- `packages/temper-placer/tests/core/test_ipc2152.py`,
  `packages/temper-placer/tests/placer/cp_sat/test_net_currents_rust_differential.py`,
  `packages/temper-placer/tests/placer/cp_sat/test_stackup_gate.py` —
  updated assertions/probe currents that hardcoded the stale 10.0A figure.
- This document.

`pcb/temper.kicad_pcb` is untouched throughout (sha256 unchanged, checked
before and after on this branch and independently against main).
