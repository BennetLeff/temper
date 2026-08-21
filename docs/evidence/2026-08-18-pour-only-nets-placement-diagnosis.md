<!-- provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false -->

# The nine pour-only nets: a placement and pour-topology diagnosis

**Date:** 2026-08-18. **Base:** `origin/main` @ `2abb246db697da2685a652b93632a42d11595d51`.
Worktree `temper-wt-analysis-pour-topology-placement`, branch
`analysis/pour-topology-placement`, cut from `origin/main`.
`pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
verified **before and after** every measurement below. **The board was
never written.** Env: `make venv-isolate` + `env -u CONDA_PREFIX make
extensions` (10/10 fresh); `pcb/temper.kicad_dru` regenerated from
`scripts/generate_kicad_dru.py` before any creepage number was read.

Driver scripts, all committed alongside this doc:
`2026-08-18-pour-only-nets-{net-policy,pour-fragmentation,pad-creepage-deficit,domain-partition,isolator-straddle,trace-freespace,trace-freespace-relaxed,cpsat-constraint-census}.py`.

---

## Headline

**The nine nets are not a routing problem and not a pour-topology problem.
They are a placement that already violates PD3 creepage at 39 of its own
59 pads, plus a verdict function that structurally refuses to credit a
pour as copper. Neither of those can be fixed by any router, any pour
shape, or any net ordering.**

Three independent findings, each sufficient on its own:

1. **No pour can ever score connected.** `NetRouteResult::verify_continuity`
   (`packages/temper-geometry/src/net_route_result.rs:204`) runs union-find
   over **pads, tracks and vias only** -- its own comment: *"Zones are
   OUTLINES, not copper ... `zone_pairs` deliberately empty"*.
   `pad_connectivity_audit.check_net_pad_connectivity` does the same;
   `zone_layers` only sets the advisory `zone_dependent_unmeasured` flag and
   never touches `fully_connected`. Six of the nine are excluded from A* by
   `_net_policy._should_route` *because* a pour covers them. The loop is
   closed by construction: policy says "the pour handles it", the verdict
   says "a pour is not copper."
2. **The board's 151 zone blocks are 100% unfilled.** `filled=0
   unfilled=151` (`zone_layers_and_fill_stats`). The emitted pours carry no
   `filled_polygon` at all, so they are not copper in the file either.
3. **A trace route is geometrically impossible for 8 of the 9**, and the
   9th (`ac_n`) only after forgiving its own pads' existing creepage
   deficit. See section 4.

---

## 1. Why these nets are zone-eligible-only

Measured (`net-policy.py`):

| net | netclass | routing_strategy | `_should_route` | continuity-exempt |
|---|---|---|---|---|
| `+170V_BUS` | HighVoltage | plane_required | **False** | no |
| `DC_BUS_RTN` | HighVoltage | plane_required | **False** | no |
| `PWR_RTN` | HighVoltage | plane_required | **False** | no |
| `SW_NODE` | HighVoltage | plane_required | **False** | no |
| `ac_n` | ACMains | plane_required | **False** | yes (class) |
| `power_in.ntc-no` | HighVoltage | plane_required | **False** | yes (net) |
| `tank.c_tank1-p2` | HighVoltageTank | plane_required | **True** | no |
| `w1_1` | HighVoltage | plane_required | **True** | no |
| `w1_2` | HighVoltage | plane_required | **True** | no |

The policy is **recorded and deliberate for eligibility, accreted for
exclusion**. `_zone_layers_for_net` derives eligibility from
`NetClassRules.routing_strategy` -- a documented SSOT decision with a full
change history (2026-07-28 `plane_required`, 2026-08-07 R4
`plane_preferred`). `_should_route`'s *exclusion* of those nets from A* is
the accreted half: it is justified in its own docstring only by "a pour
genuinely covers it", a premise finding 1 shows is unreachable.

**Three of the nine are A*-eligible and still have zero copper.**
`tank.c_tank1-p2`, `w1_1`, `w1_2` return `_should_route() == True` -- not
by design, but because `is_power_net`/`is_ground_net`/`is_hv_net` all
return False on those names (the name-classifier gap the
2026-08-14 ntc-no evidence doc records at SS1.4). They reach A*, get a
pour as well, and land nothing.

**Two stale comments found.** `PWR_RTN` is assigned to **HighVoltage**, not
GND. `GND`'s only member is `CGND` (which carries no zones). So
`_CONTINUITY_EXEMPT_CLASSES`'s `"GND"` entry is **dormant again**, and both
`_zone_pour_stitch.py:33-38` ("PWR_RTN, GND's only member with committed
zones") and `_emit_zone_pours`'s `pads_only` comment ("on this board is
CGND/PWR_RTN (GND class)") are wrong today. Consequence: `PWR_RTN` gets
`IslandPolicy::PadsOnly`, not the return-plane `KeepAll` those comments
assume.

## 2. Where the pour fragments -- the brief's split is CONFIRMED, with a correction

Reproduced `_emit_zone_pours` exactly (`pour-fragmentation.py`); the
reproduction matches the committed board's zone census on 35 of 36
(net, layer) rows.

| net | pads | clusters (pre-carve) | islands F.Cu / In3 / In4 / B | total | fragments at |
|---|---|---|---|---|---|
| `+170V_BUS` | 11 | **5** | 5/5/5/5 | 20 | **clustering** |
| `DC_BUS_RTN` | 8 | **5** | 3/3/3/3 | 12 | **clustering** |
| `PWR_RTN` | 15 | **13** (11 singletons) | 6/7/7/7 | 27 | **clustering** |
| `SW_NODE` | 7 | **5** | 3/4/4/4 | 15 | **clustering** |
| `tank.c_tank1-p2` | 4 | **3** | 2/3/3/3 | 11 | **clustering** |
| `w1_1` | 4 | **3** | 2/4/4/4 | 14 | **clustering** |
| `w1_2` | 3 | **2** | 2/2/2/2 | 8 | **clustering** |
| `ac_n` | 3 | **1** (exempt) | 0/2/2/2 | 6 | **carve** |
| `power_in.ntc-no` | 4 | **1** (exempt) | 1/2/2/2 | 7 | **carve** |

**Correction to the brief.** The briefed "19 islands for 11 pads" and "26
for 15" are **zone-block counts summed over four layers**, not per-layer
disjoint components. Per layer `+170V_BUS` has 4-5 zones. The committed
board's true `PWR_RTN` total is **27**, not 26.

**Second correction: the carve is net-*reducing*, not fragmenting, for the
seven clustered nets.** `PWR_RTN`'s 13 hulls yield 6-7 islands -- the carve
**deletes 6-7 hulls outright** (PadsOnly drops pieces with no surviving own
pad). Clustering is the sole fragmenter for those seven; the carve only
removes. For the two exempt nets, the single hull is intact until the carve,
which is where they split -- exactly the briefed split.

## 3. Would placement fix it? No -- and this is a mechanical decision, not a placer one

### 3a. 39 of 59 pads already violate their own required separation

`pad-creepage-deficit.py`, F.Cu obstacle set, separations resolved from
the regenerated DRU:

```
DC_BUS_RTN K3.1     min_gap  2.040mm  required 12.60mm  deficit +10.560
PWR_RTN    K2.1     min_gap  2.040mm  required 12.60mm  deficit +10.560
w1_2       K1.14    min_gap  4.050mm  required 12.60mm  deficit  +8.550
ntc-no     U1.2     min_gap  4.490mm  required 12.60mm  deficit  +8.110
+170V_BUS  U1.1     min_gap  5.423mm  required 12.60mm  deficit  +7.177
...
39 of 59 pads across the nine violate. Worst deficit: +10.56mm.
```

Independently confirmed by `kicad-cli pcb drc`, 3 runs intersected
(`--all-track-errors`, fp-lib-table sibling present): **379 errors,
287 stable, of which 102 stable `creepage`** -- e.g.
`('tank-out','tank.c_tank1-p2') 'HighVoltageTank functional creepage'
10.0000mm; actual 5.0000mm` and
`('gnd','power_in.ntc-no') 'HV to LV' 12.6000mm; actual 5.2152mm`.
These exist on a board whose nine nets have **zero copper** -- they are
placement violations, not routing violations.

### 3b. The two domains are fully interleaved

`domain-partition.py`, board = 38,376mm² (164 x 234 outline):

* 43 HV-only + 116 SELV-only + 9 straddling footprints.
* HV pad convex hull = **92% of board**; SELV hull = **103%**; overlap =
  **90%**.
* Current minimum HV-pad to SELV-pad edge gap = **0.000mm** (required 12.6).
* HV pads dilated by 12.6mm occupy **66.0% of the board**; the remaining
  34.0% for *all* SELV copper is in **13 disconnected pieces**.
* **152 of 420 SELV pads** currently sit inside the 12.6mm HV halo.

### 3c. The blocker is footprint geometry, not placement search

`isolator-straddle.py`, `evaluate_isolator_feasibility` at 12.6mm, both
barrier axes, all 4 rotations:

| isolator | achievable HV-SELV pad gap | need | verdict |
|---|---|---|---|
| `C6` | 8.00mm | 12.6 | **INFEASIBLE** (-4.60) |
| `K1` | 8.00mm | 12.6 | **INFEASIBLE** (-4.60) |
| `T1` | 9.10mm | 12.6 | **INFEASIBLE** (-3.50) |
| `T2` | 9.10mm | 12.6 | **INFEASIBLE** (-3.50) |
| `U6` | 8.10mm | 12.6 | **INFEASIBLE** (-4.50) |
| `K2` | 12.76mm | 12.6 | feasible |
| `K3` | 12.76mm | 12.6 | feasible |
| `PS1` | 35.50mm | 12.6 | feasible |

**5 of 8 isolators cannot straddle a 12.6mm corridor regardless of where
they are placed or how they are rotated.** This is a property of the parts,
not the layout. `docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`
already proved board expansion cannot change it (`evaluate_isolator_feasibility`
takes no board-dimension argument anywhere in its call graph); the K2/K3
swap since then moved the infeasible set from 7 to 5, and stalled there.

**Answer to "what would have to move": nothing that can move.** The
required change is **part substitution for C6, K1, T1, T2, U6** (creepage
+3.5 to +4.6mm on each part's own HV-to-SELV pad pitch), which is a
mechanical/BOM decision, not a placer input.

## 4. Is the mechanism wrong? Would traces work?

`trace-freespace.py` / `trace-freespace-relaxed.py`: exact shapely
free-space connectivity. Free space = board eroded by (half trace width +
0.5mm edge) minus every other net's copper dilated by
`max(DRU clearance, DRU creepage)` for that pair + half trace width.

The obstacle census is the whole story. For `+170V_BUS` on F.Cu:
**1,238 obstacles at 12.6mm**, 79 at 2.0, 8 at 0.5, 4 at 3.0, 4 at 10.0.
**93% of everything on the board demands a 12.6mm halo from this net.**

At the netclass spec width (HighVoltage 5.0mm, ACMains 3.0mm), free space
collapses to **3,700-5,400mm² of 38,376 (10-14%)**, shattered into 54-1,398
pieces, and only 0-4 of each net's pads land in it at all.

Relaxed test -- forgive the pads' own pre-existing violations, snap each pad
to its nearest free-space piece within 25mm, take the best of four layers:

| net | spec width | best layer | distinct corridors | verdict |
|---|---|---|---|---|
| `ac_n` | 3.0mm | In4.Cu | **1** | **FEASIBLE** |
| `power_in.ntc-no` | 5.0mm | In3.Cu | 2 | infeasible |
| `w1_2` | 5.0mm | F.Cu | 2 (+1 unreachable) | infeasible |
| `tank.c_tank1-p2` | 5.0mm | F.Cu | 3 | infeasible |
| `w1_1` | 5.0mm | In3.Cu | 3 | infeasible |
| `SW_NODE` | 5.0mm | F.Cu | 5 | infeasible |
| `DC_BUS_RTN` | 5.0mm | In3.Cu | 5 (+1 unreachable) | infeasible |
| `+170V_BUS` | 5.0mm | In3.Cu | 7 | infeasible |
| `PWR_RTN` | 5.0mm | In3.Cu | 8 (+2 unreachable) | infeasible |

Repeated at a 0.2mm width -- i.e. asking only "can *any* conductor get
there", ignoring ampacity entirely -- **eight of nine are still
infeasible**. The 5.0mm width is not the binding constraint; the 12.6mm
creepage halo against 1,238 SELV items is.

**`ac_n` is the single net of the nine for which a trace route is
geometrically possible.** Everything else needs the placement fixed first.

## 5. Is CP-SAT trying? No.

`cpsat-constraint-census.py` and direct reading of the call graph:

* `--loop` is the default (`cli/__init__.py:229-231`) and is what **both**
  flow scripts run (`scripts/run_clean_flow.sh:47` passes `--loop`
  explicitly; `run_physics_flow.sh` takes the default).
* `_loop_core.py:84-110` builds `solver_kwargs` with exactly:
  netlist, board, extra_constraints, timeout_ms, seed, zones,
  zone_components, loop_components, (+ reference_aliases, loop_aliases,
  validator_input, body_collision_input). **No `tank_creepage`, no
  `isolation_barrier`, no `heatsink_colocation`.** `PlaceRouteLoop.run()`
  has no parameter for them either -- they cannot be reached from the loop
  path at all.
* `tank_creepage={"margin_mm": 10.0}` appears **only** at
  `cli/__init__.py:676`, inside the `--no-loop` branch. Confirmed.
* `generate_domain_clearance_constraints` is called only from
  `cli/repair_commands.py` (`repair-unplaced`). Confirmed.
* Consequence nobody has stated: `validator_input` **is** forwarded on the
  loop path, but `_encoder_solve.py:791` filters
  `constraint_objects` to `c.id.startswith("domain_clearance_")` -- and on
  the loop path that set is **empty**. The REQ-SAFE-01 post-solve audit runs
  against zero constraints and can only report coverage gaps, never raise.

**What the production placer actually imposes.** The only separation family
alive on the loop path is `generate_netclass_separated_constraints`:
**8,949 constraints**, min_distance_mm histogram
`{6.0: 6439, 0.5: 1995, 2.0: 393, 0.15: 84, 0.25: 38}` -- **maximum 6.0mm**.
4,887 of them touch the 36 components carrying the nine nets, at 6.0mm
(4,535) and 2.0mm (352).

The 6.0mm figure's own `because` string reads:
*"UNSOURCED legacy 6.0mm (debunked 'Table 16 working isolation at 400V'
citation ...)"*.

**So the production placement runs with no creepage or isolation constraint
at all** -- only a debunked 6.0mm component-box separation, against a DRC
that grades the same pairs at **12.6mm**. The model is under-constrained by
**6.6mm on every HV-to-SELV pair**, and by 4.0mm on the tank's HV-to-HV
functional pairs (2.0mm imposed vs 10.0mm graded). That is a sufficient
mechanical explanation for section 3a's 39 violating pads: **the solver was
never asked.**

Arming it changes nothing on its own: section 3c shows the barrier
constraint is UNSAT for five isolators regardless.

---

## What this escalates to

1. **Mechanical / BOM (blocking, not automatable):** substitute `C6`, `K1`,
   `T1`, `T2`, `U6` for parts with >= 12.6mm HV-to-SELV pad separation.
   Until then no compliant placement exists, at any board size.
2. **Placer (correct but not sufficient):** arm the loop path with
   `domain_clearance` / `isolation_barrier` / `tank_creepage`, and raise the
   netclass auto-constraint off the debunked 6.0mm onto the DRU figures the
   DRC actually grades. This will return UNSAT until (1) lands -- which is
   the honest answer, and better than silently placing at 6.0mm.
3. **Router (independent of both):** the nine nets need a mechanism whose
   output `verify_continuity` can credit -- pads/tracks/vias. Today they are
   excluded from A* *because* of a pour that cannot count. `ac_n` is the only
   one routable as a trace on the current placement.
4. **Not the bottleneck:** the nine are 9 of 79. Of the other 70,
   **64 have no copper at all** and 6 are partials (`+3V3` 3/50, `gnd` 5/88,
   `+15V` 1/10, `vcc` 1/13, `V_BUS_SENSE` 1/4, `GATE_LS` 2/3). Fixing all
   nine moves the board from 60/139 to at most 69/139.
