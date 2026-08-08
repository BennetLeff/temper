<!-- provenance: commit=6121c49f05c1b8f4f7245d0c5204091cfb5dfa8a (agent/router-combined) dirty=true -- this doc + the three new read-only diagnostic scripts are the dirty diff in this task -->

# Placement-remediation analysis: where the congestion is, which components cause it, what to move, and whether the board fits

**Date:** 2026-08-08

**Task:** Diagnosis only, per this task's own instructions — no router-behavior
change, no `pcb/temper.kicad_pcb` edit. Board routing completeness is
placement-bound, not software-bound (established finding, `agent/router-combined`
@ `6121c49f`: 64/110 nets carry copper, 52 nets fail in Stage 4 A* with
genuine multi-net geometric congestion, 0/52 dominated by HV clearance).
This document determines *where* that congestion is, *which* component
placements cause it, *what* to move, whether the *board itself* is large
enough, and resolves the 3 of 52 failures recorded with an empty
`blocking_nets` list.

**Method:** Two independent full production routes of `pcb/temper.kicad_pcb`
on the combined-fix worktree (`agent/router-combined` @ `6121c49f`,
`scripts/route_board.py`-equivalent call: `route_pcb(parsed_stub, {},
design_rules=..., enable_net_batching=True, net_batch_size=10)`), run in
parallel in a dedicated worktree
(`.claude/worktrees/placement-remediation-analysis`, branch
`agent/placement-remediation-analysis`, never checked out in the primary
checkout):

1. `scripts/rcm_blocking_diag.py` (pre-existing, unmodified) — reproduces
   the established per-net blocker classification. Wall time 742.6s
   (~12.4 min).
2. `scripts/rcm_empty_blocker_diag.py` (new, read-only monkeypatch of
   `_astar_route_with_ripup`, same technique as (1) — never touches
   production code) — captures `channel_path.waypoints`, whether a route
   path was found at all, `forced_segment_count`, and the straight-line
   `get_blocking_nets()` result per waypoint segment, for the 3 named
   empty-blocker nets specifically. Wall time 739.3s (~12.3 min).

Both reproduced the established headline exactly: **52/52 same failing
nets, completion_rate 0.5, 0/52 blocker lists majority-HV, median blocker
count 7** (mean 7.38, sum of blocker counts across all 52 nets = 384,
spanning 46 distinct blocker net names). This is a third and fourth
independent reproduction of the established numbers (the combined-config
evidence doc already reproduced them twice); the run in this task adds a
fifth data point at 0 spread on the failure set itself.

Component and pin geometry for the spatial analysis below comes from
`temper_placer.io.kicad_parser.parse_kicad_pcb()` (the project's real
parser, not an ad hoc s-expression scrape) via a new script,
`scripts/rcm_pin_positions.py`, plus a text-property extraction for
footprint `Sheetpath`/`at`/courtyard-outline metadata (component
placement and human-readable subsystem labels only — never copper) used
only to name and locate components, not to compute anything
copper-related. `topology_copper_audit.nets_carrying_copper()` was not
needed in this task (no copper-count question was re-derived; the 64/110
figure is taken as given per the established finding), but the accessor
convention it fixed is respected throughout.

All three new scripts are committed alongside this document, diagnostic
only, no router behavior changed: `scripts/rcm_empty_blocker_diag.py`,
`scripts/rcm_pin_positions.py`, `scripts/rcm_spatial_analysis.py`.

---

## 1. Where is the congestion, spatially? (concentrated, not diffuse)

The board outline (`pcb/temper.kicad_pcb`, single `Edge.Cuts` rectangle,
read via `parse_kicad_pcb().board`) is **152mm × 234mm** (origin
(20, 20), far corner (172, 254); 35,568 mm² total).

Each of the 52 failing nets' own-pin centroid (average of its own pad
positions — a proxy for "where this net needed to route", from real pad
positions, not approximated) was bucketed into a 3×3 grid over the board
extent (each cell ≈ 50.7mm × 78.0mm, 11.1% of board area):

| Region | Failing nets (own-pin centroid) | Blocker-net occurrences (blockers' own centroid, sum=384) |
|---|---:|---:|
| **MID-MID** (x 70.7–121.3, y 98–176) | **22** | **117 (30.5%)** |
| MID-LEFT (x 20–70.7, y 98–176) | 8 | 50 (13.0%) |
| TOP-MID (x 70.7–121.3, y 20–98) | 7 | 58 (15.1%) |
| MID-RIGHT (x 121.3–172, y 98–176) | 3 | 77 (20.1%) |
| BOTTOM-MID (x 70.7–121.3, y 176–254) | 3 | 25 (6.5%) |
| BOTTOM-RIGHT | 3 | 8 (2.1%) |
| TOP-RIGHT | 3 | 7 (1.8%) |
| TOP-LEFT | 2 | 20 (5.2%) |
| BOTTOM-LEFT | 1 | 22 (5.7%) |

**Verdict: concentrated, not diffuse.** MID-MID — an 11.1%-of-board-area
cell at the physical center of the board — hosts 22/52 (42%) of failing
nets by own-pin location and 30.5% of all recorded blocker occurrences,
both the single largest share by a wide margin over any other cell.
(Two of the 22 MID-MID nets, `+3V3` and `gnd`, are board-spanning rail
nets whose "centroid" is an artifact of averaging dozens of decoupling-cap
pads everywhere on the board, not a real single location — excluding
them, MID-MID still holds 20/50 (40%) of the remaining, genuinely
localized failing nets.) MID-MID, MID-RIGHT, and TOP-MID together account
for 65.6% of all blocker occurrences in just 33% of board area — a
horizontal band across the board's mid-height is where nearly two-thirds
of the congestion signal originates, with MID-MID as its epicenter.

---

## 2. Which components are responsible?

### 2.1 MID-MID: a mixed-voltage subsystem pile-up

Fifteen components have their footprint anchor inside MID-MID: `C15,
J1, PS1, R16, R4, R58, R67, R71, TP1, TP2, U20, U25, U4, U6, U7`. Their
`Sheetpath` properties (read from the board file, not inferred) show this
is not one subsystem crowded by its own pin count — it is **five
unrelated subsystems physically stacked on top of each other**:

| Ref | Sheetpath | Footprint | Local courtyard |
|---|---|---|---:|
| `PS1` | `aux_supply.psu` | `Converter_ACDC_MeanWell_IRM-10-xx_THT` | **46.2 × 25.9mm** |
| `U7` | `hb.gate_hs.driver` | `SOIC16W_Isolated` (reinforced-isolation gate driver) | 11.9 × 10.8mm |
| `U6` | `hb.power_loop.q_low` | `TO-247-3_Vertical` (half-bridge low-side switch) | 16.4 × 5.5mm |
| `U4` | `power_mgmt.buck_3v3.buck` | SOT-23-6 buck regulator | — |
| `U20` | `safety.wdt.wdt` | SOT-23-5 watchdog | — |
| `U25` | `safety.fault_or3` | SOIC-14 | 7.4 × 9.2mm |
| `R58` | `safety.ovp.r_adc_top3` | 1206 resistor (OVP divider) | — |
| `R67` | `safety.coil_thermal.r_ref_top` | 0603 resistor | — |
| `R71` | `safety.uvlo_logic.r_div_bot` | 0603 resistor | — |
| `TP1`/`TP2` | `safety.tp_shutdown` / `safety.tp_fault` | test points | — |
| `R16` | `discharge.r_coil2` | 1206 resistor | — |
| `R4` | `power_in.r_bleed1` | 2512 resistor (HV bleed) | — |
| `C15`, `J1` | `aux_supply.c_out`, `thermal.j_fan` | — | — |

`PS1` — a mains-isolated AC/DC converter module with a 46.2×25.9mm body,
the single largest footprint anywhere near this cell — sits at its
geometric center (104.1, 124.6). Immediately around it: the isolated
gate driver `U7` (85.9, 142.4), the TO-247 switching FET `U6` (100.1,
159.3), and a dense field of small-pitch safety-comparator resistors and
test points (`R58/R67/R71/TP1/TP2/U20/U25`, all within ~15mm of each
other, all requiring 0.2mm-clearance fine routing threaded between
components carrying `HighVoltage`/`GateDriveHV` 6.0mm-clearance nets on
their own pins).

Cross-referencing against the top blocker-net list (most-frequent blocker
across all 52 failing nets' `blocking_nets`, from `rcm_blocking_diag.json`):

| Blocker net | Blocks (of 52) | Region | Component(s) |
|---|---:|---|---|
| `discharge.k_dis1-coil2` | 22 | MID-MID | `K2` (discharge relay coil) |
| `discharge.k_dis1-nc` | 20 | MID-RIGHT | `K2` |
| `safety.uvlo_logic-line` | 19 | MID-RIGHT | UVLO comparator net |
| `hb.gate_hs.driver-p2` | 18 | MID-MID | `U7` |
| `power_in.r_zcd_top1-p2` | 18 | MID-RIGHT | ZCD divider |
| `safety.ovp.r_adc_top2-p2` | 18 | MID-RIGHT | OVP divider |
| `safety-line-1` | 17 | TOP-MID | safety bus |
| `hb.gate_hs.driver-p1-1` | 16 | MID-LEFT | `U7` |
| `GATE_HS` | 15 | MID-LEFT | gate-drive signal |

`U7` (the isolated gate driver) supplies 2 of the top-8 most-frequent
blockers by itself (34 blocking occurrences combined) — its footprint and
the 6.0mm `GateDriveHV`/`HighVoltageIsolated` clearance envelope on its
own pins sit directly in the busiest through-traffic path.

### 2.2 HV relay clearance envelopes at the MID-MID/MID-RIGHT and TOP-LEFT seams

`K2` (`discharge.k_dis1`, Schrack RT314012 relay, 29.9×13.6mm courtyard,
6.0mm clearance/creepage on its contact nets) sits at (144.8, 97.6) —
essentially on the TOP/MID row seam, in the RIGHT column. Its contact
nets (`discharge.k_dis1-nc`, `discharge.k_dis1-coil2`) are the #1 and #2
most frequent blockers on the whole board (22 and 20 occurrences). `K3`
(`discharge.k_dis2`, same part) sits at (66.9, 50.6), TOP-LEFT, and its
contact net `discharge.k_dis2-nc` is #10 (14 occurrences). Both relays
carry the mandatory 6.0mm IEC 60335-1 clearance/creepage envelope
required for the discharge circuit (this document does not, and per the
task's hard constraint cannot, propose relaxing that) — the envelope
itself is non-negotiable, but *where* it is centered on the board is a
placement choice, and both relays currently sit adjacent to (not inside,
but bordering) the MID-MID/TOP-MID congestion band.

### 2.3 A ~211mm forced cross-board bus through the congestion band

`U27` (the ESP32-S3 MCU, `mcu.mcu`) sits at (34.1, 48.0), TOP-LEFT.
`U9` (the RTD front-end ADC, `rtd_pan.adc`) sits at (95.4, 249.9),
BOTTOM-MID, 4.1mm from the board's bottom edge. Straight-line distance:
**≈211mm**, on a 279mm-diagonal board — i.e. this one bus spans essentially
the full board. Six of the 52 failing nets are exactly this SPI/status
bus or its immediate neighbors (`RTD_DRDY`, `cs_n`, `sdi`, `sdo`,
`vbias`, `refin_n`, all terminating at `U9` and/or its divider network
`R36`–`R42`/`U10`), plus `i2c_sda_ui`, `WDT_KICK`, `WDT_RESET_N`,
`RELAY_CTRL` — all of which terminate at `U27` and are also in the failing
set. Every one of these must cross the MID band (rows TOP–MID or
MID–BOTTOM) to connect a component pinned to one edge of the board to a
component pinned to the opposite edge, through the same corridor already
occupied by §2.1/§2.2's components.

---

## 3. Ranked candidate interventions

No placement change was applied or measured end-to-end in this task (out
of scope — diagnosis only, `pcb/temper.kicad_pcb` is off-limits). Ranked
by the concreteness of the evidence tying each candidate to recovered
nets; recovery counts are **unquantified** unless stated otherwise, since
no re-placement + re-route was run.

1. **Relocate `PS1` (AC/DC converter, 46.2×25.9mm) out of MID-MID**, to an
   edge position near the other `aux_supply.*`/`power_in.*` components
   (e.g. along the board's left or bottom edge, away from the
   `hb.*`/`safety.*` cluster). This is the single largest footprint inside
   the single worst region (§2.1) and its body currently occupies space
   directly in the path between the discharge-relay/gate-drive block and
   the safety-comparator resistor field. **Unquantified recovery**, but
   directionally the strongest single candidate: it is the largest
   removable obstruction in the highest-blocker-density cell.
2. **Widen the corridor around `U7` (isolated gate driver) and `U6`
   (TO-247 switch)** — together responsible for 3 of the top-9
   most-frequent blockers (`hb.gate_hs.driver-p1-1`, `-p2`, and indirectly
   `GATE_HS`/`GATE_LS`). Moving `U7` a few mm toward the board edge (it
   currently sits mid-corridor at (85.9, 142.4)) would let more of
   MID-LEFT's traffic route around rather than through its 6.0mm
   isolation envelope. **Unquantified.**
3. **Shorten the `U27` (MCU) ↔ `U9` (RTD ADC) bus** (§2.3, currently
   ~211mm end to end): either move `U9` and its divider network
   (`R36`–`R42`, `U10`) toward TOP-LEFT nearer `U27`, or move `U27`
   toward BOTTOM-MID nearer the RTD front end — whichever is cheaper given
   `U27`'s other fan-out (I2C/PWM/watchdog nets, several of which are
   also in the failing set). This directly targets 10 of the 52 failing
   nets (6 RTD/SPI-bus nets + `i2c_sda_ui`/`WDT_KICK`/`WDT_RESET_N`/
   `RELAY_CTRL`) by removing the forced full-board traversal, not just
   reducing local density. **Unquantified**, but the mechanism (a
   shorter, more direct channel needs to cross less occupied territory)
   is more directly load-bearing than a density argument alone.
4. **Redistribute the safety-comparator resistor/test-point field**
   (`R58, R67, R71, TP1, TP2, U20, U25`, all within ~15mm of each other
   in MID-MID) — lowest-priority of the four, since these are the
   smallest bodies (0603/SOT-23/SOIC-14) and the least likely to be the
   binding obstruction on their own; more likely to help only after 1–3
   above open real channel width for them to spread into.

**A single-component nudge is unlikely to be sufficient on its own.**
Median blocker count per failing net is 7 (73% have ≥1 HV-class blocker
*and* a majority of ordinary-clearance blockers, per the established
finding) — most individual failures are jointly caused by several of the
components above simultaneously, not any one in isolation. Recommend (1)
and (3) together as the first placement iteration to measure, since they
target the two largest, most independent obstructions (one body, one
distance) rather than density in general; re-route and re-measure with
`scripts/rcm_blocking_diag.py` after any placement change to get a real
number rather than continuing to estimate.

---

## 4. Is the board large enough? **No — not as currently specified, at 2 usable signal layers.**

Stated plainly, per this task's instruction not to soften the answer if
the evidence points this way:

- **The stackup has 4 copper layers** (`F.Cu`, `In1.Cu`, `In2.Cu`,
  `B.Cu`, confirmed directly from the board's own `(layers ...)` block),
  **but only 2 are ever available to the router for general signal
  escape/routing.** `In1.Cu` is reserved wholesale for the GND reference
  plane and `In2.Cu` for per-domain power pours
  (`power_plane.py::generate_ground_pour`/`generate_power_pours`,
  `channel_mapping.py`'s own comment: *"Inner layers (In1.Cu / In2.Cu)
  are reference/power planes, not A* routing layers"*). Verified directly
  in `_pipeline_route.py:592`: the A* stage is built with exactly one
  primary grid (`F.Cu`) and one `alternate_grid` (`B.Cu`) — no
  `In1.Cu`/`In2.Cu` `OccupancyGrid` is ever constructed for A* at all.
  110 nets — including every fine-pitch SPI/I2C signal *and* every
  6.0mm-clearance HV/HV-isolated net — compete for those same 2 layers.
- **50% of attempted Stage-4 nets fail** (52/104 A*-attempted nets,
  `completion_rate: 0.5` in this task's own fresh measurement, matching
  the established finding exactly) **after two independent, real
  correctness fixes were already applied and measured net-neutral**
  (`agent/router-combined`'s own evidence doc: 64/110 nets carrying
  copper both before and after Fix A+B combined, from offsetting
  +6/−6 changes, not from either fix doing nothing).
- **This is not an iteration-budget artifact.** A prior, independent
  investigation on this same router
  (`docs/evidence/2026-07-27-forced-segment-analysis.md`) swept the A*
  per-net iteration cap from 500k to 4,000,000 (8×) on the full board and
  found **the failure count never moved** — at 4M, 56/59 of that day's
  failures provably exhausted their entire reachable search space, and
  only 3/59 were still cap-limited (at a cap already near the grid's
  total cell count). Raising the cap further has nothing left to search.
  This task's own instrumentation (§5 below) directly reproduces the same
  class of exhaustion on the current, larger 110-net board.
- **The congestion is concentrated, not marginal**: median 7 simultaneous
  blockers per failing net (§1), 73% of failures have at least one
  6.0mm-clearance blocker *and* a majority of ordinary-clearance blockers
  in the same list — meaning even a hypothetical perfect placement fix
  for the HV envelopes would still leave the ordinary-clearance
  congestion in place (established finding, confirmed again in this
  task's fresh run: 0/52 nets have HV blockers as a list majority).

**Verdict:** the evidence supports "the board is too tightly constrained
as currently specified" over "this is a placement-tuning problem that
will close with enough nudges." The clearest, safety-compliant paths
forward are architectural, not incremental: (a) recover real routing
capacity from an inner layer — e.g. a split/stitched plane on `In2.Cu`
that leaves channel gaps for signal traces instead of a solid domain
pour, or (b) add a 5th/6th copper layer. Placement fixes (§3) may recover
some fraction of the 52 failures — the interventions above are concrete
and worth trying and measuring — but nothing measured in this task or the
router-combined lineage demonstrates that placement alone, at 2 usable
signal layers, reaches 100% completion. This is an assessment from the
congestion signature and layer-budget facts above, not a formal
capacity/feasibility proof — no exhaustive placement search was run.

---

## 5. The 3 zero-blocker failures: resolved

`discharge.r_snub1-p2`, `tank-out`, and `w1_2` were recorded with an
**empty** `blocking_nets` list — the established finding flagged this as
unexplained and requiring examination (this project has found twelve
"reports green / cannot fail" mechanisms already; an unexplained empty
list is exactly that shape).

**Traced with `scripts/rcm_empty_blocker_diag.py`** (monkeypatches
`_astar_route_with_ripup` to capture `channel_path.waypoints`, whether a
route path was returned at all, `forced_segment_count`, and the
straight-line `get_blocking_nets()` result per waypoint pair — read-only,
never touches production code). All three nets show the **same
mechanism**, captured directly from the real production route:

| Net | Waypoints | `forced_segment_count` | Straight-line blockers |
|---|---|---:|---|
| `discharge.r_snub1-p2` | (122.72, 244.66) → (121.60, 249.56) | 1 | **[]** |
| `tank-out` | (49.10, 124.48) → (60.94, 142.01) | 1 | **[]** |
| `w1_2` | (98.41, 227.65) → (32.90, 210.10) | 1 | **[]** |

All three are ordinary 2-waypoint (2-terminal) nets. For each, every
search tier — 2D primary grid, 2D alternate-layer grid, and the
3D via-aware fallback (`_astar_route_multilayer`'s full tier stack) — was
attempted and **none found a legal, clearance-respecting path at all**
(not "found one but it required an illegal shortcut" — genuinely no path,
triggering the `allow_forced_segments=False` early-return at
`_astar_search.py:308`). Critically, the direct straight line between the
two endpoints is **not occupied by any other net's copper either**
(`grid.get_blocking_nets()` returns empty for the segment on both grids
checked). This is why `blocking_nets` is empty: `_identify_blocking_nets`
only ever reports something when a *forced/attempted* path exists to
inspect; here, none did.

**This is not a new bug and not congestion-by-a-specific-net — it is
genuine A*-search infeasibility given the current placement and iteration
budget**, the same mechanism `2026-07-27-forced-segment-analysis.md`
already characterized and directly ruled out as budget-limited (Part 5 of
that doc: "immediate exhaustion," 2/59 nets with zero straight-line
blockers on that day's smaller, 96-net board — this is the same class of
failure recurring at 3/52 on the current, denser, 110-net board, not a
regression or a new mechanism).

**`w1_2` (and its sibling `w1_1`) additionally has a real, independent,
documented root cause beyond generic exhaustion.** `w1_2`'s far
endpoint is `K1` pad `"14"` — read directly from the footprint block in
`pcb/temper.kicad_pcb` (component `K1`,
`temper:Relay_SPST_Omron-G4A-E`): pad `"14"` is declared
`smd rect (layers "F.Fab")` — **`F.Fab` is a fabrication-drawing layer,
not a copper layer**; no `*.Cu`/`F.Cu`/`B.Cu` entry is present for this
pad at all. The footprint's own hand-authored `descr` field states this
was deliberate: *"Contact terminals (13=COM, 14=NO) are #250 ... Faston
quick-connect tabs ... these tabs have zero PCB copper connection on this
variant; they mate externally with a push-on spade connector, not a PCB
trace. Modeled here as SMD (no-drill) landing pads purely for
netlist/footprint pin-count parity and courtyard/placement-clearance
purposes -- NOT a claim that solder-in-hole geometry exists at these
exact coordinates."* The net (`w1_2`, pad 14 = NO contact) is being
routed by A* against a pad that was authored, on record, to never carry
real PCB copper. The router's failure to find a path to it is, in this
one case, geometrically correct behavior against a target that cannot
have PCB copper by the footprint's own design intent — a
netlist/footprint-modeling mismatch (the schematic net expects a copper
connection; the footprint explicitly declines to provide a copper
landing site), not a placement congestion problem. `w1_1` (targeting the
sibling pad `"13"`, same relay, same `F.Fab` non-copper declaration) is
also in the 52-failure list, but *did* pick up 5 straight-line blockers
on its own topology's waypoints (its channel path routes through a
different, occupied corridor before reaching the same non-copper
terminal) — the F.Fab-pad issue is the root cause for the far endpoint
being unreachable either way; whether the recorded `blocking_nets` list
is empty or not depends on which straight line the net's own topology
happened to be assigned, which is incidental. **This is out of scope to
fix in this document** (no router-behavior or board change permitted
here) but is worth flagging as a genuine finding for a future task: either
`w1_1`/`w1_2` should not be modeled as router-completable nets at all
(the connection is a wire-to-spade-lug, not PCB copper), or `K1`'s
footprint needs real copper pads if a PCB trace to these contacts is
actually intended.

---

## 6. Sources / reproduction

- Base: `agent/router-combined` @ `6121c49f` (established finding: 64/110
  copper, 52/104 Stage-4 failures, 0/52 HV-majority).
- This task's worktree: `.claude/worktrees/placement-remediation-analysis`,
  branch `agent/placement-remediation-analysis`, never checked out in the
  primary checkout.
- Run 1 (blocker reproduction): `scripts/rcm_blocking_diag.py --output
  <path>`, wall 742.6s, 52/52 same failing nets as established, 0/52
  HV-majority, median 7 blockers — exact reproduction.
- Run 2 (empty-blocker deep dive): `scripts/rcm_empty_blocker_diag.py
  --repo-root <worktree> --output <path>` (new script, committed
  alongside this doc), wall 739.3s, captures per-segment straight-line
  blocker data for `discharge.r_snub1-p2`/`tank-out`/`w1_2`.
- Spatial data: `scripts/rcm_pin_positions.py` (new, uses
  `temper_placer.io.kicad_parser.parse_kicad_pcb`) +
  `scripts/rcm_spatial_analysis.py` (new, combines pin positions with
  `rcm_blocking_diag.json`'s per-net blocker lists into the region
  breakdown in §1).
- Board outline/layers/component footprints/courtyards: read directly
  from `pcb/temper.kicad_pcb` (`Edge.Cuts` polygon, `(layers ...)`
  block, per-footprint `F.CrtYd` graphics and `Sheetpath` properties).
- Layer-usage-for-routing claim (§4): `channel_mapping.py` comment +
  `power_plane.py` (`generate_ground_pour`/`generate_power_pours`) +
  `_pipeline_route.py:592` (`alternate_grid=None if self.single_layer
  else bcu_grid` — only F.Cu/B.Cu grids ever built for A*).
- Iteration-cap-not-binding claim (§4, §5):
  `docs/evidence/2026-07-27-forced-segment-analysis.md` Parts 3–5
  (pre-existing, cited not re-run in full — the 8x sweep is expensive and
  its conclusion is orthogonal to this task's new questions; this task's
  own Run 2 independently reproduces the same *class* of zero-blocker
  exhaustion on the current board, corroborating rather than merely
  citing).
