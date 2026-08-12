---
title: Routing-Corridor Reservation in the CP Placement Model — Plan
type: feat
date: 2026-08-12
topic: placement-corridor-reservation
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Routing-Corridor Reservation in the CP Placement Model — Plan

## Goal Capsule

**Objective:** Teach the CP placement model to *reserve routing resource* —
board-spanning channels of clear copper wide enough for a real trace of a
named net class — by encoding corridors as first-class pseudo-components, and
wire those corridors through to the router and the pour so the reservation is
honoured rather than merely declared.

**Headline finding, stated first because it changes what success means.**
The mechanism is understood and the placement-side prototype already works at
real scale, but **the honest expectation is that this alone does not take
`clearance` 499 → under 386**, and the plan is written so that a partial
result is still a landed, measurable improvement rather than a failure.
Three measured facts drive that:

1. **The regression is 100% routed copper.** Pad↔pad `clearance` violations
   went **38 → 0** on the candidate board; 95.2% of the 505 involve at least
   one track, and 98.6% fire against the *loosest* rule in the file (RULE 10
   `"Default routing"`, 0.2mm)
   (`docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md` §4,
   §5). Placement's own contribution went **down**. No placement-side
   constraint can bound a routed-copper violation count; it can only create
   room (Key Decision D1).
2. **The count is startlingly insensitive to construction.** Three
   independent regenerations of the documented recipe produced **4,228 /
   3,319 / 3,017** segments — a 29% spread in routed copper — and measured
   `clearance` **499 / 504-505 / 499-503**. A board with 29% less copper to
   collide produced *the same number*. A single lever that opens ~5% of board
   area is unlikely to move a number that ignored a 29% swing in the input.
3. **Normalised, the candidate is already better than the baseline it is
   being held against.** 386 violations over 2,290 committed segments =
   **0.169 per segment**; 499 over 4,228 = **0.118 per segment**. The
   candidate routes 85% more copper and violates 30% *less often per
   segment*. The absolute ratchet compares two boards with materially
   different routing completion. This does not excuse 499 — the ratchet is
   absolute and `AGENTS.md`'s contract is explicit that ceilings only
   decrease — but it does mean "get under 386" and "make the board better"
   are not the same objective, and this plan reports both (Requirement R14).

**What the plan does deliver, provably.** SAT of the corridor encoding
implies a geometric fact about the placement alone, auditable from
coordinates: *a connected, board-spanning region of clear width ≥ W, free of
all component copper, exists.* That is a conservative **lower bound on
routing resource**. It is **not** a bound on violation count and cannot be
made one — the router may decline to use the corridor, which is exactly why
U5/U6 (router and pour consumption) are load-bearing units of this plan and
not follow-ups.

**Product authority:**
`packages/temper-placer/src/temper_placer/placer/cp_sat/**` maintainers, with
`router_v6/**` maintainers as joint owners of U5/U6.

**Open blockers:** none for the design. Two real dependencies are named, not
assumed: the `.kicad_pro` vs `design_rules.py` `HighVoltage` clearance
disagreement (2.0mm vs 6.0mm), under investigation by a separate agent
(Dependencies); and the production-backend tractability question — the
prototype's feasibility result is a **Pumpkin** result, and production is
**OR-Tools**, which already returns `unknown` at 26s on the *uncorridored*
model (D6, U3).

---

## Product Contract

### Summary

The CP placement model's only clearance notion is a scalar
`courtyard_clearance_mm` τ applied pairwise
(`_encoder_core.py::_generate_courtyard_separated_constraints`). τ is
dimensioned to stop solder-mask bridging between adjacent footprints and does
that job correctly. It was never dimensioned to let a *trace pass between* two
components, and it does not. This plan adds the missing notion — reserved
channel — using primitives that already exist and are already proven, and
then makes the reservation real downstream.

Nothing here invents a constraint type. A corridor is an ordinary
non-rotatable pseudo-component; `separated(corridor, component, 0.0)` is the
existing, already-audited `SEPARATED` encoding; optional targeting uses the
existing, live-but-unused `ANCHORED` region primitive. The engine changes
required are **zero** for Pumpkin and **one registration-order change** for
OR-Tools (D5).

### Problem Frame

#### §0. The mechanism, in one paragraph, derived from the SSOT

`courtyard_clearance_mm` = `default_clearance_mm + 2 × MASK_EXPANSION_MM` =
`0.2 + 2 × 0.1` = **0.40mm** (`_encoder_solve.py:684-701`,
`MASK_EXPANSION_MM = 0.1` at line 32). The width a single trace of class *c*
needs to pass through a gap is `trace_width(c) + 2 × clearance(c)`, both read
from `packages/temper-placer/configs/netclass_rules.yaml`:

| class | `trace_width` | `clearance` | single-trace channel | τ = 0.40mm suffices? |
|---|---:|---:|---:|:--|
| FinePitch | 0.127 | 0.10 | **0.327** | yes — the only class that fits |
| Signal | 0.20 | 0.15 | **0.50** | no |
| HighSpeed | 0.15 | 0.20 | **0.55** | no |
| GateDriveHV / GateDriveSELV | 0.40 | 0.25 | **0.90** | no |
| Power / HighCurrent | 0.50 | 0.25 | **1.00** | no |
| GND | 1.00 | 0.30 | **1.60** | no |
| HighVoltageIsolated | 2.00 | 6.00 | **14.00** | no |
| HighVoltage / ACMains | 3.00 | 6.00 | **15.00** | no |

These figures are **derived**, not transcribed: R1 requires the generator to
compute them from `load_netclass_rules()` at run time, with no channel-width
float literal anywhere in the module, so a change to the YAML moves the
corridors.

Against this, **12,301 of 14,028 component pairs (87.7%) are governed by the
flat 0.40mm backfill** and only 1,727 (12.3%) carry a constraint ≥ τ (the
6.0mm HV rows). HPWL then drives every unopposed pair to exactly the floor,
so the router inherits a board whose inter-component gaps are, by
construction, too narrow for any class except FinePitch. Downstream, #1052
measured the same fact as F.Cu free space fragmenting into **~94 disconnected
regions** (`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`).

**Board utilization is 43.66%** (15,529.5mm² of component boxes on a
152 × 234mm = 35,568mm² board). The board is not globally area-starved.
Congestion is local — 42% of failing nets centroid into the MID-MID cell,
11.1% of board area (`docs/evidence/2026-08-08-placement-remediation-analysis.md`),
and the top 15 net pairs carry **311 of 505 (61.6%)** of the violations,
concentrated on `U27`/mcu, `U26`/safety.latch, `U22`, `U21`, `U24` and the
`rtd_pan` analog front end.

#### §1. What already exists, verified in code this session

- **Ten constraint types are implemented in the Pumpkin engine**
  (`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:219-542`); the OR-Tools
  handler registry covers the full PCL 8 (`handlers/__init__.py:24-31`).
  `keepout`, `enclosing` and `anchored` are live, tested and **unused by the
  real-board model** — this plan uses `anchored` (R6).
- **`comp.bounds` ⊇ all pad copper, in the placement frame, by construction**
  (`_parse_modules.py::_calculate_footprint_bounds`; P8/P9/P10 in
  `test_geometry_constraints_pbt.py`). This is what upgrades a box-level
  corridor guarantee to a copper-level one for free (§2's Lemma 1).
- **The `SEPARATED` encoding already carries a soundness proof and a
  post-solve audit** (`handlers/separated.py` docstring;
  `audit.py::PlacementAuditor._check_separated`), and is already inventoried in
  `power_pcb_dataset/physics_soundness_register.yaml` — the register that
  `scripts/physics_soundness_register_gate.py` enforces in
  `.github/workflows/python-tests.yml`. Corridors extend an inventoried
  surface rather than opening an uninventoried one.
- **The prototype ran, at real scale, against the committed 169-component
  board with the unmodified Pumpkin binary**
  (`docs/brainstorms/2026-08-12-copper-clearance-in-placement-options.md`,
  Option 1; generator preserved at the session scratchpad's `corridor_spec.py`):

  | config | components | constraints | status | objective |
  |---|---:|---:|:--|---:|
  | baseline | 169 | 14,196 | feasible | 2,005,980 |
  | 3V+3H @ 1.6mm | 175 | 15,216 (+7.2%) | **feasible** | 2,040,217 |
  | 4V+4H @ 1.6mm | 177 | 15,560 (+9.6%) | **feasible** | 2,190,938 |
  | 3V+3H @ 0.6mm | 175 | 15,216 | **feasible** | 1,658,634 |

  Post-solve audit on the 3V+3H @ 1.6mm solution: **0 component-into-corridor
  intrusions, 0 same-orientation corridor overlaps, 9 of 9 V–H crossings**,
  and 4 of 14,196 τ pairs short by ≤ 0.0052mm — all four explained by the
  `to_units` quantization defect (§4), not by the corridor mechanism. Area
  cost ≈ 1,820mm² = **5.1%** of the board; utilization 43.7% → 48.8%.
  **Every run hit its 30s budget and returned `feasible`, not `optimal`** —
  the objective column is anytime noise (note the 0.6mm run scoring *better*
  than baseline) and is not evidence of anything. Feasibility and the audit
  are the load-bearing results.

#### §2. The two lemmas the guarantee rests on

Both are stated here because R9's audit is written to falsify exactly these,
and R10's register entry links to them.

**Lemma 1 (clear width).** Let corridor *C* be a registered pseudo-component
with encoded box *B_C* and let component *A* have encoded box *B_A*. A
`SEPARATED` constraint at margin 0 between them is SAT only via one of the
four half-plane literals (`handlers/separated.py`), e.g.
`A.x_end + 0 ≤ C.x_start`. By the same argument `domain_clearance.py`'s
revised proof gives, every point of *B_A* is then ≥ 0 from every point of
*B_C* on that axis — i.e. their interiors are disjoint. Since `comp.bounds` ⊇
*A*'s pad copper in the placed frame, **the interior of *B_C* contains no
component copper**. With `width(B_C) = W`, a trace of the class *W* was sized
for can be laid on *C*'s centreline with full class clearance to component
copper on both sides. *Conservative, with one classified error term: the
`to_units` even-parity rounding (§4), bounded at ≤ 0.0206mm total and
neutralised by R2's inflation.*

**Lemma 2 (connectivity).** Every corridor is **full-span**: a vertical
corridor is `W × (board_h − 2m)`, a horizontal one `(board_w − 2m) × W`, and
`set_bounds` confines every registered component — corridors included — to
`[m, board_w − m] × [m, board_h − m]` (`model.py:488-507`). Therefore
`V_i = [x_i, x_i+W] × [m, board_h−m]` and
`H_j = [m, board_w−m] × [y_j, y_j+W]` and their intersection
`[x_i, x_i+W] × [y_j, y_j+W]` is **non-empty for every (i, j)**, because
board bounds already force `x_i ≥ m`, `x_i+W ≤ board_w−m` and likewise in y.
V–H pairs therefore cross *unconditionally* — provided no constraint forbids
it, which is why R4 deliberately posts **no** V–H constraint. With K ≥ 1 and
M ≥ 1 the union of all corridors is a connected set. **The 9-of-9 crossings
the prototype audit observed were not luck; they are forced.** This is the
property whose absence killed #1052 (~94 disconnected regions), and it is the
single strongest reason to prefer this option over pairwise-gap widening.

**What neither lemma gives.** Neither says the router will *use* the
corridor, that the corridor passes anywhere useful, or anything at all about
`clearance` counts. D1 and R14 hold that line.

#### §3. Corridor count, width and placement strategy

**Widths (R1).** Uniform 1.6mm was a feasibility probe, not a
recommendation. The generator emits a *width multiset* per axis, each entry
`W(c, n) = n × trace_width(c) + (n+1) × clearance(c)` for a class *c* and a
lane count *n* — the `n=1` column of §0's table generalised. Rationale for
the `(n+1)` term: a corridor carrying *n* side-by-side traces needs clearance
on both outer edges *and* between adjacent lanes; `n=1` collapses to
`trace_width + 2 × clearance`, matching §0.

**Default recommended configuration** (a starting point to be moved by U3's
measurement, not a fixed answer): per axis, one GND-class corridor
(W = 1.60), one Power-class corridor (W = 1.00), and two Signal-class
corridors (W = 0.50) — 4V + 4H. Reserved area, computed:
`3.60 × 233 + 3.60 × 151 − 3.60²` = 838.8 + 543.6 − 13.0 ≈ **1,369mm² ≈
3.85%** of the board (utilization 43.7% → 47.5%) — *less* than the
prototype's uniform 3×3 @ 1.6mm (1,820mm², 5.1%) while carrying a strictly
more useful width spectrum and one more channel per axis. HV classes (14–15mm channels) are **explicitly
not** corridored: at 15mm a single corridor is 10% of the board width, and
the HV↔LV separation job is already done by `domain_clearance.py` and the
isolation barrier, whose own PD2 corridor at `y ∈ [113.0, 121.0]` is
literally the same idea already in production.

**Uniform or targeted? Both, and targeting does not cost the connectivity
proof (R6).** Full-span corridors placed freely by the solver are the
default. Targeting the measured hot cluster is achieved *without* localising
corridors — which would break Lemma 2 — by adding an `ANCHORED` **region**
constraint that pins a corridor's *cross-axis* coordinate into a window while
leaving its span axis full board
(`handlers/anchored.py`: region ⇒ `x_start ≥ rx_min`, `x_end ≤ rx_max`, and
likewise in y; set the span axis to the full board so it is vacuous there).
So "route a 1.6mm channel through the `safety.*`/`mcu.mcu`/`rtd_pan.*`
cluster" is expressible as one anchored corridor, and Lemma 2 is untouched.
The hot-cluster windows are **data, not code**: a YAML list of
`(sheetpath_prefix, axis)` entries resolved against `Component.sheetpath`
(a real field, `core/netlist.py:100`) into a bounding window at generation
time. Default: targeting **off**, so U3's A/B measures uniform-vs-targeted
rather than assuming.

**Why not more corridors.** Corridors partition the board, so HPWL pays
whenever a net's members land on opposite sides, and — this is the risk worth
naming — HPWL under a partition will pack each cell *tighter*, which is the
opposite of what the hot cluster needs. K and M are the knob; U3 measures the
HPWL and per-cell-density cost, and R14's paired A/B is what decides.

#### §4. Both backends, explicitly

Production is **OR-Tools** (`cli/__init__.py:447-449` prints "CP-SAT placer
selected (default)"; there is no Pumpkin option). Pumpkin exists only under
`docs/evidence/2026-08-*-pumpkin-*` as spike/equivalence-harness code. Every
prototype number in §1 is a *Pumpkin* number. That asymmetry drives three
statements this plan must make plainly.

**(a) The fail-open / fail-closed divergence does not fire — by design, and
this plan proves it rather than assuming it.** On an unregistered constraint
type OR-Tools logs a warning, adds to `UNSUPPORTED_TYPES` and **continues
with the constraint silently dropped** (`_encoder_core.py:326-334`); Pumpkin
prints `unsupported constraint type … aborting` and **exits 2**
(`main.rs:535-541`). Corridors introduce **no new constraint type** — only
`separated` and (for targeting) `anchored`, both registered in both engines —
so neither branch is reachable. R8 makes that a test rather than a claim: a
corridor solve must leave `UNSUPPORTED_TYPES` empty on the OR-Tools path, and
the Pumpkin path must exit 0 with status in {optimal, feasible}. This closes,
for this feature, the gap the expressiveness audit flagged as "would confirm
this cheaply — I did not do this".

**(b) There is a real backend divergence, and it is the global
`NoOverlap2D`.** `_encoder_solve.py:290` calls
`model_wrapper.add_no_overlap_2d(comp_refs)` over every real component.
Pumpkin has **no `AddNoOverlap2D` analogue** (verified against
`pumpkin-constraints-0.5.0`: no `diffn`, no 2-D packing constraint), which is
why its no-overlap job is done entirely by the all-pairs τ backfill. If
corridor refs are appended to `comp_refs`, OR-Tools will forbid **V–H
overlap**, destroying Lemma 2 and very likely rendering the model UNSAT.
**R7 is therefore a hard, backend-specific requirement**: corridors are
registered via `add_component` + `add_rotation(is_polarized=True)` *before*
`set_bounds` (so they inherit board bounds, `model.py:501` iterates all
registered components) and are **excluded** from the `add_no_overlap_2d` ref
list. Pumpkin needs no equivalent change; its ModelSpec takes corridors as
`{"w0_mm": …, "h0_mm": …, "rotatable": false}` entries and nothing else.

**(c) Tractability on the production backend is the largest open risk.**
OR-Tools returns `unknown` at ~26s on the *uncorridored* 14,196-constraint
real-board model; Pumpkin proves the same model optimal in 0.9–2.0s
(`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md` §4.2). Corridors add
+7.2%. The real production budget is 180,000ms/round × up to 4 rounds
(`docs/evidence/2026-08-07-cpsat-objective-frequency.md` §2), not 30s, so
"unknown at 26s" is not the last word — but it has never been measured at the
real budget *with* corridors. U3 measures it. If OR-Tools cannot decide the
corridor model inside one round's budget, the feature ships **Pumpkin-path
only** behind its flag until a solver seam exists, and this plan says so
rather than quietly shipping a placer that times out (D6).

#### §5. The three defects the brainstorm surfaced — triaged

- **`to_units` optimism (`main.rs:69-74`, and its SSOT twin
  `temper-constraints::encoder.rs::mm_to_units`) — BLOCKS the soundness
  claim, does NOT block this plan, because R2 neutralises it locally.**
  `round_ties_even` then force-even-by-decrement encodes a dimension up to
  **0.010282mm small** (`30.130282 → 3013.0282 → 3013 → 3012 → 30.12`),
  affecting 6 of 338 dimensions (C2–C5, K1, PS1). It is optimistic — the
  wrong direction — and it is the *measured* explanation for the prototype
  audit's four ≤0.0052mm shortfalls. The brainstorm calls the fix "one line";
  it is not: `mm_to_units` lives in the `temper-constraints` Rust crate, is
  mirrored bit-exactly in `main.rs`, and is **pinned by
  `tests/placer/cp_sat/test_encoder_rust_differential.py`**, so the real fix
  is direction-aware (sizes and margins round *up* to even; positions and
  board extents round *down*) across three files plus the differential's
  expectations. That is a correct, separate, scoped piece of work. **This
  plan does not depend on it**: R2 inflates the encoded corridor width by a
  derived margin so the corridor guarantee is conservative whether or not
  `to_units` is fixed.

  > **Moving under this plan's feet, recorded rather than assumed.** As of
  > this document's writing, an uncommitted working-tree change by a
  > concurrent agent rewrites `main.rs::to_units` to round **up** to even and
  > adds unit tests asserting `to_units(30.130282) == 3014` — an explicit,
  > documented divergence from `CpSatModel.mm_to_units` /
  > `temper-constraints::encoder.rs`, which are unchanged. If that lands, the
  > **Pumpkin arm's** dimension shrink is gone and the **OR-Tools arm's** is
  > not, and the two backends no longer quantize identically. That makes R2's
  > inflation *more* necessary, not less, because production is the
  > un-fixed arm; and it makes "which backend was this measured on" a
  > question every U3 number must answer explicitly. Verify the state of
  > both `to_units` implementations before trusting any measurement taken
  > across this boundary.

  Error budget, derived: a component's encoded box is
  centred by the midpoint identity, so nominal copper overhangs each side by
  ≤ (w_nom − w_enc)/2 ≤ 0.00515mm; two flanking components contribute
  ≤ 0.0103mm and the corridor's own width shrinks ≤ 0.0103mm, total
  ≤ **0.0206mm** ⇒ 4 units (0.04mm) of inflation is strictly conservative and
  preserves even parity.
- **`netclass_constraints.py:90` `hasattr(c,"a") and hasattr(c,"b")` also
  matches `AdjacentConstraint` — SEPARATE, not a prerequisite, but fix it in
  this plan's U1 anyway because it is three lines and sits in the file U1
  already opens.** Any pair carrying an `adjacent` constraint silently loses
  its netclass clearance and falls back to flat τ. Today that is masked
  because τ ≥ most netclass values, but it would silently drop a 6.0mm HV
  separation. It does not interact with corridors (corridors carry no
  `adjacent` constraints), so it is a bundled fix, not a dependency. Fix:
  test `isinstance(c, SeparatedConstraint)`, matching what
  `_generate_courtyard_separated_constraints` already does correctly
  (`_encoder_core.py`). **Already implemented in an uncommitted working-tree
  change by a concurrent agent**, with a regression test in
  `tests/pcl/test_netclass_constraints.py`. R17 is therefore
  "verify, and no-op if already landed" — check before implementing, and if
  it landed elsewhere, mark R17 satisfied by that commit rather than
  re-doing it.
- **`.kicad_pro` `HighVoltage` 2.0mm vs `design_rules.py` 6.0mm — a
  dependency to note, not to resolve.** A separate agent is investigating.
  It is conservative in the placer's direction (the placer solves against the
  stricter figure the DRC does not enforce), so it cannot make this plan
  unsafe; it can make it *infeasible* — U6's joint isolator infeasibility is
  driven partly by a number the fab rules do not require. **This plan takes
  no position and hardcodes neither value**; R1 reads whatever
  `netclass_rules.yaml` says. Recorded in Dependencies so that if the
  investigation lands on 2.0mm, U3's feasibility measurements are re-run
  rather than inherited.

#### §6. How a corridor reaches the router and the pour — the seams, measured

This section exists because it is the step most likely to be silently
skipped, and because the repository already contains one worked example of
skipping it (D8).

**What the placer hands the router today.** A positional dict and nothing
else. `PlaceRouteLoop._route_placement` (`_loop_routing.py:110-174`) builds
`{ref: (x, y)}` from `placement.to_placements_dict()`, origin-shifts it,
constructs a `ParsedPCB` **stub carrying only a source path** (`:149`), and
calls `route_pcb(...)`. `scripts/route_board.py::route_once` (`:150-205`)
passes an *empty* placements dict and reads positions off the board. **There
is no `placement_report.json`** — a repo-wide grep returns zero hits in any
`.py`/`.json`/`.yaml`/`.rs`. So U4 is genuinely new surface, not a field to
add to an existing artifact.

**Seam A — the cost field (chosen, D9).** `CostFieldInput`
(`fields/interface.py:26-40`) is a per-cell `float32` array already threaded
from `route_pcb(thermal_flat=, thermal_weight=)` (`_adapter_convert.py:183-184`)
into the A* inner loop as an additive term (`astar_core.py:351-353`). It is
the only end-to-end-plumbed per-cell influence on routing cost. There is **no
bonus/attract mechanism anywhere in `router_v6`** — a grep for
`bonus|attract|preferred_region|cost_bonus|reward` returns nothing — so
"prefer the corridor" must be expressed as "penalise everything else",
which is also the only form that keeps A* admissible.

**Seam B — the hard `corridor_mask` (rejected, D9).** `astar_core.py:331`
reads a plain boolean array and neither knows nor cares how it was built, so
seeding it from placement rectangles instead of eroded copper is
semantically trivial. It is nonetheless the wrong seam twice over: it is
**unreachable from production** (threaded through `_astar_route` but not
`_astar_route_multilayer` `:368` or `_astar_route_with_ripup` `:607`, and
production enters at the latter, `_astar_reconstruct.py:281`), and hard
gating is the shape of #1052's measured failure. Recorded so the next reader
does not rediscover it as an opportunity.

**Note on vocabulary.** `router_v6` already uses "corridor" for two unrelated
things: `corridor_erosion.corridor_mask_for_net` (a configuration-space
erosion of free space by a trace's own footprint — *derived* from copper, the
#1052 object) and `corridor.extract_corridor_mask` (a dilated coarse-A*-path
region). Neither is a reservation. U4's artifact must not reuse the bare word
without qualification.

**The pour, and why a rule area is not enough on its own.** Three verified
obstacles, all named in R13: `strip_existing_copper` on the way in
(`route_board.py:182`), `strip_existing_zones` on the way out
(`_adapter_convert.py:679`), and a pour path that subtracts only the board
outline (`zone_emission.py::compute_zones_for_net`). The
`difference()`-then-emit-rule-area pattern that works
(`_ground_plane.py:720-721`, `:501-536`) lives on a standalone script path,
not on `route_pcb`. Separately, the production Rust parser cannot even
represent keepout settings — `parse_engine.rs::parse_zone` (`:1001-1053`) has
no `keepout` arm and `RawZone` (`:581-586`) has no field to carry one — which
is why `check_isolation_keepout.py` reads the board with kiutils instead.
A netless zone polygon *does* become an unconditional router obstacle today
(`obstacle_map.py:171-199`, and its docstring says so deliberately), which is
a useful accident but not a reservation mechanism.

**Routing determinism, and a concrete lead on the 4,228 / 3,319 / 3,017
spread.** The historically proven nondeterminism source (`uuid.uuid4()` for
`tstamp`) was fixed and verified (`docs/evidence/2026-07-27-router-determinism.md`:
5 post-fix runs byte-identical; `PYTHONHASHSEED` measured *not* to be the
mechanism). There is **no seed anywhere on the routing path** — `route_pcb`
has no seed parameter and `_loop_routing.py:115` accepts `_seed` and
documents that it ignores it. Two live risks remain, and one of them is
directly implicated by the documented recipe:
`net_batching.py:191`'s `DEFAULT_SUBPROCESS_TIMEOUT_S = 900.0` with
`status="crashed"` fallback (`:101-122`, `:428`) is a genuine
wall-clock → outcome coupling — a batch that times out is retried per-net
instead of solved as a batch, on a machine-speed-dependent boundary — and
**`--net-batching` is exactly the flag the reproduction recipe specifies**.
The other is un-audited Rust `HashMap` iteration order in
`temper-rust-router-core`, flagged UNVERIFIED in the determinism evidence and
the stated reason `route_board.py --runs` uses fresh subprocesses. R14's
protocol is built around both.

### Key Decisions

- **D1. The constraint is a lower bound on routing *resource*, never on
  violation *count*, and the module docstring says so in those words.** The
  DRC `clearance` count is a property of the routed board; the router is not
  in the model. Anyone wanting the AGENTS.md physics discipline's item 1
  satisfied *against `clearance` itself* will not get it from any
  placement-side option, this one included. `domain_clearance.py` already
  states its own limits this way ("What this proof does NOT cover"); the
  corridor module copies that discipline.
- **D2. Corridors are pseudo-components, not a new constraint type.** Chosen
  over a `channel`/`diffn`-style primitive because (i) Pumpkin has no 2-D
  packing constraint to build one on, (ii) it inherits `SEPARATED`'s existing
  proof, audit and register entry, and (iii) it needs no engine change, which
  the prototype verified by running the *unmodified* binary.
- **D3. Every corridor is full-span on one axis.** This is what makes
  connectivity a theorem (Lemma 2) rather than an observation. Local /
  partial-span corridors were considered and rejected: two partial corridors
  need not intersect, so connectivity would become a solver-dependent
  accident requiring a much larger encoding (pairwise crossing disjunctions)
  to restore.
- **D4. Targeting is `ANCHORED` regions on full-span corridors, not localised
  corridors.** Preserves D3/Lemma 2, reuses a live-but-unused primitive, and
  keeps the hot-cluster definition in data.
- **D5. OR-Tools registers corridors outside the global `NoOverlap2D`;
  Pumpkin needs no change.** Forced by §4(b). This is the only backend-
  specific line of code in the feature.
- **D6. Ship behind an opt-in flag, default off, and be willing to ship
  Pumpkin-path-only.** Matching plan `2026-08-11-002`'s D6 reasoning: the
  always-on Phase-1 feasibility path's speed is what keeps CI and
  `PlaceRouteLoop` predictable, and §4(c) means the production backend may
  not decide the corridor model at all. A flag makes "measured, not adopted"
  a real state.
- **D7. Success is a paired A/B against router nondeterminism, not a single
  absolute number.** Three regenerations of the same recipe spread 4,228 /
  3,319 / 3,017 segments. Any single before/after comparison is inside that
  noise. R14 specifies the protocol.
- **D8. The corridor must be honoured by the router *and* the pour, or the
  feature is not done.** The precedent is exact and unflattering:
  `IsolationBarrierReport` (`isolation_barrier.py:506-520`) already carries a
  fully-specified corridor rectangle — `orientation`, `corridor_width_mm`,
  `corridor_position_mm` — is attached to the solve result at
  `_encoder_solve.py:668`, and **`isolation_barrier_report` has five
  references in the entire repository, all inside `_encoder_solve.py`
  itself**. Nothing downstream reads it. `scripts/check_isolation_keepout.py`
  is correspondingly **red today (exit 3, check `"missing"`)** because
  `pcb/temper.kicad_pcb` contains zero keepout geometry. A second reserved
  corridor that nothing consumes would be the same defect twice. U5 and U6
  are units of this plan, and R14's verdict is not claimable without them.
- **D9. The router bias is a soft cost, not a hard mask.** Two seams exist
  (§6). `corridor_mask` (`astar_core.py:331`) is a hard boolean gate and is
  **not reachable from production** — it is threaded through `_astar_route`
  but not through `_astar_route_multilayer` or `_astar_route_with_ripup`
  (`_astar_search.py:368`, `:607`), and production Stage 4 enters at the
  latter (`_astar_reconstruct.py:281`). `CostFieldInput.cost_flat`
  (`fields/interface.py:26-40`) is a per-cell `float32` additive penalty that
  **is** plumbed end to end, `route_pcb(thermal_flat=, thermal_weight=)` →
  `astar_core.py:351-353`. Chosen: the cost field, with the penalty applied
  **outside** corridors rather than a bonus inside, because A*'s admissibility
  check (`astar_monitor.validate_cost_lower_bound`) assumes non-negative edge
  costs and a negative cell would break it. Hard-gating was also the shape of
  #1052's failure and is not to be repeated.

### Requirements

Each requirement is individually checkable; the check is named in the same
bullet. Requirement IDs are stable and become `@req(2026-08-12-001, Rn)`
annotations when this plan flips to `status: active` and is registered in
`docs/traceability-registry.yaml`.

- **R1.** Corridor widths are computed from
  `configs/netclass_rules.yaml` via `io/netclass_loader.load_netclass_rules`
  as `W(c, n) = n × trace_width(c) + (n+1) × clearance(c)`. **Check:** a unit
  test recomputes every emitted width from a parsed copy of the YAML and
  asserts equality; a second test mutates a class's `trace_width` in a
  temp-copy of the YAML and asserts the emitted width moves. No numeric
  channel-width literal appears in the corridor module (grep-asserted).
- **R2.** The encoded corridor width is `W + CORRIDOR_QUANTIZATION_MARGIN_MM`
  where that constant is `0.04` (4 model units), carrying the §5 derivation
  in its docstring. **Check:** a test asserting the constant ≥ the derived
  0.0206mm bound, and the R9 audit's pass criterion being nominal `W` (not
  the inflated value), so the inflation can only ever be surplus.
- **R3.** Every corridor is non-rotatable and full-span: vertical corridors
  are `W × (board_h − 2m)`, horizontal are `(board_w − 2m) × W`, with `m` the
  same `COPPER_EDGE_CLEARANCE_MM` the encoder already uses. At least one
  corridor of each orientation is emitted whenever corridors are enabled.
  **Check:** generator unit test on emitted geometry; a test asserting the
  generator raises when asked for `K = 0` or `M = 0` (the configuration that
  would silently void Lemma 2).
- **R4.** The generator emits `separated(corridor, component, 0.0)` for every
  real component, `separated` at `CORRIDOR_MIN_SPACING_MM` between
  same-orientation corridor pairs, and **no constraint at all** between a
  vertical and a horizontal corridor. **Check:** a test enumerating the
  emitted constraint set for a small synthetic board and asserting exactly
  these three families, including the *absence* of any V–H pair.
- **R5.** Lemma 1 and Lemma 2 are written into the corridor module's
  docstring in the style of `domain_clearance.py`, including the explicit
  statement that the guarantee is a lower bound on routing resource and not a
  bound on violation count. **Check:** the soundness-register gate resolves
  `proof_location.symbol` inside that docstring (R10), and a docstring test
  asserts the "not a bound on violation count" sentence is present — a
  deliberately blunt check, because that sentence is the one most likely to be
  dropped in a later edit.
- **R6.** Targeted corridors are expressible as `AnchoredConstraint` region
  windows on full-span corridors, with the window list loaded from data keyed
  on `Component.sheetpath` prefixes; targeting defaults to **off**.
  **Check:** a test that an anchored corridor still spans the full board on
  its span axis, and that with targeting off the emitted constraint set
  contains zero `anchored` entries.
- **R7.** On the OR-Tools backend, corridors are registered before
  `set_bounds` and are excluded from the ref list passed to
  `add_no_overlap_2d`. **Check:** a test that solves a small OR-Tools model
  with 1V+1H corridors and asserts the returned coordinates have the two
  corridors overlapping (i.e. crossing) — this test **fails** if a future
  edit adds corridors to the global no-overlap, which is exactly the
  regression worth catching.
- **R8.** Neither backend hits its unknown-constraint-type path. **Check:**
  after an OR-Tools corridor solve, `UNSUPPORTED_TYPES` is empty (asserted,
  not logged); the Pumpkin corridor run exits 0 with status in
  `{optimal, feasible}` (asserted on the subprocess return code, so an
  `exit 2` is a test failure rather than a skipped run).
- **R9.** A post-solve corridor audit recomputes, in mm, from the solver's
  returned coordinates and each component's **nominal** `comp.bounds` (never
  the quantized encoded sizes): (a) zero component-box-into-corridor
  intrusions, (b) realised corridor width ≥ nominal `W`, (c) zero
  same-orientation corridor overlaps, (d) all `K × M` V–H crossings present.
  It lives in `placer/cp_sat/audit.py` as a `PlacementAuditor` check
  alongside `_check_separated`, is invoked from `solve_placement` on the same
  footing as `audit_fixed_copper`, and **raises** on (a)/(b)/(c) — a
  violation means the encoding did not deliver what it claimed.
  **Check:** the audit's own unit tests include a hand-built *failing*
  placement for each of (a)–(d), asserting each is detected (an audit never
  observed to fail is not an audit); plus `test_audit_pbt.py`-style property
  coverage.
- **R10.** `power_pcb_dataset/physics_soundness_register.yaml` gains an entry
  for the corridor generator with `proof_type: conservative-bound`, a
  `proof_location` resolving into R5's docstring, `coverage_scope` naming the
  resource-not-count limitation, `exemptions` naming the `to_units`
  classified error and R2's neutralisation, and `audit` pointing at R9's
  symbol. **Check:** `scripts/physics_soundness_register_gate.py` exits 0
  (it is already wired in `.github/workflows/python-tests.yml`); the gate
  independently verifies the encoder symbol resolves to real code and the
  proof location substring exists.
- **R11.** BMC-exhaustive validation on small N: the corridor-vs-component
  predicate *is* `encode_separated`, so the existing
  `TestChebyshevSoundnessBMC` sweep covers it — extended with a
  corridor-shaped case set (extreme aspect ratios, margin exactly 0,
  degenerate zero-size boxes) — plus a **new** exhaustive sweep over small
  `(K, M, W, board)` on an integer grid asserting Lemma 2's crossing claim on
  every enumerated solution. **Check:** both sweeps are tests; the new sweep
  is falsifiable by construction (it must fail if the generator ever emits a
  non-full-span corridor).
- **R12.** The router consumes corridors, through the **already-plumbed cost
  field**. The placer emits the corridor rectangles as a machine-readable
  artifact (U4); the router rasterises them into a `CostFieldInput`-shaped
  `(H*W,) float32` array whose value is `0.0` inside a corridor and a
  configured positive penalty outside it, and passes it through the existing
  `route_pcb(thermal_flat=…, thermal_weight=…)` parameter into
  `astar_core.py:351-353`. **No new router plumbing is required, and no
  negative cost is ever written** (A*'s `validate_cost_lower_bound`
  admissibility check assumes non-negative edge costs). The corridor is never
  a hard mask. **Check (behavioural, not structural):** an integration test
  routing the same board twice, corridors on and off, asserting the fraction
  of routed segment length falling inside corridor rectangles is materially
  higher with corridors on; plus an artifact round-trip test. *"The router
  reads the file" is not the property that matters and is not what this
  requirement checks.*
- **R13.** The pour does not backfill the reservation, and the reservation
  survives the write path. Three concrete obstacles, all verified:
  (a) `route_board.py:182` calls `strip_existing_copper()`, which strips
  every `(zone …)` block including rule areas
  (`temper-io-types/src/strip_copper.rs:97-99`); (b) `_adapter_convert.py:679`
  calls `strip_existing_zones()` immediately before emitting pours, so a rule
  area present on the input board never reaches the output; (c) the
  `route_pcb` pour path (`zone_emission.py::compute_zones_for_net`) subtracts
  only the board outline — it has **no keepout subtraction at all**.
  The requirement is therefore: corridor rectangles are subtracted from each
  pour region *before* emission and are re-emitted as a KiCad rule area,
  reusing the pattern already proven in `_ground_plane.py`
  (`plane_region.difference(keepout)` at `:720-721`;
  `_emit_keepout_zone_s_expr` at `:501-536`, `(copperpour not_allowed)`,
  `(priority 1000)`) — which today runs only on the standalone
  `scripts/generate_ground_plane.py` path, not on `route_pcb`. **Check:** a
  gate script in the shape of `scripts/check_isolation_keepout.py` (which
  reads the board via kiutils precisely because the production Rust parser
  discards keepout settings — `parse_engine.rs:1001-1053` has no `keepout`
  arm) asserting on a regenerated candidate board that (i) a corridor rule
  area exists per emitted corridor, (ii) no zone polygon intersects a
  corridor rectangle, (iii) the corridor's full nominal width survives; wired
  into the same CI job as the existing keepout gate.
- **R14.** Success is measured by a **paired** A/B against a *stabilised*
  recipe, not by an absolute delta. Four parts, each separately checkable:
  **(a) Stabilise the recipe first.** Re-run the regeneration with
  `--net-batching` **off**, and separately with it on while logging every
  batch that hits `DEFAULT_SUBPROCESS_TIMEOUT_S` and falls back to per-net
  (`net_batching.py:191`, `:101-122`). If the segment-count spread collapses
  with batching off, the 4,228 / 3,319 / 3,017 mystery is solved and the
  no-batching recipe becomes the measurement recipe. If it does not, the
  residual is attributed (Rust `HashMap` order is the named suspect) and
  carried as a measured noise band rather than ignored.
  **(b) Freeze the absolute baseline.** The corridors-off board from the
  first stabilised run is committed as a fixture under `power_pcb_dataset/`
  with its sha256 recorded, so the baseline stops being re-derived on every
  investigation.
  **(c) Pair the comparison.** From one reconciled netlist and one fixed
  placement, generate n ≥ 5 (corridors-off, corridors-on) pairs through an
  identical routing invocation, measuring each with
  `temper_placer.validation._drc_api.run_drc` — the single-thread
  `KICAD_CONFIG_HOME` pin under which the committed board reproduced
  386/386/386; bare `kicad-cli` is what produced the 499–505 scatter.
  **(d) Report three numbers, not one:** mean `clearance` delta with its
  per-pair spread, `clearance` per routed segment, and routing completion.
  **Check:** the evidence document carries all four parts; a claimed
  improvement smaller than the measured spread is reported as "not
  distinguishable from routing nondeterminism", not as a win.
- **R15.** Rollback is one flag. Corridors are reachable only through an
  explicit opt-in on `solve_placement` and its CLI surface, default off; with
  the flag off, the emitted constraint set, the solve time and the resulting
  placement are **byte-identical** to today's. **Check:** a test asserting
  constraint-set equality between flag-off and a pre-change baseline on the
  golden corpus; CI's existing placement regression tests are not
  re-baselined by this plan.
- **R16.** Corridors do not break the isolation barrier. The corridor model
  is solved jointly with all 8 isolator straddles at the PD2/8.0mm bar before
  any adoption decision. **Check:** the joint solve returns
  feasible/optimal, or the plan records the measured infeasibility and the
  corridor configuration is reduced until it does — 7-of-8 is already the
  measured ceiling (`U6` alone relaxed), so this is a live risk, not a
  formality.
- **R17.** `netclass_constraints.py`'s `hasattr(c,"a") and hasattr(c,"b")`
  skip test is replaced with an `isinstance(c, SeparatedConstraint)` test.
  **Check:** a regression test asserting a pair carrying an
  `AdjacentConstraint` still receives its netclass `SEPARATED` constraint —
  a test that fails on today's code.

### Deferred

- **R18** (deferred). Per-pair channel-demand `min_distance` replacing the
  flat τ on the measured hot-cluster axis only (the brainstorm's Option 3,
  narrow variant). Genuinely promising and complementary, but it tightens
  pairs rather than reserving space and has no conservative-bound story of
  its own; sequence it after R14 has a measurement to attribute against.
- **R19** (deferred). Margin-aware soft objective (hinge penalty on proximity
  to the τ floor, the brainstorm's Option 4). Highest ceiling of any option
  and cannot cause UNSAT, but needs a `main.rs`/`model.py` engine change and
  real weight tuning against HPWL — a different plan.
- **R20** (deferred). Direction-aware `mm_to_units` rounding across
  `temper-constraints::encoder.rs`, `CpSatModel.mm_to_units` and the
  bit-exact differential (§5). Correct and worth doing; R2 removes this
  plan's dependence on it. Note the Pumpkin half may already have moved
  independently (§5's inset), which would leave the two backends quantizing
  differently — a state worth closing, and a reason this stays on the list
  rather than being dropped.

---

## Units

Dependency order. U1–U3 are the placement side and can land alone behind the
flag; U5–U6 are where the value is realised and are the units most likely to
be skipped, which is why they are numbered as work rather than as follow-ups.

### U1 — Corridor generator and its proof

**Deliverable.** A new
`packages/temper-placer/src/temper_placer/placer/cp_sat/corridors.py`:
width derivation from the netclass SSOT (R1, R2), the corridor pseudo-component
spec, the three constraint families (R4), optional `ANCHORED` targeting from
data (R6), and the Lemma 1 / Lemma 2 docstring (R5) written in
`domain_clearance.py`'s style — including the "not a bound on violation count"
sentence. Bundled: R17's three-line `isinstance` fix in
`netclass_constraints.py`.

**Evidence of closure.** R1/R2/R3/R4/R5/R6/R17's named checks pass. No solve
runs in this unit; it is pure generation and is unit-testable without a
solver.

**Blocked by:** nothing. **Blocks:** U2, U3.

### U2 — Audit, register entry, BMC (the AGENTS.md discipline, all three items)

**Deliverable.** R9's `PlacementAuditor` corridor check with its
deliberately-failing fixtures; R10's register entry; R11's BMC extensions.
Wired so that `solve_placement` raises on a corridor audit failure, on the
same footing as `audit_fixed_copper`, and so
`scripts/physics_soundness_register_gate.py` — already PR-blocking via
`.github/workflows/python-tests.yml` — covers the new surface.

**Why this is a unit and not a step inside U1.** The discipline's three items
are the ship gate; making them a separately-closable unit is what stops them
becoming "we'll add the audit later". The prototype already implemented and
ran a ~20-line version of R9's audit, so the risk here is low and the reason
to separate it is process, not difficulty.

**Evidence of closure.** R9, R10, R11 pass; the physics-soundness gate exits
0; each of the four audit conditions has a fixture that provokes it.

**Blocked by:** U1. **Blocks:** U3.

### U3 — Backend measurement: does the production solver decide this model?

**Deliverable.** A measurement, not a decision: solve the real 169-component
board with the recommended 4V+4H mixed-width configuration on **both**
backends at the **real** budget (180,000ms, not 30s), with and without
targeting, and with the full 8-isolator barrier (R16). Report status, wall
time, HPWL, constraint count, and the R9 audit's four conditions. R7 and R8's
tests land here because they are backend-specific.

**The question this unit exists to answer.** OR-Tools returns `unknown` at
26s on the *uncorridored* model. If it also returns `unknown` at 180s with
corridors, the feature is Pumpkin-path-only until a solver seam exists, and
that is a legitimate outcome to record (D6) — not a reason to quietly widen
the timeout. If R16's joint isolator solve is infeasible, reduce the corridor
configuration (fewer corridors, then narrower) until it is, and report the
configuration that survived rather than the one that was hoped for.

**Evidence of closure.** An evidence document with the two-backend table and
the R16 verdict.

**Blocked by:** U1, U2. **Blocks:** U4.

### U4 — Corridor artifact: the placer→router contract that does not exist yet

**Deliverable.** A `ReservedCorridors` artifact — per corridor: rectangle in
absolute board mm, orientation, the net class it was sized for, nominal `W` —
produced by a corridor-enabled solve and serialised alongside the placement.
There is **no `placement_report.json` today** (§6): the handoff is a
`{ref: (x, y)}` dict plus a path-only `ParsedPCB` stub
(`_loop_routing.py:135-156`), so this is new surface and both call paths
(`PlaceRouteLoop` and `scripts/route_board.py`) must carry it.

**Bundled, because it is the same defect and costs nothing extra:** route the
existing `IsolationBarrierReport`'s corridor (`isolation_barrier.py:506-520`,
stored at `_encoder_solve.py:668`, read by nobody) through the same artifact.
The isolation barrier is a reserved corridor by any reasonable definition; it
should not have a second, private, unread representation.

**Evidence of closure.** Round-trip test (R12, first half); a test that a
corridor-enabled solve's artifact contains the isolation barrier's corridor
when the barrier is enabled.

**Blocked by:** U3. **Blocks:** U5, U6.

### U5 — Router consumption (R12) — the unit most likely to be silently skipped

**Deliverable.** Rasterise U4's rectangles into a `(H*W,) float32` cost field
— `0.0` inside corridors, a configured positive penalty outside — and pass it
through the **already-plumbed** `route_pcb(thermal_flat=…, thermal_weight=…)`
parameter (`_adapter_convert.py:183-184` → `astar_core.py:351-353`). If a
thermal field is already supplied, the two combine additively; the unit must
decide and document that composition rather than let one silently overwrite
the other.

**Why a penalty-outside rather than a bonus-inside:** `router_v6` has no
bonus mechanism at all (§6), and a negative cell would break A*'s
admissibility check (`astar_monitor.validate_cost_lower_bound`).
**Why not the hard `corridor_mask`:** unreachable from production
(`_astar_search.py:368`, `:607` do not thread it) and hard gating is the
shape of #1052's measured failure.

**Closure is R12's behavioural assertion** — routed segment length inside
corridors materially higher with corridors on — not "the router reads the
file".

**Named risk, stated as a falsifier.** #1052 proved a smarter *search* over
the same placement does not help. This unit is a search over a *different*
placement, one with reserved connected space. If the measurement shows the
router still does not use the corridors, that falsifies the whole approach,
not just this unit, and must be reported as such.

**Blocked by:** U4. Joint ownership with `router_v6/**` maintainers.

### U6 — Pour consumption (R13)

**Deliverable.** Subtract corridor rectangles from each pour region before
emission and re-emit them as KiCad rule areas, following
`_ground_plane.py`'s proven `plane_region.difference(keepout)` (`:720-721`) +
`_emit_keepout_zone_s_expr` (`:501-536`) pattern — which today runs only on
the standalone `scripts/generate_ground_plane.py` path and not on
`route_pcb`. Plus the `check_isolation_keepout.py`-shaped gate script.

**The three verified obstacles this unit must clear** (§6, R13):
`strip_existing_copper` on the way in (`route_board.py:182`),
`strip_existing_zones` on the way out (`_adapter_convert.py:679`), and a pour
path that subtracts only the board outline. A corridor that survives none of
these is worth nothing: #1052's own no-backbone control measured vias + pour
alone at +42 `clearance` against a 392 baseline, so the pour is not a
secondary consumer.

**Blocked by:** U4. Shares the pour-regeneration seam
`docs/plans/2026-08-11-002` U3 already names; coordinate rather than
duplicate.

### U7 — Measurement and verdict (R14)

**Deliverable.** The paired A/B (n ≥ 5), the frozen baseline board fixture,
the three reported numbers, and an honest verdict against the 386 target —
including the "not distinguishable from routing nondeterminism" outcome if
that is what the spread says. Supersedes every estimate in this document with
real numbers.

**Blocked by:** U5, U6.

---

## Scope Boundaries

- **No modification to `pcb/**`.** Every measurement runs against scratch
  copies and regenerated candidate boards, as the cited evidence documents
  already do.
- **Not a router rewrite.** U5 adds a cost bias driven by a new input; it
  does not re-open #1052's search-strategy question, which is a measured dead
  end for this regression and must not be re-proposed.
- **Not a global τ raise.** Raising `default_clearance_mm` tightens 87.7% of
  pairs uniformly to buy margin where there is no violation, and pushes on a
  constraint set already proven jointly infeasible at `U6`. Strictly
  dominated by corridors.
- **Not pad-level placement modelling.** Pad separation is already sound via
  `bounds ⊇ pads`, pad↔pad violations are already 0 on the candidate board,
  and the pad model is 9.8× the pair count (138,601 vs 14,196). Correct
  eventually, wrong problem today.
- **Not two-sided placement.** All 169 components are on side 0 and the model
  carries no side variable. This is plausibly the single largest lever on
  local congestion and it is a board-architecture decision with thermal,
  assembly-cost and DFM consequences — a human's call, logged in Outstanding
  Questions, deliberately not costed here.
- **Not a change to `netclass_rules.yaml`'s values**, including the
  `HighVoltage` figure under separate investigation.
- **Not a re-basing of the DRC ratchet.** Whether 499 should be accepted on a
  board that is measurably safer (safety-rule clearance 26 → 1, creepage
  −60%, pad↔pad 38 → 0) is a real question and an explicitly human one.

## Dependencies / Assumptions

- **`comp.bounds` ⊇ pad copper in the placement frame** — an invariant proven
  by construction since 2026-07-30 and property-tested (P8/P9/P10). Lemma 1's
  copper-level conclusion inherits it; if that invariant regresses, the
  corridor guarantee degrades to box-level silently. Worth an explicit
  cross-reference in the corridor docstring.
- **`SEPARATED`'s existing soundness proof and audit** are reused unmodified.
  This plan adds a caller, not a mechanism.
- **The `.kicad_pro` (2.0mm) vs `design_rules.py` (6.0mm) `HighVoltage`
  disagreement** is under separate investigation. This plan hardcodes
  neither. If it resolves to 2.0mm, U3's feasibility numbers — and possibly
  R16's verdict — must be re-measured, not inherited, because `U6`'s joint
  infeasibility may partly dissolve at the lower figure.
- **Production is OR-Tools; Pumpkin is spike code** reachable only by ad-hoc
  scripts shelling out to a compiled binary. Every prototype number in §1 is
  a Pumpkin number and is treated as an existence proof for the *encoding*,
  not as a production tractability result.
- **The real objective-bearing solve budget is 180,000ms/round, up to 4
  rounds** — U3 sizes against that, not against the 30s the prototype used or
  the 5s harness artifact.
- **There is no seed anywhere on the routing path** — `route_pcb` has no seed
  parameter and `_loop_routing.py:115` accepts `_seed` and documents that it
  ignores it. The `uuid4` tstamp nondeterminism was fixed and verified, and
  `PYTHONHASHSEED` was measured *not* to be the mechanism
  (`docs/evidence/2026-07-27-router-determinism.md`). The two residual risks
  are `--net-batching`'s 900s subprocess timeout with per-net fallback
  (`net_batching.py:191`, `:101-122` — a genuine wall-clock → outcome
  coupling, and `--net-batching` is the recipe's own flag) and un-audited
  Rust `HashMap` iteration order in `temper-rust-router-core` (flagged
  UNVERIFIED in that evidence). R14(a) tests the first directly rather than
  assuming either.
- **`_drc_api.run_drc`'s single-thread `KICAD_CONFIG_HOME` pin** removes
  DRC-side scatter (386/386/386 on the committed board) but not routing-side
  scatter; bare `kicad-cli` is what produced the 499–505 band. R14 uses the
  pinned path throughout.

## Outstanding Questions

- **O1.** Will the router actually use the corridors (R12/U5)? This is the
  question the whole plan turns on and it is genuinely open. #1052 showed a
  better search over a fragmented placement does not help; nobody has yet
  measured a search over a *deliberately unfragmented* one.
- **O2.** Does HPWL under a corridor partition make the hot cluster *worse*?
  Corridors partition the board; the objective may respond by packing each
  cell tighter, which is the opposite of what `U27`/`U26`/`rtd_pan` need. U3
  should report per-cell density, not only HPWL total.
- **O3.** Is the 4V+4H mixed-width default right? It is reasoned from the
  class table, not measured. The prototype only measured uniform 1.6mm at
  3×3 and 4×4. U3's sweep is where this gets settled.
- **O4.** Is 499 actually a blocker? 98.6% of it is a generic 0.2mm track
  rule; the candidate board is *safer* (HV↔LV clearance 12 → 0, AC mains↔LV
  5 → 0, creepage −60%) and routes 85% more copper at a 30% lower violation
  rate per segment. Re-basing the ratchet against a safer board is a
  legitimate alternative to closing the gap, and it is a human's decision.
- **O5.** Two-sided placement. Roughly halves local density, needs a side
  variable the model does not have, and sits outside a clearance fix.
  Probably the largest available lever on the actual mechanism.
- **O6.** Is `--net-batching`'s subprocess timeout the whole explanation for
  the 4,228 / 3,319 / 3,017 segment spread? It is the only wall-clock →
  outcome coupling on the default path and the recipe uses the flag, so it is
  the leading hypothesis — but the un-audited Rust `HashMap` iteration order
  is a second, independent candidate that nobody has ruled out. R14(a)
  settles it; until then the plan treats the spread as measured noise, not as
  a solved problem.
- **O7.** Should corridors be solver-placed (as here) or derived from a
  routing-demand estimate and then anchored? Solver-placed is the feature —
  the model chooses where channels go — but it means `W` must still be picked
  from a demand heuristic, which is where the guarantee is weakest and this
  plan says so.

## Sources / Research

- `docs/brainstorms/2026-08-12-copper-clearance-in-placement-options.md`
  (branch `docs/placement-model-expressiveness-gaps`, commit `fefb37674`) —
  the option ranking, the τ-vs-channel-width table, the real-board prototype
  and its audit, and the R24-posture framing this plan carries forward
  unchanged. Read in full.
- `docs/brainstorms/2026-08-12-placement-model-expressiveness-gaps.md` (same
  branch) — the encoder fail-open/fail-closed divergence (gap #5), the full
  solver-divergence inventory, and the "Pumpkin is not the production engine"
  finding behind §4 and D6.
- `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md` and
  `docs/evidence/2026-08-12-clearance-regression-independent-spike.md`
  (branch `diagnose/clearance-regression`) — two independent measurements:
  the 0-of-505 pad↔pad breakdown, the top-15-net-pairs 61.6% concentration,
  the 54.3%-gross distribution, the 98.6% RULE-10 attribution, and the
  4,228 / 3,319 / 3,017 segment spread that D7 and R14 are built around.
- `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` (#1052) — the
  failed router-side attempt: mechanism proven correct, `clearance` unmoved
  across five strategies, free space fragmenting into ~94 disconnected
  regions. The reason D3/Lemma 2 exists and the reason U5 is a cost bias
  rather than a mask.
- `AGENTS.md` "Future CP-SAT Physics Constraint Discipline (R24)" and
  `docs/physics-verification-methodology.md` — the three-item ship gate U2
  closes.
- `power_pcb_dataset/physics_soundness_register.yaml` and
  `scripts/physics_soundness_register_gate.py` — the existing, already
  PR-blocking inventory R10 extends.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`
  — the proof-writing template (revised copper-to-copper Chebyshev proof,
  and the "What this proof does NOT cover" discipline R5 copies).
- `.../cp_sat/handlers/separated.py`, `.../handlers/anchored.py`,
  `.../audit.py`, `.../model.py` (`add_component`, `add_no_overlap_2d:214`,
  `set_bounds:488`), `.../_encoder_core.py` (τ backfill; fail-open at
  326-334), `.../_encoder_solve.py` (component registration at 226-252,
  `add_no_overlap_2d` at 290, `courtyard_clearance_mm` at 684-701),
  `.../netclass_constraints.py:90` — read directly this session, not
  inherited from any summary.
- `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs` — ten constraint
  types (219-542), `to_units` (69-74), `exit(2)` on unknown type (535-541),
  HPWL objective (565-603).
- `packages/temper-placer/configs/netclass_rules.yaml` — the width/clearance
  SSOT R1 derives from.
- `packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py`
  — the existing real-board harness U3's measurement extends rather than
  reimplements.
- `power_pcb_dataset/drc_ceiling.json` — `clearance` ceiling 386, provenance
  `measured-live`, 130 samples via `_drc_api.run_drc` with the single-thread
  pin; the protocol R14 adopts and the monotone contract R14 is measured
  against.
- `router_v6/` surfaces read directly for §6/D9/R12/R13/U4–U6:
  `fields/interface.py:26-40` (`CostFieldInput`), `_adapter_convert.py:179-197`
  (`route_pcb` signature), `:679-680` (`strip_existing_zones` then pour),
  `astar_core.py:331` (`corridor_mask` gate), `:351-353` (additive cost
  field), `_astar_search.py:368`, `:607` (the two entry points that do **not**
  thread `corridor_mask`), `_astar_reconstruct.py:281` (production entry),
  `obstacle_map.py:171-199` (netless zone → unconditional obstacle),
  `zone_emission.py::compute_zones_for_net` (board-outline clip only),
  `_ground_plane.py:501-536`, `:720-721` (the working keepout pattern),
  `occupancy_grid.py:38-43` (`CellState.RESERVED`, declared with zero uses),
  `net_batching.py:191`, `:101-122` (subprocess timeout → per-net fallback),
  `_loop_routing.py:110-174` (the positional-dict handoff),
  `scripts/route_board.py:150-205`, `:182`.
- `packages/temper-design-bundle/src/parse_engine.rs:581-586`, `:1001-1053` —
  `RawZone` has no keepout field and `parse_zone` has no `keepout` arm; the
  reason `scripts/check_isolation_keepout.py` uses kiutils instead.
- `scripts/check_isolation_keepout.py` — the gate R13's check is modelled on;
  currently **red (exit 3, `"missing"`)** because the board carries zero
  keepout geometry.
- `docs/evidence/2026-07-27-router-determinism.md` — the `uuid4` tstamp fix,
  the `PYTHONHASHSEED` falsifier, and the UNVERIFIED Rust `HashMap` residual
  behind R14(a).
- `docs/plans/2026-08-11-002-feat-placer-wirelength-and-hv-separation-plan.md`
  and `docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md`
  — read in full for structure and requirement-ID convention; 002's U3
  (keepout-before-pour bridge) is the seam U6 shares, and its D6 (opt-in
  entry point) is the precedent for D6 here.
