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

**Revision note:** §4 (board-size verdict) was rewritten after a
coordinator review challenged its first-pass claim that "only 2 of 4
copper layers are usable." That challenge was correct to press — the
original claim did not check `select_routing_grids`, the power-plane
generators, or the committed board's actual per-layer copper, and the
corrected §4 reverses the verdict's direction: the constraint measured
today is a hard-coded 2-layer cap in the A* engine (software), not the
board's physical layer count (hardware). §§1-3 and §5 are unchanged from
the first pass.

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

## 4. Is the board large enough? **REVISED — see the errata note below. Verdict: unresolved, and for a reason that changes the shape of the answer — the constraint measured today is software (a hard-coded 2-layer cap in the A* engine), not the board's physical layer count.**

> **Errata (this section rewritten after coordinator review).** The first
> version of this section claimed "only 2 of 4 copper layers are ever
> usable for signal routing" and concluded the board must grow or gain
> layers. That claim was checked against the actual committed board and
> against code the first pass never reached (`select_routing_grids`,
> `power_plane.py`'s pour generators, and `docs/hardware/POWER_PLANE_DESIGN.md`),
> and it does not survive: **`In1.Cu`/`In2.Cu` are two fully fabricated,
> currently 100%-copper-free layers, and nothing in this pipeline's
> current, real behavior — not Stage 4, not the plane generator — ever
> writes anything to either of them.** This is not "the board is too
> small"; it is closer to the coordinator's hypothesized "the router is
> failing to use two copper layers the board already has," with one
> substantial qualifier: exploiting that capacity safely is a nontrivial
> software project, not a one-line fix, and this task did not attempt it
> (out of scope for diagnosis, and a naive version of it has a
> directly-documented failure mode — see §4.3).

### 4.1 Where the 2-layer restriction actually lives (both parts, exact code)

**Part A — the layer-role classification is correct and lets all 4
layers through.** `RouterV6Pipeline.run()` (`_pipeline_core.py`) parses
with `use_declared_layer_roles=True` (landed in `8abcec24`, present on
this branch — confirmed: `git merge-base --is-ancestor 8abcec24 HEAD`
succeeds). This classifies layer role by structural stackup position
(outer = signal, inner = mixed), not by an existential zone-quantifier
bug the same commit fixed. `ChannelSkeletonStage.run()`
(`channel_skeleton.py`) was also fixed in the same commit to stop
hardcoding skeleton extraction to the literal names `"F.Cu"`/`"B.Cu"` and
now builds a skeleton for every layer `routing_spaces` contains. Verified
directly on this branch: no `"F.Cu"`/`"B.Cu"` literal filter remains in
`channel_skeleton.py` (grep confirms only stale comments referencing old
perf numbers). This matches the coordinator's independent measurement
exactly (204,500 skeleton edges across 4 layers: F.Cu 114,632 / In1.Cu
29,956 / In2.Cu 29,956 / B.Cu 29,956) — **Stage 2 genuinely builds real,
substantial, unblocked routing raw material for all four layers.**

**Part B — Stage 4 never asks for it.** Two places, both exact:

1. `select_routing_grids()`, `_pipeline_route.py:463-487`:
   ```python
   primary = occupancy_grids.get("F.Cu") or next(iter(occupancy_grids.values()))
   alternate = occupancy_grids.get("B.Cu") or next(
       (candidate for name, candidate in occupancy_grids.items() if name != primary.layer_name),
       None,
   )
   return primary, alternate
   ```
   This always returns exactly 2 grids. Called unconditionally at
   `_pipeline_route.py:586` inside `_run_stage4` — the `if
   pathfinding_result is None:` guard around it is not a real branch:
   `pathfinding_result = orchestrated.assemble_pathfinding_result(state)`
   (line 583) is called on a `state` that was just freshly constructed
   two lines above and never run through `Stage4Orchestrator.run()`, so
   `state.pathfinding_result` is always unset and `assemble_pathfinding_result`
   (`stage4_orchestrator.py:59-62`, a bare `getattr(state,
   "pathfinding_result", None)`) always returns `None`. `select_routing_grids`
   therefore runs on every production route.
2. `run_astar_pathfinding()`'s own signature caps it a second, deeper way
   (`_astar_reconstruct.py:89-120`): the function takes one `grid`
   (primary) and one `alternate_grid: OccupancyGrid | None` — singular,
   not a list — and builds `all_grids: dict[str, OccupancyGrid] =
   {grid.layer_name: grid}` (line 118), optionally adding the one
   alternate (line 119-120). **No code path anywhere in this project ever
   passes more than 2 grids.** Confirmed by history, not absence of
   effort to look: `git log --all -S"alternate_grids"` (plural) returns
   zero commits, across the entire repository's history.

**Both parts are needed and neither is new debt from `8abcec24`** — that
commit's own message scopes itself explicitly to "F.Cu/B.Cu" and never
claims to change Stage 4's layer consumption. `select_routing_grids`
predates it (`b39b382d`, 2026-07-29) and was written for a *different*
world: at that time, `_extract_stackup()`'s zone-quantifier bug
misclassified F.Cu/B.Cu as `plane` (condemning them) whenever *any* zone
on them sat on a plane-required net, so **In1.Cu/In2.Cu were the *only*
grid-backed layers available**, and `select_routing_grids`'s
name-preference fallback (`.get("F.Cu") or next(...)`) existed precisely
to substitute inner layers in for outer ones when the latter were
unavailable — not to combine all four. `8abcec24` fixed the
misclassification (F.Cu/B.Cu are correctly `signal` again), which means
`select_routing_grids` now finds F.Cu/B.Cu present and picks them by
name preference, silently dropping the extra 2 grids Stage 2 still
builds — the *correct* outcome for a 2-signal-layer board, but arrived at
by a name-preference accident rather than an explicit plane-role check.
This is a real, narrow, honest hardening gap (`select_routing_grids`
should gate on layer role, not on literal names) but — per §4.2-4.3
below — it is not gating away real signal capacity today, because
nothing else is either.

### 4.2 Is the 2-signal-layer design itself deliberate? **Yes — this part of the original verdict was correct and is now better-cited.**

`docs/hardware/POWER_PLANE_DESIGN.md` (REQ-ELEC-05, **Status: Implemented**)
specifies the stackup explicitly: L1 (`F.Cu`/TOP) = HV pours + power
components (signal), L2 (`In1.Cu`/GND) = **continuous ground reference
plane**, L3 (`In2.Cu`/PWR) = **power distribution / domain planes**, L4
(`B.Cu`/BOT) = control signals, digital, gate drive (signal) — with a
stated impedance-control rationale (50Ω microstrip L1→L2, referenced to
the L2 plane). `power_plane.py::generate_ground_pour`/`generate_power_pours`
implement exactly this: `generate_ground_pour` floods the **entire board
rectangle, unconditionally, on `In1.Cu`** (100% of 35,568mm²);
`generate_power_pours` partitions `In2.Cu` into 3 domain strips
(`DEFAULT_POWER_DOMAINS = ("+3V3", "+5V", "+15V")`) spanning the full
152mm board width minus 2×`DEFAULT_ISOLATION_GAP_MM` (0.3mm) = 151.4mm —
**99.6% of `In2.Cu`**. Neither generator has any copper-awareness (no
keepout carved for pre-existing traces): a real 4-layer board built to
this spec genuinely has only 2 signal layers. A companion evidence doc
independently confirms this boundary already received direct engineering
scrutiny, not silence: `docs/evidence/2026-07-28-stackup-partial-revert.md`
measured forcing F.Cu/B.Cu to `signal` (an earlier, over-corrected attempt
at what `8abcec24` later did properly) and found it cost a **12×
completion regression** (38.5% → 3.12%) on the July board, because outer
layers already carried real per-net zone-pour copper for creepage/thermal
reasons — that doc closes with an explicit, still-open flag: *"Should
this board's outer layers be poured at all?"*.

### 4.3 But the plane design is not actually realized anywhere in this pipeline's current output — which is the load-bearing correction.

Measured directly against the committed `pcb/temper.kicad_pcb` (not
inferred): **every existing zone (96), every committed segment (2290),
and every committed via (48) is on `F.Cu`/`B.Cu` only.**

```
zones by layer:    {'F.Cu': 48, 'B.Cu': 48}
segments by layer:  {'F.Cu': 1193, 'B.Cu': 1097}
via layer pairs:    {('F.Cu','B.Cu'): 24, ('B.Cu','F.Cu'): 24}
```

`In1.Cu`/`In2.Cu` carry **zero copper of any kind** in the artifact that
actually gets routed, DRC'd, and measured — not a sliver, not a partial
pour, nothing. And critically, nothing in this pipeline's real behavior
is currently positioned to change that:

- `enable_manufacturing_drc` — the only flag that invokes
  `generate_power_planes` at all — defaults to `False`, and
  `scripts/route_board.py`'s own comment says why: *"stays at its False
  default deliberately -- it is reporting-only, does not affect
  pathfinding."* Every completion-rate measurement to date (the
  established finding, both of this task's fresh runs) used that
  default — `In1.Cu`/`In2.Cu` were never even hypothetically poured
  during any of them.
- Even when `enable_manufacturing_drc=True`, `generate_power_planes`'s
  output (`geometry`) only ever feeds a log line
  (`_pipeline_verify.py:350`, *"Power planes: GND pour on %s..."*) and a
  `ManufacturingReport` violation count. **It is never merged into
  `routed_pcb_content`** — traced through `_pipeline_core.py`'s
  `manufacturing_report` field and `_adapter_convert.py:820`'s
  `routed_pcb_content=routed_content` construction; the pour geometry has
  no path to the output board at all in the current code.
- The mechanism that *does* write real zone-pour copper into production
  output — `_zone_pour_stitch.py::_zone_layers_for_net()`, active by
  default (`enable_zone_pours=True`) and directly responsible for the
  established finding's 12 zone-only nets (`SW_NODE`, `DC_BUS_RTN`,
  `ac_l`, `ac_n`, ...) and the 96 committed zones above — **only ever
  returns `["F.Cu", "B.Cu"]`** (`_zone_pour_stitch.py:63`). It has no
  `In1.Cu`/`In2.Cu` branch either.

So the honest, complete picture: **`In1.Cu` and `In2.Cu` are real,
physically fabricated, currently and durably empty copper layers.**
REQ-ELEC-05 says they *should* eventually carry continuous/near-continuous
reference and domain planes, and the Python to generate exactly that
pour geometry exists and is correct — but it is wired into a report-only
path that never reaches the board this project actually measures,
routes, or (per the committed file) fabricates against. There is,
concretely, **no code today that would conflict with a hypothetical
Stage-4 trace placed on either inner layer** — my original claim that
such a trace would be "silently overwritten/shorted" by a later pour step
was checked against the actual code path and does not hold: that pour
step does not write to the board at all, today, regardless of Stage 4.

### 4.4 Why this is not, therefore, a green light — and why §3's recovery estimate stays "unquantified"

Two real obstacles remain, both concrete, neither hand-waved:

1. **The A* engine has no N-layer via-transition logic**, only a 2-layer
   one (`_astar_route_multilayer`'s primary/alternate structure, §4.1).
   Extending it is a real search-algorithm change (how to drop a via onto
   a 3rd/4th layer, cost-model and capacity-accounting implications for
   Stage 3's SAT model, `select_routing_grids`'s role-based hardening from
   §4.1) — not a parameter tweak, and explicitly out of scope for a
   diagnosis-only task (per this task's own constraint: "do not change
   router behavior").
2. **A directly-relevant, already-measured precedent shows the naive
   version of "just let it route on an extra layer" produces fake
   completion.** `b39b382d`'s commit message: a rejected competing fix
   that routed a tree-route edge "on some grid-backed layer anyway" (when
   the pad's real layer had no grid) reported 41.6% vs 26.3% completion,
   but emitted 23,605 extra segments landing on `In1.Cu` that never
   touched their intended `F.Cu` pad — DRC got *worse* (398 vs 396
   unconnected items) despite the higher completion number. "The extra
   completion is fake." A hasty 4-grid extension to `run_astar_pathfinding`
   risks reproducing exactly this failure mode if via-drops onto the new
   layers aren't done correctly.

Given both, this task did **not** attempt to prototype N-layer A* (even
as a throwaway, read-only-style diagnostic) to produce a real recovered-net
count — doing so safely requires exactly the engineering work in
obstacle (1), and doing it unsafely risks reproducing obstacle (2)'s
already-documented trap. §3's ranked interventions and their
"unquantified" recovery estimates stand unchanged.

### 4.5 Revised verdict

**Not "the board is too small."** The board has four real copper layers;
two are currently, measurably, 100% unused by any part of this pipeline —
neither routed by Stage 4 nor (despite existing, correct code to do so)
actually filled with the planes they are speced for. Whether opening them
to real signal routing would recover some, most, or none of the 52
failing nets is a **genuine, currently open, empirically-testable
question that this task did not answer** — not because the layers are
unavailable (they are not), but because answering it safely requires
implementing real N-layer A* routing, which is a software project with a
known failure mode to avoid, not a diagnostic measurement. The
highest-leverage next step for this board is very likely **that software
project**, not a hardware change (grow the board / add a 5th-6th layer) —
my original verdict had this backwards. If that project is later
attempted and still leaves a meaningful gap, growing the board becomes
the fallback question, but the evidence gathered in this task does not
support jumping there first.

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
- Iteration-cap-not-binding claim (§5):
  `docs/evidence/2026-07-27-forced-segment-analysis.md` Parts 3–5
  (pre-existing, cited not re-run in full — the 8x sweep is expensive and
  its conclusion is orthogonal to this task's new questions; this task's
  own Run 2 independently reproduces the same *class* of zero-blocker
  exhaustion on the current board, corroborating rather than merely
  citing).
- §4 (revised after coordinator review): `_pipeline_route.py:463-487`
  (`select_routing_grids`), `:586`, `:592`; `_astar_reconstruct.py:89-120`
  (`run_astar_pathfinding` signature, `all_grids` construction);
  `stage4_orchestrator.py:59-62` (`assemble_pathfinding_result`); commit
  `8abcec24` (`fix(router): open F.Cu/B.Cu to real routing instead of the
  plane-condemnation fallback`, confirmed ancestor of this branch's HEAD
  via `git merge-base --is-ancestor`) and commit `b39b382d` (`fix(router):
  pick a tree route layer that actually has an occupancy grid (#386)`,
  origin of `select_routing_grids` and the "fake completion" precedent);
  `docs/hardware/POWER_PLANE_DESIGN.md` (REQ-ELEC-05, Status: Implemented);
  `docs/evidence/2026-07-28-stackup-partial-revert.md`; `power_plane.py`
  (`generate_ground_pour`/`generate_power_pours`, `DEFAULT_POWER_DOMAINS`,
  `DEFAULT_ISOLATION_GAP_MM`); `_pipeline_verify.py:340-364`
  (`generate_power_planes` call site, report-only); `_adapter_convert.py:820`
  (`routed_pcb_content` construction, no plane geometry merged in);
  `scripts/route_board.py:149-152` (`enable_manufacturing_drc` False-by-
  design comment); `_zone_pour_stitch.py:40-63` (`_zone_layers_for_net`,
  `["F.Cu", "B.Cu"]` only); committed-board zone/segment/via layer counts
  measured directly against `pcb/temper.kicad_pcb` with a short read-only
  Python snippet using `re.findall` over the file's own `(zone
  ...)`/`(segment ...)`/`(via ...)` blocks (metadata extraction, not a
  copper-accessor re-derivation).
