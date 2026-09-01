<!-- provenance: commit=155df4f5ba562e7bf0a54d26c711d3e86aa63598 dirty=UNKNOWN -->
/home/bennet/Desktop/temper-worktrees/ntc-ampacity-fix, based on
docs/evidence/2026-08-14-ntc-no-ampacity-current-fix-and-pour-neck-measurement.md
@ 1291cdaff (that task's own SS3.3 recommendation is the starting point
this task executes and then measures against reality). pcb/temper.kicad_pcb
is UNCHANGED by this task (sha256
1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d before and
after -- checked repeatedly through this task, including after every
kicad-cli invocation, not just at the end). -->

# power_in.ntc-no realization decision + ΔT single-sourcing

## Headline -- lead with the honest bottom line

- **Connectivity: genuinely fixed, twice-verified.** `power_in.ntc-no`'s
  4 real pads (K1.13/RT1.2/U1.2/U2.1) are now joined by a real,
  DRC-checked segment/via graph. Verified two independent ways: the fixed
  pad-connectivity audit (`fix/pad-connectivity-audit-metric` @
  `575f1ba8f`) reports `fully_connected=True, is_fake_completion=False,
  unreached_pads=()`; `kicad-cli pcb drc` on the same board reports this
  net in **neither** its 423 `unconnected_items` (KiCad's own ratsnest).
  This replaces 31 pre-existing segments that touched none of the net's
  pads (confirmed fake completion) and, as a side effect, fixes 59
  pre-existing DRC violations those fake segments themselves caused
  against unrelated nets.
- **Ampacity: NOT genuinely achieved, and this is reported plainly, not
  papered over.** Every mechanism tried for a continuous, 4.156mm-adequate
  15A conductor failed a real, measured check:
  - A single-hull **pour** (matching `ac_l`/`ac_n`'s ACMains idiom)
    fragments into **47+ disconnected islands** under real DRC-aware fill
    -- it does not deliver a continuous wide path (SS1.4).
  - A **wide (4.156mm) trace** along the one topology that IS DRC-clean
    at 0.2mm introduces **4 new real clearance violations** against
    unrelated nets/parts when widened (SS1.6).
  - **A\* pathfinding** (the mechanism that could, in principle, solve
    both problems at once by routing around obstacles) **exhausts an 8GB
    memory cap and aborts**, reproduced in isolation against just this
    one net (SS3.1/SS3.2) -- a router robustness bug, not proof the
    geometry is infeasible.
  - The thin (0.2mm) connectors this task ships for connectivity are
    explicitly **not** rated for 15A -- about 20x undersized.
  **Net conclusion: this task closes the connectivity failure mode
  ("copper that exists and does not connect") but does NOT close the
  ampacity requirement.** What would be needed is specified in SS5.
- **Decision on realization mechanism**: single-hull pour (matching the
  `ac_l`/`ac_n` idiom, per-NET exempted from HighVoltage's clustering) +
  a DRC-verified pad-to-pad stitch topology on `In3.Cu` for provable
  connectivity. Not a pure pour (fails `fully_connected`, SS1.3) and not
  an A*-routed trace (crashes, SS3).
- **Required width, corrected: 4.156mm, not 6.329mm** (Task 3). The
  production width-assignment path was sizing every current-cited net,
  including this one, at an uncited internal ΔT=10°C default, not
  `TRACE_WIDTH_CALCULATIONS.md` SS1's cited 20°C ("IPC-2221B
  recommendation"). Single-sourced at `temper_drc_rs::ipc::
  {TRACE_TEMP_RISE_C, POUR_TEMP_RISE_C}` -- SS2. Consequence: every
  current-cited net's required width gets SMALLER at 20°C, never larger
  -- reported plainly (SS2.3), not chosen to minimise disruption.

## 1. Realization decision and what was actually measured (Task 1/2)

### 1.1 Clustering splits this net's pour into two disconnected islands

`_zone_layers_for_net('power_in.ntc-no')` returns
`['F.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu']` (HighVoltage, `routing_strategy=
"plane_required"`) -- zone-eligible, same as every other HighVoltage
member. HighVoltage is deliberately NOT in `_CONTINUITY_EXEMPT_CLASSES`
(R6, 2026-08-07) -- unlike `ACMains` -- so `compute_zones_for_net` runs
its clustering heuristic instead of one board-wide hull.

Run directly against this net's real 4 pad positions (K1.13
98.405,211.895; RT1.2 32.9,210.1; U1.2 162.92,223.03; U2.1 28.29,175.44):

```
num clusters: 2
 cluster: [(98.405, 211.895), (162.92, 223.03)]   # K1.13 + U1.2
 cluster: [(32.9, 210.1), (28.29, 175.44)]         # RT1.2 + U2.1
```

`compute_zones_for_net(..., cluster=True)` emits **2 separate
convex-hull pours**. `_stitch_isolated_pads` only stitches a pad that
falls OUTSIDE every pour of its own net; every one of this net's 4 pads
is already inside its own cluster's hull, so none is "isolated" and none
gets a stitch. Result: **two genuinely disconnected copper islands**,
each containing 2 of the 4 pads.

### 1.2 Fix: a per-NET continuity exemption, not a class change

Reverting HighVoltage's class-level exemption (R6) would reopen the
board-spanning-hull defect R6 fixed for `SW_NODE`/`DC_BUS_RTN`. Instead,
added `_CONTINUITY_EXEMPT_NETS = frozenset({"power_in.ntc-no"})` in
`_zone_pour_stitch.py`, OR'd into `_emit_zone_pours`'s existing
`exempt = nc in _CONTINUITY_EXEMPT_CLASSES` check. This is not merely a
workaround: `power_in.ntc-no` is physically the same AC-mains conductor
as `ac_l`/`ac_n` one node further along (the line between the CM choke /
bypass-relay NO contact / inrush NTC and the rectifier,
`elec/src/modules.ato`) -- the ACMains precedent applies to it directly.

Verified: single hull, clipped cleanly to the real board outline (no
fragmentation, no overshoot), 2876.5mm² = 8.09% of board area (35568mm²)
-- comparable in scale to `ac_l`/`ac_n`'s own measured 3.9%/7.0%.

### 1.3 Pour alone cannot be scored `fully_connected` -- measured against the precedent itself

Running the FIXED audit against the CURRENT committed board:

| Net | `fully_connected` | `category` | Why |
|---|---|---|---|
| `power_in.ntc-no` | False | `broken` | 31 fake-completion segments touch none of its 4 pads |
| `ac_l` | True | `connected` | 0 pads on this net in the committed netlist (trivial case) |
| **`ac_n`** | **False** | **`zone_dependent_unmeasured`** | **has a real, committed ACMains-idiom pour, but zero segment/via copper touches any of its 3 pads** |

`ac_n` is the literal precedent Task 1's brief pointed at, and it does
not clear `fully_connected` either -- by the audit's own design (its
575f1ba8f commit message: "deliberately does NOT attempt
point-in-polygon zone-fill analysis... an active source of false
confidence on a mains-voltage board"). A pad geometrically inside a
zone's drawn outline is invisible to the audit's segment/via graph, full
stop. Matching the idiom exactly would leave `power_in.ntc-no` in the
same bucket `ac_n` is already in -- not a pass.

### 1.4 The pour itself does not deliver continuous ampacity -- measured, not assumed

Exported the real DRC-aware fill (`kicad-cli pcb export svg --check-zones`,
same method as the prior task's `ac_l`/`ac_n` neck measurement) for
`power_in.ntc-no`'s single-hull pour and rasterized it (custom numpy/scipy
pipeline, validated against a synthetic 2.0mm-neck fixture -- measured
1.9982mm, 0.1% error -- and a known-exact 0.508mm board segment --
measured 0.4999mm, 1.6% error -- before trusting it on real geometry).
Masked to the zone's own outline polygon to isolate this net's fill from
the rest of the board's F.Cu copper in the same crop.

**Result: 47 disconnected components** inside the one hull polygon,
before any erosion is even applied. Largest single fragment: 6717 px at
15px/mm = 29.9mm² -- nowhere near a continuous path across the ~150mm
hull. The hull spans a densely populated diagonal band of the board;
real DRC clearance carving around every OTHER component's pads/traces
inside that large area leaves the fill as a maze of disconnected slivers,
not a floodable plane. **This is the same "declared coverage vs. drawn
copper disagree" pattern this whole investigation exists to catch,
applied to the pour's own fill geometry, not just its outline.**

Consequence: the pour is real, DRC-clean copper (it clips to the board,
respects clearance), but it does not constitute a 4.156mm-adequate
current path between the 4 pads. Whatever mechanism actually carries
15A between the pads has to be something else.

### 1.5 A safe (no-search) pad-to-pad stitch was tried, found unsafe as first built, fixed twice

First attempt: a minimum-spanning-tree of straight 0.2mm segments,
pad-to-pad, on the SAME layer as the pour (F.Cu), reasoning "any straight
line between two points inside our own convex-hull pour stays inside
that pour's clearance margin." True, but irrelevant: F.Cu is dense with
OTHER nets' SMD pads/traces that also sit inside that large hull.
Measured (`kicad-cli pcb drc` against a real spliced board -- the
committed board with ONLY this net's own copper replaced, everything
else left byte-identical, verified via sha256 that `pcb/temper.kicad_pcb`
itself was never touched by this splice): **all 3 MST edges produced
real shorting/clearance violations** against `inb`, `w1_2`, `gnd`,
`safety.fault_or-y2`.

Fix attempt 2: moved the connectors to `In3.Cu` (a PR #1195 inner signal
layer measured to carry **zero** existing track segments anywhere on
this board, and which never carries SMD pad copper at all -- only sparse
THT-pad copper can obstruct it), with a via at both endpoints of every
edge. Measured: the "holes co-located" DRC error on every THT pad
(RT1.2/U1.2/U2.1 already reach every layer via their own plated hole; a
redundant via at the identical position collides with it) plus the
K1.13<->RT1.2 edge (the nearest-neighbour MST's own choice) still
clipping `C6`'s gnd PTH pad.

Fix attempt 3 (final): only place a via where the pad genuinely lacks
copper on `In3.Cu` -- verified via `temper_placer.core.pin_geometry.
pin_world_layer`: RT1.2/U1.2/U2.1 all resolve to `layer="all"` (real THT
pads spanning every layer); K1.13 resolves to `layer="F.Cu"` (real SMD
pad, genuinely needs a via to reach an inner layer -- despite its raw
`.kicad_pcb` declaration literally saying `(layers "F.Fab")`, a red
herring chased and ruled out: the project's own canonical, tested
pin-geometry math -- used throughout the router for pad
unblocking/obstacle placement -- resolves it to real F.Cu copper at
(98.405, 211.895), matching the originating evidence doc's own
hand-verified figure exactly; a DIFFERENT, simpler parser accessor
(`kicad_parser.parse_kicad_pcb(...).pads[i].position`) was found to
silently ignore footprint rotation for this specific rotated footprint,
which is what produced the misleading (92.055, 230.895) figure that
first raised the alarm -- not used by this task's own geometry, which
matches the correct, rotation-composed value throughout). Replaced the
greedy nearest-neighbour edge choice with an **empirically DRC-verified**
topology after testing 3 alternatives:

| Topology | New violations vs. baseline |
|---|---|
| Nearest-neighbour MST (K1.13<->RT1.2, K1.13<->U1.2, RT1.2<->U2.1) | 1 short (K1.13<->RT1.2 clips `C6`/gnd) |
| Path avoiding the direct edge (K1.13<->U1.2<->RT1.2<->U2.1) | 1 short (RT1.2<->U1.2, 130.7mm, ALSO clips `C6`) |
| **K1.13<->U2.1, U2.1<->RT1.2, K1.13<->U1.2 (longer in aggregate)** | **0** |

C6 sits directly in the gap between the board's two component clusters
this net's pads straddle; any edge crossing that gap clips it except the
one topology that routes around it via U2.1 instead. **Final measured
result** (real spliced board, real `kicad-cli pcb drc`): 59 of the
board's pre-existing violations (all caused by the 31 stale fake
segments this replaces) fixed, **0 new shorting/clearance violations**,
1 new benign `via_dangling` warning (severity `warning`, not `error` --
KiCad flags the via's declared `F.Cu`/`B.Cu` full-through span as having
no trace on the unused far side; the net itself is confirmed connected by
the SAME DRC run's `unconnected_items` list, which does not mention this
net at all).

### 1.6 Widening the verified topology to the required 4.156mm reopens the problem

Tested directly: same 3-edge topology, width raised from 0.2mm to
4.156mm. Result: **4 new real clearance violations** (against
`hb.gate_hs.driver-p1-1`, `safety.thermal.comp-inp`, `discharge.r_dis1a-p2`,
and K1's own mounting NPTH hole) that the thin line cleared but the wide
one does not. This is the corridor tightness the originating evidence
doc's SS3.2 already flagged (`U1.2`/`U2.1` marginal-to-blocked for a
straight 4.16mm trace), now confirmed for the LONGER, obstacle-routed
path too, not just a straight line to the nearest neighbour. Hand-tuning
further waypoints to dodge these 4 new obstacles was judged likely to
keep surfacing new ones (the exact failure mode A*/real pathfinding
exists to solve systematically) rather than a bounded fix, and was
stopped here rather than continued indefinitely.

## 2. ΔT single-sourcing (Task 3)

### 2.1 Authority

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS1 (REQ-ELEC-02, v1.0,
"Status: Implemented") is a formal, versioned, standards-cited board
design document: "Max Temp Rise (traces): 20°C -- IPC-2221B
recommendation"; "Max Temp Rise (pours): 40°C -- Acceptable for power
zones." Same class of document already treated as SSOT throughout this
task chain (`NET_CLASS_SPECIFICATION.md`, `REQUIREMENTS.md`,
`elec/src/constraints.ato`).

The competing value, `10.0`, appeared independently in at least 8 call
sites across 2 crates and 4 Python modules, with no citation beyond
"matches this repo's existing convention":

- `temper-drc-rs/src/ipc_pyo3.rs`: `ipc2152_min_width_mm`/
  `ipc2152_current_capacity` pyo3 signature defaults
- `temper-placer/router_v6/trace_width_assignment.py`: `assign_trace_widths`'s
  `temp_rise_c` default -- the PRODUCTION call
  (`_pipeline_route.py::_run_stage5`) never overrides it
- `temper-placer/placer/cp_sat/gates.py`: `StackupGate._DEFAULT_TEMP_RISE_C`
- `temper-placer/core/ipc2152.py`: `ipc2152_external_width`/
  `ipc2152_internal_width` defaults, and `ipc2152_min_width`'s own
  internal hardcoded positional `10.0` (not wired -- SS2.4)
- `temper-placer/core/ipc2221.py`, `core/power_topology.py`: independent
  `10.0` defaults (not wired -- SS2.4)
- `temper-placer/temper-constraints/src/ipc.rs`: a THIRD, independently
  unsourced implementation (already flagged non-authoritative by this
  task's own brief re: its `k_ext=0.065`; not buildable in this worktree
  at all -- SS2.4)

### 2.2 Fix: single home in `temper-drc-rs`, wired to the production path

Added `temper_drc_rs::ipc::{TRACE_TEMP_RISE_C=20.0, POUR_TEMP_RISE_C=40.0}`
(cited from `TRACE_WIDTH_CALCULATIONS.md` SS1), exposed via pyo3. Wired:

- `ipc2152_min_width_mm`/`ipc2152_current_capacity` pyo3 defaults
- `assign_trace_widths`'s default (determines drawn copper width for
  every routed net on the production board)
- `StackupGate._DEFAULT_TEMP_RISE_C` (the DRC-gate check and the
  width-assignment path it checks now cannot disagree on ΔT)
- `core/ipc2152.py`'s two convenience wrapper defaults

Verified against the rebuilt extension (this worktree's own isolated
`.venv`, `uv sync --all-packages --reinstall-package temper-drc-rs`,
never touching the shared repo `.venv`):

```
>>> import temper_drc_rs as t
>>> t.TRACE_TEMP_RISE_C, t.POUR_TEMP_RISE_C
(20.0, 40.0)
>>> t.ipc2152_min_width_mm(15.0, 2.0)   # power_in.ntc-no/ac_l/ac_n, 2oz ext
4.155896707954811
```

`cargo test -p temper-drc-rs --lib`: 3314 passed, 0 failed (matches the
prior task's own baseline exactly). `cargo test -p temper-geometry --lib`:
8399 passed, 0 failed (unmodified crate). `scripts/gen_wasm_test_registry.py
--check --crate temper-drc-rs`: up to date. Full relevant pytest surface
(`test_adapter.py`, `test_trace_width_assignment.py`, `test_ipc2152.py`,
`test_topology_copper_audit.py`, `test_forced_segment_fail_closed_pbt.py`):
170 passed, 1 skipped, 1 pre-existing failure
(`test_full_pipeline_run_surfaces_the_same_unexplained_gap` -- GATE_L/PWM_H
A* pathfinding gap on the 33-net benchmark fixture; confirmed
independently reproducible at the PARENT commit `1291cdaff` with none of
this task's changes present, via a scoped `git checkout <parent> --
<changed files>` / re-test / `git checkout HEAD -- <changed files>`
round-trip -- not touched by this task's diff).

### 2.3 Consequence for every current-cited net -- reported plainly, not minimised

Computed directly via `temper_geometry.ipc2221b_min_trace_width_mm_py`,
2oz external and 1oz internal, both ΔT conventions:

| Net | I (A) | w @10°C ext (mm) | w @20°C ext (mm) | delta | w @10°C int (mm) | w @20°C int (mm) |
|---|---:|---:|---:|---:|---:|---:|
| `DC_BUS+` | 16.0 | 6.9186 | 4.5428 | -2.3758 | 35.9967 | 23.6357 |
| `SW_NODE` | 16.0 | 6.9186 | 4.5428 | -2.3758 | 35.9967 | 23.6357 |
| `AC_L` | 15.0 | 6.3293 | 4.1559 | -2.1734 | 32.9308 | 21.6226 |
| `AC_N` | 15.0 | 6.3293 | 4.1559 | -2.1734 | 32.9308 | 21.6226 |
| `power_in.ntc-no` | 15.0 | 6.3293 | 4.1559 | -2.1734 | 32.9308 | 21.6226 |
| `GATE_H`/`GATE_L` | 2.0 | 0.3930 | 0.2580 | -0.1349 | 2.0447 | 1.3425 |
| `+3V3`/`+5V` | 0.5 | 0.0581 | 0.0381 | -0.0199 | 0.3021 | 0.1984 |
| `+15V` | 0.2 | 0.0164 | 0.0108 | -0.0056 | 0.0854 | 0.0561 |
| `BYPASS_RELAY-COIL` | 0.0754 | 0.0043 | 0.0028 | -0.0015 | 0.0222 | 0.0146 |
| `Q_RELAY_DRV-G` | 0.0033 | 0.0001 | 0.0000 | -0.0000 | 0.0003 | 0.0002 |

**Every current-cited net's required width gets SMALLER at the corrected
20°C, never larger.** Reported as-is, not chosen because it minimises
disruption: 20°C is IPC-2221B's own cited recommendation for this board's
application, carried by a real, versioned design document; 10°C was an
internally-consistent-but-uncited pair of code defaults with no
independent derivation for this board. This is not "lowering a
requirement to make copper pass" -- it corrects an unsourced internal
default that happened to disagree with the board's own formal spec in
the conservative direction, exactly parallel to Task 1's own
`AC_MAINS_CURRENT_A` correction (10A->15A), which happened to go the
OTHER direction. Both corrections follow the citation, not a preferred
outcome.

### 2.4 Sites NOT wired -- explicitly enumerated

Not part of the live `route_board.py -> router_v6` drawn-copper path:

- `core/ipc2152.py::ipc2152_min_width`'s own internal hardcoded
  positional `10.0` -- only reached via `deterministic/stages/power_plane.py`,
  which `router_v6`/`route_pcb` never imports. Not touched because ~10 of
  its own tests (`test_ipc2152.py::TestIpc2152MinWidth`) pin EXACT width
  values computed against this literal.
- `core/ipc2221.py`, `core/power_topology.py`: same "not on the live
  path" reasoning.
- `temper-placer/temper-constraints/src/ipc.rs`: a third, independently
  unsourced implementation, already rejected as an authority by this
  task's own brief, and not installed by `uv sync --all-packages` in this
  worktree at all (confirmed: `ModuleNotFoundError: No module named
  'temper_constraints'`, reproducing the prior task's own SS1.4 finding
  exactly, in 8 `test_stackup_gate.py` cases plus 4 more in
  `test_ipc2152_rust_differential.py`). `gates.py`'s own
  `_min_width_ipc2152`/`_ipc2152_forward` route through THIS crate, not
  `temper_drc_rs` -- flagged, not fixed (would mean either building an
  uninstalled crate with no way to verify the change here, or rewriting
  `StackupGate`'s DRC-check delegation target).

## 3. Why an A*-routed real trace was not used (and could not be)

### 3.1 Isolated single-net route: exhausted an 8GB cap and aborted

`_should_route`'s upstream pre-filter
(`is_hv_net('power_in.ntc-no')`/`is_power_net(...)`) independently
returns **False** for this net's literal dotted name -- a separate,
pre-existing classification gap (the SSOT-driven A*-exclusion branch,
`if _zone_layers_for_net(net_name): return False`, is never reached for
it) -- so A* was already permitted to attempt this net regardless of
anything in this task. To find out what actually happens, ran
`route_pcb()` against the REAL board's real obstacle geometry (pads/
footprints from `pcb/temper.kicad_pcb` itself) with the netlist filtered
to ONLY `power_in.ntc-no` (Stage 0's obstacle map is unaffected by
netlist filtering), under `ulimit -v 8000000` (8GB hard cap, chosen so a
repeat blowup fails as a clean crash rather than another system-wide OOM
kill).

**Result: exhausted the 8GB cap and aborted** ("memory allocation of 4
bytes failed", Rust allocator abort) rather than terminating with a
route-or-fail verdict -- for this ONE net in isolation, far cheaper than
the full ~139-net pipeline. A separate full-board attempt (before this
isolation test) was independently OOM-killed by the kernel at ~59GB RSS
(`dmesg`/`journalctl -k`: `Out of memory: Killed process ... (python3)
total-vm:67304044kB, anon-rss:59341568kB`), confirming this is a real
router robustness gap when a wide net's clearance-respecting path is very
hard or impossible to find, not a full-pipeline aggregate effect.

Per this task's own instructions ("report rather than relaunch if yours
dies"), neither run was relaunched.

### 3.2 Consequence for `_net_policy.py`

Given A* is unsafe for this net, `_should_route` now explicitly EXCLUDES
every `_CONTINUITY_EXEMPT_NETS` member from A* -- checked BEFORE, and
overriding, the `is_power_net`/`is_ground_net`/`is_hv_net` pre-filter, so
this protection holds regardless of that other, unrelated
name-classifier gap. (An earlier version of this same commit attempted
the OPPOSITE -- deliberately letting A* attempt this net alongside its
pour, on the theory that the pour needed a supplementary routed trace to
be scored connected. That was reverted the same day once the memory
blowup was measured; see the git history on this branch for the full
back-and-forth, kept as 3 separate, individually-buildable commits rather
than squashed, since each one is independently informative about what
was tried and why it changed.)

## 4. `test_production_board_drc_regression` -- status, not touched

Not run against this task's own changes (no full production route was
completed -- SS3). The ratchet's own status from the originating task
(median 1648 vs ratchet 1425, already red) is unaffected either way by
this task's diff, since nothing here alters what gets routed onto
`pcb/temper.kicad_pcb` itself. Not touched; no `R27 Ceiling-Approval:`
trailer sought or granted.

## 5. What is genuinely still needed

Stated plainly, per this task's own explicit instruction to say so
rather than work around a genuine gap:

1. **A router robustness fix** for A*'s handling of a net whose
   clearance-respecting path at its assigned width is very hard or
   impossible to find -- it should terminate (route or fail) within
   bounded memory, not exhaust multiple GB and abort. This is the
   mechanism that could, if fixed, deliver a genuinely continuous,
   obstacle-routed, ampacity-adequate trace for this net (and for any
   other wide/tight net this board's future work touches) automatically,
   rather than via hand-tuned waypoints. Out of scope for this task
   (a router-core change, not a net-realization decision).
2. **Or**, re-place `K1`/`RT1`/`U1`/`U2` to shorten the distances between
   this net's 4 pads and/or open a clear corridor between the board's two
   component clusters they straddle -- Task 1's own third, "expensive,
   justify only if the first two genuinely fail" option. Both of the
   first two (pour, hand-routed stitch) have now genuinely failed the
   ampacity requirement (SS1.4/SS1.6), so this option is no longer
   merely theoretical -- it is the most likely path to an actually
   current-adequate conductor without a router-core fix.
3. **Or**, a human, visual PCB-CAD routing pass for just this one net,
   which can see and route around obstacles (like `C6`) that this task's
   blind, empirically-tested-by-trial-and-error waypoint approach could
   only find by repeated real-DRC measurement, not by design.

## 6. Files changed

- `packages/temper-drc-rs/src/ipc.rs` -- `TRACE_TEMP_RISE_C`/
  `POUR_TEMP_RISE_C` constants.
- `packages/temper-drc-rs/src/ipc_pyo3.rs` -- pyo3 defaults + exposed
  constants.
- `packages/temper-placer/src/temper_placer/core/ipc2152.py` -- two
  convenience wrapper defaults.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` --
  `StackupGate._DEFAULT_TEMP_RISE_C`.
- `packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`
  -- `assign_trace_widths`'s default + docstring.
- `packages/temper-placer/src/temper_placer/router_v6/_net_policy.py` --
  `_should_route` excludes `_CONTINUITY_EXEMPT_NETS` from A*.
- `packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py`
  -- `_CONTINUITY_EXEMPT_NETS`, `_CONTINUITY_EXEMPT_NET_SMD_PAD_POSITIONS`,
  `_CONTINUITY_EXEMPT_NET_VERIFIED_EDGES`, `_stitch_pads_to_each_other`.
- This document.

`pcb/temper.kicad_pcb` is untouched throughout (sha256 unchanged,
verified repeatedly, including immediately after every `kicad-cli`
invocation against copies/splices written elsewhere).
