---
title: Block Decomposition of Routing on the Atopile Hierarchy — Plan
type: feat
date: 2026-08-07
topic: routing-block-decomposition
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
product_contract_source: ce-plan
execution: code
status: draft
---

# Block Decomposition of Routing on the Atopile Hierarchy — Plan

`docs/STRATEGY.md` build order step 8: *"Block decomposition of routing on
the atopile hierarchy — only after step 2. Subdivides the one loop that is
still monolithic (`METHODOLOGY.md` §3.4)."* Never started before this plan.

## Goal Capsule

- **Objective:** Design a partition of the router's ~110–149-net SAT model
  into per-block sub-models along the atopile module-instance hierarchy,
  estimate the resulting model-size reduction arithmetically against the
  measured monolithic model, and prototype the partitioner far enough to
  emit a real block assignment for the production netlist — without
  implementing the full routing integration (that is future work, scoped
  as units U1–U6 below).
- **Product authority:** temper-placer / router_v6 maintainers.
- **Open blockers / provenance gaps, stated up front:**
  1. **`docs/evidence/2026-08-07-pruned-encoding-measurement.md`, cited in
     this plan's originating task brief, does not exist in this worktree**
     (checked after merging `worktree-agent-af448502d9c6417ca`, the stated
     base). The brief's figures (22,493,900 primary variables, 204,490
     skeleton edges × 110 nets, `MemoryError` at 5.43 GB, 0% geographic-
     pruning reduction, 120.9 mm median pin span on a 279 mm diagonal) are
     used throughout this plan as given, because they are what the task
     asked this work to be measured against, but they are **not
     independently re-derived here** and could not be cross-checked
     against their source doc. Related, findable evidence
     (`docs/evidence/2026-08-07-router-oom-diagnosis.md`,
     `docs/evidence/2026-07-27-stage3-model-and-rewrite.md`) instead
     records a **42M-variable / 78M-clause CNF built from ~20,734
     capacity constraints × 96 nets (~2M primary variables)** — a
     different measurement, an order of magnitude smaller on edges, and
     from a different pipeline stage (post-Sinz-encoding CNF size, not
     pre-encoding primary-variable count). The two do not obviously
     reconcile from the docs available in this worktree. This is flagged,
     not resolved, here.
  2. **This board's real committed net count does not match the brief's
     110.** Reading `pcb/temper.kicad_pcb`'s own net table (162 total
     nets) through the router's actual classification code
     (`net_classification.py` / `_net_policy.should_route`, reimplemented
     standalone in `tools/block_partition.py` because this shell's Python
     is 3.9 and the package requires ≥3.11) gives **149 router-eligible
     signal nets** (power/ground/HV nets are zone-poured, not SAT-routed,
     and are excluded). A second, independent count derived straight from
     `elec/src/main.ato` + `elec/src/modules.ato` (§2 below) gives **148**
     — the two agree to within 1, which is strong cross-validation of the
     *method*, but neither is 110. The likely explanation is additional
     filtering in the real `ConstraintModel` builder (e.g. dropping
     single-pad/no-connect nets — a footprint-level pass found 35 of 127
     candidate nets touch only one component) that this plan did not
     re-implement. **This plan reports both the task's cited 110-net
     monolith figure and this plan's own ~148-net figure, and does the
     arithmetic against both**, rather than silently picking one.
  3. **`elec/exports/temper.design-input.v1.json`** (the one hierarchy-
     preserving atopile export this repo ships) is a **3-component,
     2-net placeholder fixture** in this worktree, not the production
     board's export — unusable for this task.

---

## 1. What survives from the atopile hierarchy into the netlist, exactly

`docs/STRATEGY.md` states "Atopile's semantic hierarchy is flattened to
strings." That is true, but not uniformly, and the *particular* way it is
lost turns out to matter for block decomposition.

**Refdes carry zero hierarchy.** `pcb/temper.kicad_pcb`'s component
references are flat (`C1`, `R23`, `U16`, ...) — no instance path anywhere
in the refdes itself. 169 components on the board, all flat.

**Net names carry hierarchy — but only for ONE endpoint, and only when
nothing renamed them.** Every net not given an explicit
`.override_net_name(...)` in `elec/src/main.ato` is auto-named by atopile
after the dotted instance path of (apparently) the first electrically
attached pin: `hb.gate_hs.driver-p1`, `safety.ovp.comp-inp`,
`rtd_pan.rail_monitor-outa`, `discharge.k_dis1-coil1`, `tank.c_tank1-p2`.
124 of the 149 router-eligible nets on the committed board carry a
recognizable instance prefix this way. This is real, useful, recoverable
information — but it is **not sufficient on its own** to reconstruct which
blocks a net touches:

- **It reports at most one endpoint.** `main.ato:806`, `tank.out ~
  ct_sense.primary_in`, is a genuine two-block wire (tank ↔ ct_sense), but
  its auto-generated name is just `tank-out` — the `ct_sense` side is
  invisible in the netlist's own strings. Any purely name-based block
  assignment silently **undercounts cross-block connectivity**. This
  plan's partitioner (§4) does not use net names for this reason — it
  reads the atopile source's connection graph directly.
- **The hierarchy is lost exactly on the nets that matter most for a
  boundary contract.** `docs/NET_NAME_MAPPING.md` documents ~20
  `.override_net_name()` calls, and inspecting them shows they are
  disproportionately the cross-module and shared-rail signals: `PWM_HS`,
  `PWM_LS`, `SW_NODE`, `SHUTDOWN`, `I_SENSE`, `V_BUS_SENSE`, `WDT_KICK`,
  `WDT_RESET_N`, `RELAY_CTRL`, `ZCD_ISO`, `RTD_SCK`/`SDI`/`SDO`/`CS_N`/
  `DRDY`, `RTD_HW_FAULT`, `OVP_VREF_2V5`, `DISCHARGE_CTRL`, plus the
  global rails (`+15V`, `+170V_BUS`, `+3V3`, `DC_BUS_RTN`, `PWR_RTN`,
  `GND`). This is the opposite of a coincidence: names get overridden
  *because* they are important enough to want a stable, readable
  cross-module name — which is exactly when the hierarchy string is
  thrown away.

**A different, coarser hierarchy survives exactly, but doesn't match.**
KiCad's hierarchical schematic sheets (`pcb/half_bridge.kicad_sch`,
`power_management.kicad_sch`, `safety_interlock.kicad_sch`,
`power_input.kicad_sch`, `sensing.kicad_sch`, `mcu.kicad_sch`) each hold
their own components' `(property "Reference" ...)` blocks — so refdes →
sheet is 100% recoverable, with zero ambiguity, straight from those six
files. But this is a **6-sheet, hand-drawn editorial grouping**, not the
atopile module-instance boundary this task and `METHODOLOGY.md` §3.4
name: `Half_Bridge` sheet contains both `hb` and `tank`'s components
(confirmed: `c_tank1`–`c_tank3` are declared inside `HalfBridge`'s
`ResonantTank` sibling relationship at the schematic-authoring level, and
physically live on the `Half_Bridge` sheet); `Power_Input` sheet holds
`discharge`'s relays alongside `power_in`'s; `Sensing` holds both
`rtd_pan` and (likely) `ct_sense`. A 7th sheet file exists
(`pcb/user_interface.kicad_sch`, with real LED/switch components) but is
**not instantiated** by the root `temper.kicad_sch` — an orphaned,
unbuilt sheet, incidental but worth flagging since it means "count the
`.kicad_sch` files" overstates the real sheet hierarchy by one.

**Bottom line, stated as the task asked:** the atopile module-instance
hierarchy is not preserved as structured metadata anywhere downstream of
compilation. It is partially, asymmetrically recoverable from net-name
string prefixes (biased toward *under*-reporting cross-block edges), and
a *different*, exactly-recoverable hierarchy exists one level coarser
(KiCad sheets) but doesn't align with the module boundaries this task
needs. The only reliable reconstruction is to go back to
`elec/src/main.ato` + `elec/src/modules.ato` and rebuild the connectivity
graph from source — never from the compiled netlist or PCB alone. That is
what `tools/block_partition.py` does (§4).

---

## 2. Block definition

**Blocks = the 11 top-level module instances declared in `module Top:`**
(`elec/src/main.ato:539-569`):

```
power_in   = new PowerInput      discharge  = new BusDischarge
power_mgmt = new PowerManagement aux_supply = new AuxSupply
hb         = new HalfBridge      tank       = new ResonantTank
ct_sense   = new CurrentSensing  rtd_pan    = new RTDSensing
safety     = new SafetyInterlock mcu        = new MCU
thermal    = new ThermalSystem
```

This is a superset of `METHODOLOGY.md` §3.4's illustrative list (`hb.*`,
`tank.*`, `safety.*`, `discharge.*`, `power_in.*`, `thermal.*`,
`rtd_pan.*`) — that list omits `power_mgmt`, `aux_supply`, `ct_sense`, and
`mcu`, which are equally real, equally top-level instances at the same
hierarchy depth and are included here for completeness.

A block **owns** its top-level module type plus every module type
transitively instantiated inside it (e.g. `hb` owns `HalfBridge` and,
because `HalfBridge` instantiates them, `GateDriveHS`, `GateDriveLS`, and
`PowerLoop`; `safety` owns `SafetyInterlock` and its seven nested
comparator/logic types: `OCPComparator`, `OVPComparator`,
`ThermalComparator`, `CoilThermalComparator`, `SecondaryOCPComparator`,
`Watchdog`, `LogicUVLOComparator`). Since `elec/src/modules.ato` defines
each class in isolation with no cross-type identifier reachable from
another type's body, any `~` connection lexically inside an owned type's
body is, by construction, entirely internal to that block — it cannot
reach another block's text.

## 3. Boundary contract

**24 point-to-point boundary nets** — each connecting exactly two
blocks — are the actual SAT-routed cross-block signals (measured by
`tools/block_partition.py`, reading `main.ato`'s `~` statements as a
union-find over dotted paths, listed in full by the tool's default
output):

| Pair | Nets |
|---|---|
| hb ↔ mcu | `PWM_HS`, `PWM_LS` |
| hb ↔ tank | `SW_NODE` (excluded from the SAT model — see below) |
| ct_sense ↔ tank | `tank.out`/`ct_sense.primary_in` |
| ct_sense ↔ mcu | `I_SENSE` (ADC line) |
| ct_sense ↔ safety | `I_SENSE` (comparator input) |
| mcu ↔ rtd_pan | `RTD_CS_N`, `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `RTD_DRDY` (5) |
| rtd_pan ↔ safety | `RTD_HW_FAULT`, `OVP_VREF_2V5` |
| mcu ↔ safety | `V_BUS_SENSE`, `WDT_KICK`, `WDT_RESET_N`, `NTC` sense, `FAULT`, `RESET_N`, `RUNAWAY_CUT` (7) |
| hb ↔ safety | `SHUTDOWN` |
| mcu ↔ power_in | `RELAY_CTRL`, `ZCD_ISO` |
| discharge ↔ mcu | `DISCHARGE_CTRL` |

Each of these is a two-pin net at the model level (one terminal per
side). **The contract at each boundary net is: a fixed connection point
(pad or a reserved via stub) at the block seam, with layer assignment
decided before either side's local model is built**, so a block's local
`ModelBuilder` can treat the far side as a terminal with a known
location/layer rather than needing the other block's internal geometry.
This mirrors how the *existing* per-net channel-variable encoding already
treats any net's pin list — no new variable kind is needed, only a
narrower `nets` argument per block plus one pinned terminal for each
boundary net's far side.

**6 shared-rail groups** (`gnd`, the `+170V_BUS`/`hv_plus` group, the
`dc_bus_minus` group, the `+15V` group, the `+3V3` group, and the
doubler-midpoint/`power_return` group) touch between 4 and 10 of the 11
blocks each. These are **not SAT-routed today at all** —
`net_classification.py`'s `is_power_net`/`is_ground_net`/`is_hv_net` and
`_net_policy.should_route` already exclude them from the per-net channel
model; they are handled by zone pours. Block decomposition changes
nothing about their handling.

### Non-decomposable constraints — explicit list

1. **Creepage / HV-SELV separation** (`creepage_check.py`). This check is
   pairwise over *every* HV-net segment against *every* LV-net segment on
   the whole board's routed copper, after routing. It cannot be evaluated
   per block: a block's own routing can be creepage-clean in isolation
   and still violate creepage once an adjacent block's copper is added
   nearby, because the check depends on the physical distance between two
   blocks' geometry, not on either block's internal structure. **This
   must be re-run globally after every block is frozen**, not once at the
   partition boundary — see §5. Reassuringly, the block boundary mostly
   *tracks* the existing HV/SELV domain split already documented in
   `docs/hardware/SELV_ISOLATION_REDESIGN.md` (`power_in`, `discharge`,
   `hb`, `tank` are HV/mains-referenced; `safety`, `mcu`, `rtd_pan`,
   `power_mgmt`, `aux_supply`, `thermal` are SELV) — the handful of nets
   that legitimately cross that domain (`I_SENSE` via an isolated CT,
   `V_BUS_SENSE` via an isolated divider, `ZCD_ISO` via an optocoupler,
   `OVP_VREF_2V5` via a reference) are exactly a subset of the 24
   point-to-point boundary nets above, so the isolation-crossing points
   needing the most creepage scrutiny are already named and small in
   number.
2. **Shared layer / via / copper-plane budget.** Layer capacity and the
   global via count are board-wide resources, not partitionable per
   block without an explicit reservation scheme this plan does not
   design (out of scope; flagged as future work in U2/U4 below).
3. **Zone pours** for the 6 shared-rail groups are computed once, globally,
   over the whole board's obstacle map — a zone is a single connected
   copper fill wherever its net's pads are, and by construction those
   pads span most of the 11 blocks (measured: 4–10 blocks per rail
   group). This is unaffected by block decomposition either way, since
   it's already outside the SAT model.

---

## 4. The prototype and its measured output

`tools/block_partition.py` reads `elec/src/main.ato` and
`elec/src/modules.ato` only (no PCB or netlist parsing) and:

1. Splits `modules.ato` into per-type bodies by its 22 top-level `module
   <Name>:` headers.
2. Builds the "Type instantiates Type2" graph from `<name> = new <Type2>`
   lines, and computes each of the 11 blocks' owned-type closure.
3. Union-finds every `~` connection line inside a block's owned bodies —
   each resulting group is one net, entirely internal to that block by
   construction.
4. Separately union-finds `Top`'s own `~` lines (main.ato) and classifies
   each resulting group by which blocks' identifiers appear in it.
5. Filters "rail-like" internal groups (any member ending `.gnd`/`.vcc`/
   `.vdd`, or matching `gnd_ref`/`power_return`) — these are local
   references to a block's power interface that Top later ties to a
   global rail, so they are not real SAT-routable signal nets even
   though they show up as a 2-member internal union-find group. This
   heuristic is calibrated against the real board: filtering it in
   brings the atopile-derived total from 177 to **148**, against the
   PCB's own **149** router-eligible signal net count — agreement within
   1 net.

**Measured per-block net counts** (`python3 tools/block_partition.py`):

| Block | Internal (routable) | + boundary nets touching it | Total (own+boundary) |
|---|---:|---:|---:|
| safety | 33 | 11 | **44** |
| mcu | 26 | 18 | **44** |
| rtd_pan | 24 | 7 | 31 |
| hb | 20 | 4 | 24 |
| power_in | 16 | 2 | 18 |
| discharge | 14 | 1 | 15 |
| ct_sense | 5 | 3 | 8 |
| power_mgmt | 6 | 0 | 6 |
| tank | 3 | 2 | 5 |
| thermal | 1 | 0 | 1 |
| aux_supply | 0 | 0 | 0 |

`safety` and `mcu` tie as the largest blocks (`safety` has the most
internal nets — 7 nested comparator/logic sub-modules; `mcu` has fewer
internal nets but the most boundary fan-out, being the natural
communication hub).

**Measured cut size:** 24 point-to-point boundary nets out of 148+24=172
atopile-derived signal-level nets — a **14% cut fraction**, concentrated
almost entirely on `mcu` and `safety` (18 and 11 of the 24 boundary nets
respectively touch one of these two). This is not a dense, unpartitionable
graph — most blocks (`tank`, `thermal`, `power_mgmt`, `aux_supply`,
`ct_sense`, `discharge`, `power_in`) have 0–3 boundary nets each — but it
is also not clean: `mcu` and `safety` are structurally hubs (`mcu` is
directly wired to 7 of the other 10 blocks; `safety` to 4), so any
ordering strategy has to treat them specially (§6).

`tools/block_edge_estimate.py` extends this with a geometric check against
the *real, committed* board (`pcb/temper.kicad_pcb`, read-only — this plan
does not modify it): it classifies each of the board's 169 components into
a block (via net-name prefix matching plus a hand-built crosswalk for the
~18 override-named boundary nets, both derived from `block_partition.py`'s
own output — not invented separately — plus adjacency propagation through
low-fanout nets for the remainder), then measures each block's component
bounding-box area as a fraction of the board.

**Result: this board's physical placement does not cluster by atopile
module.** Even components that are *unambiguously* internal to one block
by direct net-name match are scattered across nearly the entire board —
e.g. `power_in`'s own rectifier diode (168, 93), relay (95, 221),
NTC (40, 210), and top-rail resistor (155, 21) span almost the full
152×234 mm outline. Measured bounding-box area fractions: 8 of the 11
blocks with resolvable geometry cover ≥84% of the board's area; only
`thermal` (2 components) shows a small footprint, and that is more likely
an artifact of having too few resolved components than genuine
clustering. **This is the same root cause already found for geographic
pruning** (`docs/evidence/2026-08-07-pruned-encoding-measurement.md`,
per the task brief: 0% reduction, median pin span 120.9 mm on a 279 mm
diagonal) — this board's component placement doesn't cluster along
*either* axis a size-reduction lever wants to exploit (pin locality, or
schematic-module locality). That is a real, connected finding across both
investigations, not a coincidence of measurement.

---

## 5. Arithmetic estimate

Both figures are reported because of the reconciliation gap in the Open
Blockers section above.

### Against the task brief's cited monolith (204,490 edges × 110 nets = 22,493,900 vars)

Because block bounding boxes cover most of the board (§4), the honest,
measured assumption is that a block's *local* channel-skeleton edge count
does **not** shrink proportionally to its net count — it needs
(approximately) the full board's 204,490 edges regardless of which block
is being routed, because the block's own components are not confined to
a sub-region. Variables scale as `edges × nets_in_block`, so with edges
held at the whole-board figure:

```
largest block (own nets only):      204,490 × 33 = 6,748,170 vars  (30.0% of the monolith)
largest block (own + boundary nets): 204,490 × 44 = 8,997,560 vars  (40.0% of the monolith)
```

Per §3.3's dominance point in the task brief — an uneven partition is
dominated by its largest block, not the average — **the relevant number
is the 30–40% figure for `safety`/`mcu`, not the ~148/11 ≈ 13-net
per-block average**, which would understate the real ceiling by roughly
2.5×.

### Against this plan's own measured 148-net figure

```
monolith (204,490 × 148) = 30,264,520 vars
largest block (own+boundary, 44 nets) = 8,997,560 vars (29.7% of THIS monolith)
```

The percentage is essentially unchanged (~30–40%) whichever monolith
baseline is used, because the ratio is dominated by `44 / N_total`,
which sits in the same range (44/110 = 40%, 44/148 = 30%) under both
counts. This is reassuring: the headline conclusion is not sensitive to
which of the two unreconciled net-count baselines is correct.

### What this reduction is worth against the OOM

The task brief states the current monolithic model `MemoryError`s at
5.43 GB *before reaching the CNF encoder* — i.e. the Python
`ConstraintModel` construction itself, at the primary-variable stage, not
the post-Sinz-encoding CNF. Scaling that figure by the same 30–40%
fraction gives an estimated **1.6–2.2 GB** for the largest single block's
local model — comfortably under any plausible per-process ceiling
(8 GB / 16 GB), and a real, credible fix for the specific failure mode
named in the brief, even without any placement change.

### Why this is smaller than geographic pruning's claimed 10–40×

Geographic pruning (the parallel, independently-scoped effort — see
`docs/evidence/2026-08-07-pruning-u1u2-implementation.md` and
`docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md`) shrinks
the **nets-per-constraint** dimension *per edge* (from 96 nets down to a
small constant per capacity constraint), which multiplies through every
one of the ~20,000+ constraints. Block decomposition here only shrinks
the **nets-per-model** dimension globally (from 110–148 down to ≤44 for
the largest block) while the **edges-per-model** dimension stays at the
whole board's size, because this board's placement doesn't cluster by
block. The two levers are compatible, not competing — pruning operates
*within* whatever net set a block's local model already has, so applying
both should be closer to multiplicative than either alone. That
composition is not measured here; it is named as follow-up work (U4
below).

---

## 6. Ordering: iterative with targeted rip-up, not pure sequential

`METHODOLOGY.md` §3.4: *"Route a block, verify it, freeze it, route the
next."* That is the right frame, but the measured boundary graph (§4) is
not a DAG a simple topological order can exploit cleanly — `mcu` connects
directly to 7 of the other 10 blocks and `safety` to 4, so no ordering
avoids having at least one hub block wire up against several
already-frozen (or several still-unrouted) neighbors.

**Recommendation:**

1. **Order low-fan-out blocks first.** `thermal` (0 boundary nets),
   `power_mgmt` (0), `aux_supply` (0), `tank` (2), `ct_sense` (3),
   `power_in` (2), `discharge` (1) — these can route and freeze with
   almost no interaction, shrinking the remaining problem fast and cheap.
2. **Route hub blocks (`mcu`, `safety`) last**, once every other block's
   half of each boundary net already has a fixed stub location and layer
   from step 1. This minimizes the search space the hub's local model has
   to consider for its own 18/11 boundary terminals — the far ends are
   already pinned, not free variables.
3. **A pure sequential "freeze and never revisit" policy is not safe on
   this board**, because §4 established blocks are not spatially
   separated — a block routed early can plausibly place a boundary
   terminal in a location that becomes congested or creepage-violating
   once its neighbor is later routed nearby. **Recommend iterative
   ordering with targeted rip-up**: route once in the low-fan-out-first
   order; if a later block's attempt to route a boundary net fails, or
   the post-freeze global creepage/clearance check (item 1, §3) flags a
   violation against an already-frozen block, roll back *only* the
   copper immediately adjacent to that one boundary net (not the whole
   frozen block) and re-route with an adjusted stub constraint, bounded
   to a small retry budget. This is standard negotiated-congestion
   rip-up-and-reroute practice (PathFinder-style), scoped down to the 24
   boundary nets specifically — the 148 internal nets never need this
   treatment, since they can't touch another block by construction.
4. **Global checks are re-run after every freeze, not deferred to the
   end.** Creepage/clearance is O(all copper) per run regardless of
   decomposition — `METHODOLOGY.md` §3.2's loop-quality table already
   rates checks like this at "ms" scale, cheap relative to the SAT solve
   itself, so paying for it 11 times (once per block freeze) instead of
   once is affordable and catches an inter-block violation at the block
   that caused it rather than at the very end.

---

## 7. `METHODOLOGY.md` §3.4 compliance

Quoted directly, and checked against this plan's decisions:

> "Routing is the hardest loop to subdivide — it is a global optimization
> and nets interact through congestion. The decomposition is already
> present in the atopile semantic hierarchy... Route a block, verify it,
> freeze it, route the next. Blocks that share no nets interact only at
> boundaries, and boundaries take contracts... Per §3.3, this lands
> *after* seam assertions exist, not before."

- Blocks are the atopile hierarchy (§2), extended to all 11 real
  instances rather than the doc's illustrative 7.
- "Blocks that share no nets interact only at boundaries" is now
  measured, not assumed: 7 of 11 block pairs sharing a boundary net
  form a genuinely sparse graph (0–3 boundary nets each); the two hub
  blocks (`mcu`, `safety`) are the exception and are handled explicitly
  (§6).
- Boundaries "take contracts" — §3 gives the explicit contract (fixed
  terminal + layer, decided before either side's local model builds).
- Ordering (§6) directly answers "route a block, verify it, freeze it,
  route the next," refined to "iterative with targeted rip-up" because
  pure sequential freezing is not safe given the measured lack of
  spatial clustering.
- The build-order prerequisite ("only after step 2") is satisfied: step
  2 ("Seam contracts + footprints-inside-outline precondition") is
  recorded as landed in `docs/STRATEGY.md`'s build order and commit
  history predating this task.

---

## 8. Feasibility verdict

**Workable, with an honestly modest and clearly-bounded benefit — proceed,
but do not oversell it.**

- The **net-count reduction is real and substantial for the model's
  dominant scaling term**: the largest block's SAT model drops to
  ~30–40% of the monolith's variable count, using only source-derived
  partitioning — no placement change, no PCB modification (none was made;
  `pcb/temper.kicad_pcb` was read-only throughout this task). That is
  enough to plausibly clear the specific 5.43 GB `MemoryError` named in
  the brief (estimated 1.6–2.2 GB for the largest block).
- **The edge-count dimension does not shrink under this decomposition
  today**, because this board's physical placement is not clustered by
  atopile module (measured directly against the committed board, §4) —
  the same root obstacle that already zeroed out geographic pruning's
  benefit. This is the honest ceiling on this lever as currently
  scoped: it is a nets-per-model win, not an edges-per-model win, unless
  a future re-placement pass deliberately clusters each block's
  components into its own sub-region (a placement change well beyond
  this task's scope and explicitly forbidden from touching
  `pcb/temper.kicad_pcb`).
- **Decomposition is not free**: 24 new boundary-net seams each need an
  explicit contract, plus global creepage/clearance re-verification after
  every block freeze, plus a real (not pure-sequential) ordering/rip-up
  strategy. Per `METHODOLOGY.md` §3.3, "subdivision has a cost" — this
  plan's 24-seam, iterative-rip-up design is the honest price of the
  30–40% reduction, not a free lunch.
- **It composes with, rather than competes with, the parallel geographic
  pruning effort** — different axes of the same `vars ≈ edges × nets`
  product — and combining both is named as explicit follow-up work (U4),
  not measured here.
- **Two reconciliation gaps remain open** (§ Open Blockers): the missing
  cited evidence doc, and the ~110-vs-~148 net-count discrepancy. Neither
  changes the qualitative verdict (the percentage reduction is stable
  across both candidate baselines), but both should be resolved before
  this plan's units are executed against a specific numeric target.

---

## 9. Unit breakdown for the routing integration (not built here)

This plan is the design + prototype (§1–8, `tools/block_partition.py`,
`tools/block_edge_estimate.py`). The units below are the follow-on
implementation work, explicitly out of this task's scope ("do not
implement the full routing integration").

### U1. Wire block-scoped `ModelBuilder` invocation

**Goal.** `ConstraintGenerationStage` accepts a `nets: set[str] | None`
filter (default `None` = today's monolithic behavior) so a caller can
build a `ConstraintModel` restricted to one block's own nets plus its
boundary nets' terminals.

**Evidence that closes U1.** A block-scoped `route_pcb()` call on the
production board produces a CNF whose primary-variable count matches
this plan's per-block arithmetic (§5) to within the same tolerance
`docs/evidence/2026-08-07-router-oom-diagnosis.md` already accepts for
solver-version variance (~5–10%).

**Blocked by:** reconciling the 110-vs-148 net count gap (§ Open
Blockers item 2) — the target to validate U1 against needs to be a single
number, not two.

### U2. Boundary-net terminal contract + shared-resource reservation

**Goal.** Implement the fixed terminal (pad/via + layer) mechanism named
in §3 for the 24 point-to-point boundary nets, plus a simple layer/via
budget reservation so blocks routed later don't starve.

**Evidence that closes U2.** All 24 boundary nets route successfully
across two arbitrarily-chosen adjacent blocks in isolation, with the far
side represented only by its fixed terminal (no access to the other
block's internal geometry).

**Blocked by:** U1.

### U3. Ordering controller with targeted rip-up

**Goal.** Implement the low-fan-out-first, hub-last ordering (§6) with
the bounded rip-up-and-reroute fallback for boundary-net failures.

**Evidence that closes U3.** A full production-board route via the block
sequence completes without ever needing a full-board re-solve; the
rip-up retry count is bounded and logged per boundary net.

**Blocked by:** U2.

### U4. Global creepage/clearance re-verification hook + pruning composition

**Goal.** Re-run `verify_creepage`/clearance after every block freeze
(§6 item 4), fail-closed on the same anti-vacuous-truth basis as
`docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md`. Also
measure whether composing block decomposition with the parallel
geographic-pruning flag (`enable_geographic_pruning`) is multiplicative,
as §5 predicts but does not verify.

**Evidence that closes U4.** A deliberately-mis-ordered corpus board (one
block's stub placed to violate creepage against a not-yet-frozen
neighbor) is caught by the per-freeze check — the anti-vacuous-truth
demonstration this repo requires (`METHODOLOGY.md` §5). Separately, a
before/after CNF-size measurement with both levers enabled together.

**Blocked by:** U3.

### U5. Corpus regression + determinism gate

**Goal.** Behavioral A/B (block-decomposed vs monolithic route) on the
board corpus, matching the determinism protocol
(`docs/evidence/2026-07-27-router-determinism.md`) and the margins
already used for the geographic-pruning gate (R6/R7 in
`docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md`).

**Evidence that closes U5.** Bit-identical route output on every corpus
board where both paths complete; documented, attributed divergence
(never silent) on any board where they don't.

**Blocked by:** U4.

### U6. Verdict document

**Goal.** Record measured production-board memory/time with the full
integration, superseding this plan's arithmetic estimate with real
numbers.

**Blocked by:** U1, U3, U4, U5.

---

## Sources

- `docs/STRATEGY.md` — build order step 8; "Atopile's semantic hierarchy
  is flattened to strings."
- `docs/METHODOLOGY.md` §3.2–3.4 — loop-quality framing, subdivision
  cost, the block-decomposition design this plan implements.
- `elec/src/main.ato`, `elec/src/modules.ato` — the source of truth for
  the block/boundary graph (§1, §2, §4).
- `pcb/temper.kicad_pcb`, `pcb/*.kicad_sch` — read-only, for the
  hierarchy-survival analysis (§1) and the geometric clustering
  measurement (§4). Not modified.
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py`,
  `_net_policy.py` — the router's actual signal/power/ground/HV net
  classification, reimplemented standalone in `tools/block_partition.py`
  and `tools/block_edge_estimate.py` due to this shell's Python 3.9
  (package requires ≥3.11).
- `packages/temper-placer/src/temper_placer/router_v6/creepage_check.py` —
  the pairwise, whole-board HV/LV creepage check cited as non-decomposable
  in §3.
- `docs/evidence/2026-08-07-router-oom-diagnosis.md`,
  `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — the 42M/78M
  CNF measurement used in the Open Blockers reconciliation note.
- `docs/evidence/2026-08-07-pruning-u1u2-implementation.md`,
  `docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md` — the
  parallel geographic-pruning effort this plan composes with (§5, U4).
- `docs/NET_NAME_MAPPING.md` — the ~20 `.override_net_name()` cross-walk
  used in §1 and §4.
- `tools/block_partition.py`, `tools/block_edge_estimate.py` — this
  plan's prototype; both run against the current worktree state.
