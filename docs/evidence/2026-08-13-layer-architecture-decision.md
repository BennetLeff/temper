<!-- provenance: commit=8fc9c9967e11a8079d224b91a0117e6301c467f1 dirty=UNKNOWN -->
fix/layer-architecture-ssot, based on origin/fix/board-schematic-resync @ a3fbaff37, fast-forward
merged onto origin/fix/pcb-stackup-declaration @ bdd17a162 (PR #1153, unmerged as of this writing)
so this document's stackup edits extend PR #1153's `(setup (stackup ...))` block rather than
re-declaring it, per this task's own instruction to build on that SSOT. docs/hardware/FAB_CAPABILITY.md
and docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md are cherry-picked file-for-file from
origin/docs/jlcpcb-fab-capability-envelope @ ccc795ccc (PR #1142, unmerged) rather than merged as a
branch, to avoid pulling in ~5,600 unrelated lines from that branch's far-diverged base -- see this
branch's own commit e330a0efd. Every routing-capacity, DRC, and JLCPCB-capability number cited below
is either (a) reproduced/cited from a named prior evidence document with its own independent
provenance, or (b) sourced from a live web fetch with URL and retrieval date (2026-08-13), or (c)
newly derived arithmetic from (a)/(b), shown with its inputs. pcb/temper.kicad_pcb's `(stackup)` and
`(layers)` blocks are edited in this change (declaration only); no track, via, zone, footprint, or
DRU/clearance/creepage value is touched -- confirmed by DRC re-measurement in Sec 6. -->

# Layer architecture decision: 6-layer (add In3.Cu/In4.Cu as dedicated signal layers), keep In1.Cu/In2.Cu exactly as declared planes

**Recommendation, up front: Option A -- declare a 6-layer stackup.** Add two new signal layers
(`In3.Cu`, `In4.Cu`) flanking the existing `In1.Cu`/`In2.Cu` plane pair. Leave `In1.Cu` (GND) and
`In2.Cu` (PWR) exactly as PR #1153 already declared them -- same role, same copper weight, same
physical position relative to each other. This is a **declaration-only** change: no track, via, or
zone is added, moved, or deleted; `pcb/temper.kicad_pcb`'s `(stackup)`/`(layers)` blocks change, its
copper does not.

**The three numbers that decide it:**

1. **Capacity roughly doubles, converting a proven-infeasible bound into a comfortable one.**
   PR #1172 measured this board's 2-signal-layer channel capacity at **8546 mm²** against
   **11236.6 mm²** of routing demand -- **utilization 1.31**, a provable bin-packing lower bound
   that guarantees net failures regardless of algorithm (`resource_bound.py`'s own soundness proof;
   confirmed empirically: 40/139 nets found zero legal path on the real board). Two more signal
   layers of the same board area contribute roughly the same capacity each (~4273 mm²/layer,
   8546/2): **4 signal layers -> ~17092 mm² capacity vs. the same 11236.6 mm² demand ->
   utilization ~0.66.** This is arithmetic on cited, previously-measured inputs, not a new
   measurement -- see Sec 1 for the derivation and its stated approximation (equal capacity per
   layer; not independently re-measured per-layer here).
2. **JLCPCB confirms 2oz outer copper is a standard, non-special-order option on 6-layer
   multilayer, at the same 0.15mm/0.15mm minimum trace/space floor 4-layer 2oz already clears.**
   Sourced live, 2026-08-13 (Sec 2). The floor does not tighten by adding layers.
2b. **Exact price and lead-time delta vs. 4-layer are NOT obtainable from this fab without a real
   design upload** -- JLCPCB's quote tool is a dynamic SPA with no static pricing page; confirmed by
   direct fetch (Sec 2.3). What is confirmed: 6-layer is marketed as a standard, fast-turn product
   ("as fast as 48 hours," promotional pricing "from $2/5pcs"), not a DFM-review specialty tier.
   No dollar or day figure is invented here.
3. **The alternative that's "free" in fab cost (Option B, converting `In1.Cu`/`In2.Cu` to mixed
   signal+plane) does not touch fab cost or lead time at all, but risks the thing this board
   actually depends on those two layers for**: the sole continuous ground-return path for a
   20.7-22.5 A rms resonant tank on 38 kHz half-bridge switching with 50 V/ns dV/dt, and the
   sole reference plane this design's own EMI strategy is built around (Sec 3). No formal
   ampacity failure is provable -- a solid 1 oz plane carries 22.5 A trivially -- but fragmenting
   it for signal channel space is a direct, documented conflict with this repo's own
   `GROUNDING_EMI_STRATEGY.md`/`POWER_PLANE_DESIGN.md` design rules (continuous flood, minimal
   cuts, single star-point connection), and the capacity it would recover is smaller and less
   certain than Option A's clean +2 layers, since enough continuous copper must stay unfragmented
   to preserve the return path.

**Option C (grow the board) is ruled out on its own evidence, not re-litigated here**: PR #1151
found the current 152 x 234mm outline is explicitly "rung 1" of a documented four-rung tightening
ladder (`docs/METHODOLOGY.md` §10) whose stated direction is to shrink toward a teardown enclosure
envelope, not grow -- and that the board's 234mm length may **already** exceed the one real cited
enclosure figure (chassis width ~230mm, itself flagged "needs verification"). Growing the outline
moves in the opposite direction from the project's own plan and risks an enclosure violation this
repo cannot currently rule out. See Sec 4.

**Safety: this recommendation does not touch, weaken, or newly exercise the isolation barrier.**
The two new signal layers carry LV/SELV traffic only, by policy (Sec 5) -- every netclass that is
pinned to a specific copper layer today (`HighVoltage`/`HighVoltageTank` -> `B.Cu`,
`GateDriveHV`/`HighVoltageIsolated` -> `F.Cu`) stays pinned to its existing outer layer; `In3.Cu`/
`In4.Cu` are declared `signal` but are **not** added to the router's actual routable-layer set in
this change (Sec 6.3) -- so no HV/mains net can reach them even accidentally, including `ACMains`,
whose `required_layer` is `None` (unconstrained) today. Creepage is a surface (X-Y) phenomenon,
unaffected by layer count by construction (Sec 5.1); no clearance-through-dielectric question is
opened because no HV copper is placed on any new layer. The existing isolation-keepout barrier
mechanism (`scripts/check_isolation_keepout.py`) already spans "every copper layer the board's own
stackup declares of type signal," so it generalizes to the two new layers automatically, with no
code change, the moment (if ever) that gate's own separately-tracked, pre-existing gap (no keepout
zones exist on the board yet -- unrelated to this change) is closed.

---

## 1. Routing capacity: the numbers, and what is and is not measured here

### 1.1 Inputs, cited

| Quantity | Value | Source |
|---|---:|---|
| Signal-layer channel capacity (today, 2 layers: F.Cu + B.Cu) | 8546 mm² | PR #1172, `docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md` §4, citing `docs/evidence/2026-08-13-clearance-1085-remediation-exec-steps-1-2.md` Sec 2.5 (`resource_bound.py`'s own live measurement against the real, committed board) |
| Routing demand (139-net board, current placement) | 11236.6 mm² | same source |
| Utilization (today) | 1.31 | same source, `demand / capacity` |
| Nets with zero legal path (measured, reproduced) | 40 / 139 | PR #1172 §1, reproduced from the task's own cited figures |
| Nets fully pad-connected (measured, reproduced) | 53 / 139 | PR #1172 §1 |

### 1.2 Derivation for a 6-layer (4-signal-layer) stackup

Per-layer capacity, assuming the 2 existing signal layers contribute roughly equally (both are the
same board outline, same obstacle density from components mounted on both sides):

```
capacity_per_layer = 8546 mm^2 / 2 = 4273 mm^2/layer
```

Four signal layers (F.Cu, In3.Cu, In1.Cu-role-unchanged... -- see Sec 1.3 for why In1.Cu/In2.Cu
themselves are NOT counted as signal capacity here):

```
capacity_4_layer = 4273 mm^2/layer * 2 NEW layers + 8546 mm^2 existing = 17092 mm^2
utilization_4_layer = 11236.6 mm^2 / 17092 mm^2 = 0.657
```

**This is arithmetic on cited numbers, not a fresh geometric re-measurement of the new layers'
capacity** -- there is no copper on `In3.Cu`/`In4.Cu` to measure yet (this is a declaration-only
change, Sec 6). The approximation this rests on (each new signal layer contributes about as much
free channel area as the existing two) is reasonable for two layers of the same board outline with
similar component/via obstruction, but is explicitly **not** independently verified per-layer here.
0.657 clears both the proven-infeasible bound (>1.0, Sec 1.4) and this change's own new fail-closed
gate threshold (Sec 7) with real margin (~0.34 headroom before the 1.0 bound, vs. today's -0.31
deficit).

### 1.3 `In1.Cu`/`In2.Cu` are not counted as new signal capacity

Both remain declared `power`-role planes in this change, unchanged from PR #1153. They contribute
zero new A*-routable channel capacity under this recommendation -- see Sec 3 for why converting them
to mixed use was considered and not recommended.

### 1.4 Why utilization > 1.0 is a provable bound, not a heuristic estimate

`packages/temper-placer/src/temper_placer/router_v6/resource_bound.py`'s own docstring: "Theorem
(bin-packing lower bound): for items with sizes s_i and bin capacity C, the maximum number of items
is `max{k : sum(smallest k) <= C}`... If k_max < N, at least N - k_max nets MUST fail --- no
algorithm can succeed because even the smallest k_max+1 demands exceed capacity." At 1.31 utilization
the aggregate demand exceeds aggregate capacity outright; not every individual net need fail (the
bound is about aggregate area, and fill-factor is itself an approximation of real trace geometry),
but the aggregate deficit cannot be routed around by a better algorithm, a different net order, or
more router iterations -- exactly what PR #1172 independently confirmed at the per-net level (33/33
nets that reached a real A* search failed via `forced_segment_fail_closed`, not timeout or search-
bound exhaustion).

---

## 2. Fabricator capability: JLCPCB, 6-layer, sourced 2026-08-13

### 2.1 2oz outer copper on 6-layer

Fetched live from JLCPCB's own capability page and 6-layer-specific product pages, 2026-08-13:

| Parameter | 4-layer, 2oz (already sourced, PR #1142) | 6-layer, 2oz |
|---|---|---|
| Outer copper weight options | 1oz, 2oz (2oz "standard, not special-order") | **1oz, 2oz** -- listed identically: "Finished Outer Layer Copper: 1 oz / 2 oz (35um / 70um)" |
| Inner copper weight options | 0.5oz (**default**), 1oz, 2oz | **0.5oz (default), 1oz, 2oz** -- unchanged |
| Min. track width & spacing, 2oz multilayer | 0.15 / 0.15 mm (6/6 mil) | **0.15 / 0.15 mm (6/6 mil) -- identical figure, not broken out separately by layer count** ("Multilayer: 0.15/0.15mm" applies to both 4- and 6-layer per JLCPCB's own capability table) |
| Min. track width & spacing, 1oz multilayer | 0.09 / 0.09 mm | **0.09 / 0.09 mm -- identical** |

Sources: <https://jlcpcb.com/capabilities/pcb-capabilities> (fetched 2026-08-13, cross-checked
against PR #1142's own 2026-08-13 fetch of the same page); <https://jlcpcb.com/6-layer-pcb> and
<https://jlcpcb.com/resources/6-layer-pcbs> (both fetched 2026-08-13). **The 2oz-multilayer
trace/space floor does not tighten when going from 4 to 6 layers** -- it is the same published
number both places. No "Advanced options ... require DFM review" language applies to a 6-layer/2oz
combination specifically; that phrase (present on the general capabilities page) is about the
2-layer-only 2.5-4.5oz heavy-copper tier, not this board's configuration, per PR #1142 §2 item 3
(re-confirmed here for the 6-layer-specific pages, same finding).

### 2.2 Inner-copper default caveat, now applying to 4 layers instead of 2

PR #1142 already found: JLCPCB's inner-copper **default** is 0.5oz, not the 1oz this repo's
current-capacity derivations assume (`TRACE_WIDTH_CALCULATIONS.md` §1) -- an explicit "1oz inner"
order-form note is required regardless of layer count, or the default silently applies. This change
extends that same requirement to 2 more inner layers (`In3.Cu`, `In4.Cu`, declared 1oz in Sec 6) --
**not a new risk category, the same pre-existing one PR #1142 already flagged, now with twice the
surface**. `scripts/check_stackup_copper_weight_gate.py` is extended in this change (Sec 7.1) to
enforce all four inner layers against the same assumed weight, closing this for the new layers the
same way PR #1153 closed it for the original two.

### 2.3 Price and lead time: what is and is not obtainable

Fetched 2026-08-13:

- <https://jlcpcb.com/6-layer-pcb> and <https://jlcpcb.com/resources/6-layer-pcbs>: "as fast as 48
  hours for 6-layer PCBs"; "5pcs 6-layer PCBs starts from $2" (promotional headline price, not a
  real quote for this board's dimensions/copper weight/quantity).
- <https://jlcpcb.com/blog/pcb-pricing-breakdown>: confirms layer count and copper weight both
  affect price ("each additional layer adds complexity... requiring more time and resources";
  heavier copper "significantly increase[s] manufacturing costs due to longer etching and plating
  times") but publishes **no numeric multiplier** for either factor.
- <https://cart.jlcpcb.com/quote> (JLCPCB's actual quote tool): confirmed by direct fetch to be a
  dynamic single-page app requiring an uploaded design (Gerbers) before any price renders --
  "Calculated Price: $0.00" with no design uploaded. **No static price table exists to cite.**

**Verdict: a real price/lead-time quote for this specific board (152 x 234mm-class outline, 6-layer,
2oz outer/1oz inner, ENIG) is not obtainable without submitting the actual design to JLCPCB's order
flow.** Per this task's constraint against inventing figures, no multiplier is stated. What is
sourced and stands on its own: 6-layer/2oz is a catalog-standard configuration at this fab, not a
custom/DFM-review tier, and its advertised turnaround class ("as fast as 48 hours") is in the same
fast-turn bracket JLCPCB markets its 4-layer service in -- there is no sourced indication this is a
slow or exotic option.

---

## 3. Option B (convert `In1.Cu`/`In2.Cu` to mixed signal+plane): the real trade, not a fab-cost one

### 3.1 What the two planes actually carry

`docs/hardware/GROUNDING_EMI_STRATEGY.md` (current, post-PR-#1153-correction) and
`docs/hardware/POWER_PLANE_DESIGN.md` (same) both declare, and this change does not touch:

- `In1.Cu` (L2, GND, 1oz): the split PGND/CGND/ISOGND reference plane. PGND's own declared contents
  include **"Resonant tank return"** and **"IGBT emitters (Q1, Q2)"** -- i.e., the tank circuit's
  20.7-22.5 A rms return current flows through this plane, plus the board's entire star-ground
  topology ("All ground return currents must flow through the star point").
- `In2.Cu` (L3, PWR, 1oz): the +5V/+3.3V/+15V power-island plane -- lower current (<=2A per island,
  §4.1), not the tank current path.

### 3.2 Ampacity is not the binding constraint; return-path/EMI integrity is

A solid 1oz copper plane carries 22.5A without difficulty -- plane current capacity scales with
usable cross-sectional width, and a plane's effective width is centimeters, not the sub-mm width an
IPC-2221B trace formula would imply. **No formal ampacity failure is claimed or provable for Option
B.** The real cost is structural: converting part of `In1.Cu` to routed signal channels means cutting
into the one continuous copper flood this board's own grounding strategy is built around --
`GROUNDING_EMI_STRATEGY.md` §3.3's ground-plane rules (not touched by this change) require "no
unnecessary cuts... minimize inductance" and route return current through a single star point;
`POWER_PLANE_DESIGN.md` §3.3 requires no traces crossing the ground split except at the star point.
Threading A*-routed signal traces through the plane's copper is, by construction, cutting it in
places the current design treats as inviolate. This is a real conflict with this repo's own
documented low-noise design for a 38 kHz half-bridge with 50V/ns dV/dt switching (both docs, §5.1 of
`GROUNDING_EMI_STRATEGY.md`) -- not a cost trade-off, a functional-integrity one.

### 3.3 The capacity gain is smaller and less certain than Option A's

Even setting the EMI concern aside: reclaiming signal-channel area from `In1.Cu`/`In2.Cu` can only
use the *fraction* of each plane not needed to preserve return-path continuity and current capacity
at the star point and around the switch node -- an amount this repo has not measured and cannot
currently bound (no plane-fragmentation-vs-capacity study exists in this repo). Option A's +2 full
signal layers is a clean, already-measured (Sec 1.2) capacity number; Option B's capacity gain is
real but unquantified and structurally smaller by definition (a mixed-use layer is not a full signal
layer). **Not recommended as the primary lever** for closing the 1.31 deficit; it remains available
as a smaller, targeted, separately-justified move (e.g., a single narrow signal escape routed through
a low-current corner of `In2.Cu` for one hard-to-route net) if a future, specific need arises -- that
is a different, much narrower decision than "declare both planes mixed-use" and is not what this
document evaluates or recommends.

---

## 4. Option C (grow the board): ruled out on existing evidence

Not re-measured here -- PR #1151 (`docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md`
§4) already resolved this question while evaluating an unrelated subsystem placement problem, and
its findings apply unchanged:

- Current outline: 152 x 234mm, `pcb/temper.kicad_pcb`'s `gr_poly (20,20)-(172,20)-(172,254)-(20,254)`
  -- unchanged by this document, hard constraint respected.
- Set 2026-07-25 as **"rung 1" of a deliberate four-rung tightening ladder**
  (`docs/METHODOLOGY.md` §10): true pad extents (132.2 x 213.6mm) plus a flat 10mm margin,
  **explicitly not an enclosure decision**, and explicitly meant to be tightened toward a teardown
  enclosure envelope at rungs 3-4 (never reached). The project's own stated direction is to shrink
  this outline, not grow it.
- The real mechanical constraint (`docs/specs/REQUIREMENTS.md:431-434`): a vintage RCA 12A3
  tube-amplifier chassis, external dims "~230mm W x 180mm D x 120mm H (approximate, needs
  verification)." Separately, `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md:74-79`
  flags that **the current board's 234mm length may already exceed the chassis's own stated 230mm
  width figure** -- unresolved which of the two repo figures is wrong.
- No verified chassis interior dimension exists anywhere in this repo to check a *larger* board
  against, and no PCB-fab cost-tier data exists to price a size increase (an invented $ figure would
  violate this task's own constraint against fabricated pricing).

Growing the board to close the capacity deficit would move directly against the project's own
documented plan, cannot currently be shown not to violate the one real enclosure figure this repo
has, and has no sourced cost data -- **ruled out**, consistent with, not independently re-derived
from, PR #1151's own verdict on the same question asked for a different reason.

---

## 5. Safety: isolation barrier and creepage/clearance, checked explicitly

### 5.1 Creepage is unaffected by layer count

Creepage (IEC 60335-1 Table 17/18) is a surface (X-Y, along-the-board) distance between conductive
parts -- PR #1152's own measurement (`docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md`)
confirms this repo's creepage enforcement is computed entirely in the board's XY plane via
`scripts/generate_kicad_dru.py`'s `(constraint creepage ...)` rules against pad/copper positions, with
no layer-count or Z-axis term anywhere in that computation. Adding two declared signal layers changes
nothing about any pad or copper object's XY position -- **creepage exposure is provably unchanged by
this document's stackup edit**, independent of what is ever routed on the new layers.
`HV_CREEPAGE_ENFORCED_MM` (currently 8.0mm/PD2, with PD3's 12.6mm separately determined to govern per
PR #1152 -- neither value touched here) is untouched.

### 5.2 Clearance-through-dielectric is a real question this document deliberately does not need to answer

The task correctly identifies that inner-layer clearance is a *thickness* question (solid-insulation
withstand through the dielectric between two copper layers, IEC 60664-1 territory), not a
surface-creepage one -- and that this repo does not currently have that analysis for any inner
layer. **This document does not perform that analysis, because its recommendation does not need
it**: `In3.Cu`/`In4.Cu` carry LV/SELV signal traffic only, by policy (Sec 5.3) -- no HV or mains
copper is ever placed on either new layer under this recommendation, so no HV-to-LV
through-dielectric proximity is ever created for this analysis to bound. If a future change wants to
route HV/mains signals on an inner layer, that change would need to perform this analysis first --
explicitly flagged here as **not done, and not needed for what this document recommends**.

### 5.3 Why HV/mains nets structurally cannot reach the new layers

Per-netclass `required_layer` (`packages/temper-placer/src/temper_placer/core/design_rules.py`,
unchanged by this document):

| Netclass | `required_layer` |
|---|---|
| `HighVoltage`, `HighVoltageTank` | `B.Cu` |
| `GateDriveHV`, `HighVoltageIsolated` | `F.Cu` |
| `ACMains` | `None` (unconstrained) |

Three of the five HV-adjacent classes are already pinned to an existing outer layer and cannot reach
`In3.Cu`/`In4.Cu` regardless of what the router considers routable. `ACMains` is **not** pinned
today -- a real latent risk if the router's routable-layer set were naively widened to match the
newly-declared signal-layer count. This document closes that risk structurally, not by policy alone:
Sec 6.3's SSOT reader deliberately does **not** add `In3.Cu`/`In4.Cu` to the router's actual
routable-layer set in this change (that requires occupancy-grid/obstacle-map infrastructure this
document does not build -- see Sec 6.4). So today, immediately after this change lands, `ACMains`
cannot reach either new layer, because nothing can: the router treats the routable-layer set exactly
as it did before this document, declared-layer-count notwithstanding.

### 5.4 The isolation-keepout barrier mechanism already generalizes correctly

`scripts/check_isolation_keepout.py`'s own LAYER SPAN check (`_COPPER_LAYER_TYPE = "signal"`, read
live via kiutils' `board.layers`) requires a keepout corridor to cover every copper layer the board's
own `(layers ...)` block declares `signal` -- not a hardcoded two-layer list. Verified directly
against the post-edit board (`uv run python scripts/check_isolation_keepout.py`):

```
Copper layers: 4 (F.Cu, In3.Cu, In4.Cu, B.Cu). Footprints examined: 168. Pads examined: 527
(HV=89, SELV=223). ...
FAILED -- 1 violation(s): No keepout zone named 'MAINS_SELV_ISOLATION_BARRIER' found on the board
```

The gate correctly, automatically picked up both new signal layers with zero code change -- exactly
the "already generalizes" claim, confirmed rather than merely argued. It still fails, for the
identical, **pre-existing** reason it failed before this change (`gate_input_registry` records it as
"baseline red on main (no keepout zones)" -- no keepout zone of any kind exists on this board yet, at
2 layers or 4): this document neither creates nor worsens that gap, and closing it is tracked
separately, outside this document's scope.

---

## 6. SSOT and enforcement -- see the accompanying PR body / commit series for the full change list

Summarized here; full detail in the commits:

### 6.1 SSOT ownership decision

`pcb/temper.kicad_pcb`'s `(layers ...)` block (per-layer role: signal/power/jumper) and
`(setup (stackup ...))` block (per-layer copper weight, dielectric build, total thickness) together
are the single source of truth for **layer count and per-layer role** -- they are the artifact a
fabricator actually receives, and PR #1153 already established the copper-weight half of this
precedent. `docs/hardware/FAB_CAPABILITY.md` owns **fabricator capability limits** (what JLCPCB can
build) and is extended (Sec 2), not restated, by anything that needs to know a manufacturing floor.
Neither file re-derives the other's numbers; each is edited in its own domain in this change.

### 6.2 The board file's stackup, after this change

6 copper layers, 5 dielectric layers, 1.6mm total (unchanged): `F.Cu` (2oz, signal) / prepreg 0.15mm
/ `In3.Cu` (1oz, **new**, signal) / prepreg 0.15mm / `In1.Cu` (1oz, power/GND, unchanged) / core
0.72mm / `In2.Cu` (1oz, power/PWR, unchanged) / prepreg 0.15mm / `In4.Cu` (1oz, **new**, signal) /
prepreg 0.15mm / `B.Cu` (2oz, signal). Copper sum 0.28mm + dielectric sum 1.32mm = 1.60mm, matching
the unchanged `(general (thickness 1.6))` declaration exactly. `In3.Cu`/`In4.Cu` are placed flanking
the existing plane pair (adjacent to `F.Cu`/`B.Cu` respectively) rather than renaming or
repositioning `In1.Cu`/`In2.Cu`, so every existing reference to those two names (router modules, both
hardware docs, the copper-weight gate) needed zero renaming -- only new names were introduced.
Exact impedance/dielectric-material optimization for a real fab order is explicitly **not** performed
here (declaration-only change; see hard constraints) -- the split above preserves total thickness
with a defensible, simple placeholder split, not a fab-engineered stackup.

### 6.3 Typed SSOT reader + router wiring

A new module, `temper_placer.core.board_layer_roles`, gives any caller a typed answer ("is this layer
signal or power, per the board's own declaration") via a `LayerRole` enum, plus a second, deliberately
narrower `routable_signal_layers()` accessor that additionally intersects with the router engine's
actual occupancy-grid/A* capability today (`ENGINE_SUPPORTED_SIGNAL_LAYERS = {"F.Cu", "B.Cu"}`) -- the
distinction Sec 5.3 depends on.

Three previously-hardcoded router call sites were surveyed (`router_v6/channel_mapping.py`'s
`_LAYER_ENUM_TO_KICAD`, `router_v6/_astar_nlayer.py`'s `select_routing_grids_nlayer`,
`router_v6/_zone_pour_stitch.py`'s `_zone_layers_for_net`), with three different outcomes:

- **`_zone_layers_for_net` -- wired**, the one confirmed-live production decision point
  (`scripts/check_layer_plane_emission_coverage.py`'s own docstring names it as the function
  `_adapter_convert.route_pcb` actually consults for zone-pour layer selection). Its hardcoded
  `["F.Cu", "B.Cu"]` literal is replaced with `board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED`
  -- still a hardcoded value (this specific call site needs router ENGINE capability, not per-board
  architecture -- see the module's own docstring for why those are different questions), but now
  centralized in one typed, documented place instead of duplicated. Zero behavior change (99 existing
  tests across `test_adapter.py`/`test_topology_copper_audit.py` re-run and pass unmodified; order
  preserved via an explicit ordered tuple, not `sorted(frozenset(...))`, since one call site indexes
  `[0]` as a preferred-layer default and alphabetical B-before-F sorting would have silently changed
  that).
- **`channel_mapping.py`'s `_LAYER_ENUM_TO_KICAD` -- surveyed, found dead, not touched.** Confirmed by
  grep across the whole package: this dict is defined but never read anywhere in the production module
  it lives in; the real logic it once represented moved to Rust (`temper-orchestration`'s
  `channel_mapping.rs`) during an earlier migration, leaving this a vestigial, unused literal. Wiring
  dead code to a new dependency adds risk (import-time coupling) for zero behavioral benefit --
  left alone, noted here for the next person who finds it.
- **`_astar_nlayer.py`'s `select_routing_grids_nlayer` -- surveyed, left unwired.** Its own docstring
  identifies it as a spike/prototype, not a production entry point; not exercised by `route_pcb()`.

Board-context threading was considered and rejected for `_zone_layers_for_net` specifically: it is
called from ~9 sites across 4 modules with signature `(net_name: str)` only, no board path or content
-- reading a hardcoded real-file path inside it would silently mis-attribute layer roles for any
caller processing a different (test/synthetic) board, and threading real board context through every
call site is a materially larger, separately-risky refactor this task does not need (see the module's
own docstring for the full argument for why the engine-capability constant is the *correct* fix for
this call site, not merely the safe one).

### 6.4 What this change deliberately does not build

Occupancy-grid, obstacle-map, and A*-routing support for `In3.Cu`/`In4.Cu` does not exist after this
change -- declaring them `signal` in the board file does not make the production router capable of
placing a single trace on them. That is real infrastructure work (Stage 2 grid construction, Stage 4
pathfinding layer selection, zone-pour emission) explicitly out of scope for this task (a layer-
architecture *decision* and its SSOT/gate codification, not an N-layer router implementation). The
existing, already-anticipated 6-layer fallback naming in `io/_parse_board.py`
(`["F.Cu","In1.Cu","In2.Cu","In3.Cu","In4.Cu","B.Cu"]`, a no-declared-stackup fallback path) is
consistent with the names chosen here, but that code path is not exercised by this board (which now
has a real declared stackup) and was not modified.

### 6.5 Measured DRC consequence of the layer-count declaration -- NOT absorbed into the ceiling, per this task's hard constraint

`AGENTS.md`'s "Board Change -> DRC Ceiling Re-measurement" convention requires re-measuring and
updating `power_pcb_dataset/drc_ceiling.json` in the same PR whenever `pcb/temper.kicad_pcb` changes.
This task's own hard constraints say the opposite for THIS document: "Do NOT change any... ratchet
ceiling." Measured directly (130-sample re-run, `temper_placer.validation._drc_api.run_drc`,
`--all-track-errors`, regenerated `.kicad_dru`, isolated by reverting/restoring only
`pcb/temper.kicad_pcb` in place, 5 samples on each side before committing to the full 130 -- method
matches this file's own established protocol) to find the honest answer, not to assume "declaration
only" implies zero DRC effect:

| Category | Before (2-signal-layer declaration) | After (6-layer declaration, this change) | Delta | Determinism |
|---|---:|---:|---:|---|
| `hole_clearance` | 90 (matches committed ceiling) | **94** | **+4** | 130/130 samples, both sides |
| `shorting_items` | 181 (matches committed ceiling) | **183** | **+2** | 130/130 samples, both sides |
| every other category (`annular_width`, `clearance`, `copper_edge_clearance`, `courtyards_overlap`, `drill_out_of_range`, `hole_to_hole`, `solder_mask_bridge`, `track_width`, `tracks_crossing`, `via_diameter`) | -- | -- | **0** | unchanged, both sides |
| `creepage` (already-nondeterministic) | {166,167,168} band (prior record) | {167: 5, 168: 125}/130 this session | within the existing band, max unchanged (168) | nondeterministic, unaffected by this change |

**Root cause, attributed, not merely observed:** a KiCad through-hole via or pad is electrically/
geometrically present on every copper layer between its declared endpoints by construction (a
plated barrel through the full board thickness) -- adding two more declared copper layers to the
stack means every EXISTING via/pad on this board (zero of which moved -- confirmed: this document's
diff to `pcb/temper.kicad_pcb` touches only the `(layers ...)`/`(setup (stackup ...))` blocks, no
`(via ...)`/`(pad ...)`/`(segment ...)` entry) now spans two more layers than before, which changes
the layer-crossing pairs `hole_clearance`/`shorting_items` check. Nothing physically moved; the
declared *stack depth* changed, and KiCad's DRC engine correctly re-evaluates hole-to-hole/hole-to-pad
proximity across the now-deeper stack.

**What this document does NOT do about it, and why:** this is exactly the shape of change
`AGENTS.md`'s ceiling-approval process (R27) exists for -- a measured, attributed, deterministic rise,
with a named cause, ready to approve. This document does not execute that approval: raising a ratchet
ceiling is explicitly listed among this task's own hard constraints as out of scope, and unlike PR
#1152's creepage finding (a policy decision "available at any time" the document chose not to
execute), this one is not optional if the 6-layer declaration is adopted as-is -- **landing this
board change for real, unmodified, will show `check_measurement_provenance.py` and
`ci_check_drc.py`/the DRC ratchet gate as failing**, because the real board now measures 94/183
against a committed ceiling of 90/181. Resolving that is a decision for whoever owns the
ceiling-approval process (a `Ceiling-Approval:` commit trailer plus this document's own measurement
as the required attributed cause), not a call this document makes for them. Stated plainly, per this
task's own instruction to say what is left undone rather than silently working around a hard
constraint: **this PR's `power_pcb_dataset/drc_ceiling.json` is deliberately NOT updated, and CI's DRC
gates are expected to go red on this exact diff until someone with authority to raise a ratchet
ceiling does so, citing this section.**

---

## 7. Type-level enforcement -- what was built, what wasn't, and why

Following PR #1167's convention (`initial_rotation` -> `initial_rotation_quadrant`: a Rust newtype
with no `Div`/`Mul`/`Deref` impl, proven via a `compile_fail` doctest, plus a Python static
textual-scan gate) as the pattern to match, not reinvent.

**Delivered -- Python side, real, matches the convention's spirit:**

- `LayerRole` (`core/board_layer_roles.py`): a proper `Enum` (`SIGNAL`/`POWER`/`MIXED`/`JUMPER`), not a
  bare string. `parse_declared_layer_roles()` returns `dict[str, LayerRole]`; a caller asking "can I
  route on `In1.Cu`" gets `LayerRole.POWER` back, typed, not a string that happens to read `"power"`
  this week. `is_signal_layer()` is the direct yes/no accessor.
- The engine-support intersection (`routable_signal_layers()` /
  `ENGINE_SUPPORTED_SIGNAL_LAYERS(_ORDERED)`) makes "route on a layer the engine doesn't actually
  support yet" structurally unreachable through this module's own API for the one production call site
  wired to it (Sec 6.3) -- not by convention, by construction: the accessor cannot return a layer name
  outside that set.
- 19 tests (`test_board_layer_roles.py`) plus 9 more for the utilisation gate, including a real,
  reproducible demonstration that this module's typed answer changes correctly between the pre-decision
  (2-signal) and post-decision (4-signal) board declarations.

**Not delivered -- a Rust newtype/`compile_fail` test mirroring PR #1167's Rust half.** Assessed and
found disproportionate for a different, load-bearing reason (not merely "ran out of time"):
investigating where the router's *actual* per-net layer decision lives (Sec 6.3's survey) found there
is no live Rust type at the FFI boundary a newtype could usefully wrap in the first place.
`packages/temper-rust-router/src/layer_assignment.rs` (a pinned, verbatim port of the Python
`assign_layers` oracle) has **no `Layer` enum at all** on the Rust side -- it matches net names
against regex patterns and returns plain integer layer codes (1-4), documented only in `//` comments
(`// Layer.L4_BOT: geometric_preferred_layer is always ...`) as corresponding to the Python-side
`Layer` enum's values. The Python `Layer` enum (`router_v6/channel_mapping.py`) never crosses the FFI
boundary as a typed value; it crosses as a bare integer the Rust side re-derives meaning for from a
comment. A newtype needs an existing type at the boundary to replace -- there is no `Layer::POWER`
variant a caller could wrongly construct and route on, because there is no Rust `Layer` type of any
kind to add one to. Building a *new* Rust-side typed representation (an actual enum, with a role
dimension distinguishing `In1.Cu`/`In2.Cu` from `In3.Cu`/`In4.Cu`, threaded through the FFI boundary
shared by 3+ crates) is real router-capability work, not a wrap-the-existing-thing rename -- the same
scope Sec 6.4 already excludes for occupancy-grid/A* infrastructure, for the same reason: it is router
implementation, not a layer-architecture declaration or its enforcement.

**What remains genuinely unenforced, stated plainly:** nothing on the Rust side stops a future change
to `layer_assignment.rs` (or any other Rust router module) from routing on an integer layer code that
corresponds to a power plane, because the Rust side has no representation of layer *role* at all today
-- only bare integers a `//` comment explains. The enforcement this PR actually has against that
mistake is the Python-side `board_layer_roles` module (for any NEW Python call site) and the two gates
(Sec 6, Sec 8) that would catch a resulting SSOT/router mismatch or capacity violation after the fact,
on the next CI run -- not a compile-time guarantee, and not covering Rust at all. An honest partial,
per this task's own instruction: real Python-level typing and one wired production call site, a
documented and reasoned decision not to extend it into Rust today (there being no existing Rust type to
extend), and a clear statement of what a determined future mistake could still get past.
