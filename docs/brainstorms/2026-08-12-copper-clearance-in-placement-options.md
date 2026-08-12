<!-- provenance: branch docs/placement-model-expressiveness-gaps, from origin/main at d8062c6e6 (#1053), local HEAD 1ef19c161. Companion to 2026-08-12-placement-model-expressiveness-gaps.md on the same branch. No pcb/** or solver source modified; every prototype below ran against scratch copies and a scratch-dir ModelSpec generator. -->

# Copper clearance in the placement model: options, with the framing corrected first

**Status:** research/decision only. No `pcb/**`, no encoder, no
`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs` change. Prototypes ran
in a scratchpad against the committed board. The ranking at the end is
reasoning, not authority.

## Verdict

**Recommended: Option 1 — reserve routing corridors at placement time as
first-class pseudo-components.** I prototyped it against the real
169-component board and it works: a 3×3 grid of 1.6 mm channels costs **+7.2 %
constraints (14,196 → 15,216)**, stays **feasible**, and a post-solve audit
confirms **0 component intrusions and 9 of 9 vertical/horizontal crossings** —
i.e. the reserved free space is a *connected* grid spanning the board, which
is precisely the property whose absence killed #1052 (its corridor mask
fragments into ~94 disconnected regions). It needs **no new constraint type
and no engine change**: corridors are ordinary components and the existing
`separated` primitive does all the work.

**The single most important tradeoff:** a corridor grid buys a *guaranteed
lower bound on routing resource* — a geometric fact about the placement
alone, provable and auditable — but it **cannot** be given a conservative
bound on the DRC `clearance` count, because that count is a property of the
routed board and placement does not determine routing. You are trading a
provable guarantee about the wrong quantity (violations) for a provable
guarantee about a *sufficient* quantity (channel width and connectivity).
Anyone who wants R24 item 1 satisfied against `clearance` itself will not
get it from any placement-side option, including this one. Said plainly and
early because the brief asks for exactly this honesty.

---

## Read this first: three corrections to the task's framing

These change how everything below should be read. All three are measured,
not argued.

### 1. The candidate placement did not regress copper clearance. It fixed every clearance violation placement controls, and the +113 is entirely routed copper.

The brief treats the 386 → 499 `clearance` regression as the thing a
placement-side clearance notion must fix. I recomputed the breakdown from
the raw `kicad-cli` reports for both boards (the reports are **not** checked
in; `drc_ceiling.json` stores only per-type totals):

| geometry pair | `origin/main` (386) | candidate (499) | delta |
|---|---:|---:|---:|
| TRACK ↔ TRACK | 254 | 342 | **+88** |
| PAD ↔ TRACK | 60 | 129 | **+69** |
| TRACK ↔ VIA | 18 | 21 | +3 |
| VIA ↔ VIA | 0 | 4 | +4 |
| PAD ↔ VIA | 16 | 3 | −13 |
| **PAD ↔ PAD** | **38** | **0** | **−38** |
| ZONE ↔ anything | 0 | 0 | 0 |

**Pad-to-pad clearance violations went 38 → 0.** The new placement
*eliminated* every violation attributable to footprint copper geometry. And
**492 of the 499 (98.6 %) fire against one DRU rule** — RULE 10 `"Default
routing"`, `(condition "A.Type == 'Track' || B.Type == 'Track'")`,
`min 0.2mm` — whose own condition requires at least one side to be a track.

Safety-rule clearance violations collapse from ~26 to 1: `HV to LV` 12 → 0,
`AC Mains to LV` 5 → 0, `HV internal same footprint` 4 → 0,
`HighVoltageIsolated to LV` 4 → 0. **The regression is not a safety
regression.** It is a routing-quality/manufacturability regression measured
by a generic 0.2 mm track rule. That distinction matters a great deal for
how much risk is worth taking to close it.

I corroborated this independently from the placement side. On the committed
board, of 131,205 inter-component, different-net, layer-compatible pad
pairs, only **14** sit below 0.2 mm and only 8 actually overlap; separately,
**38 component-box pairs overlap outright** (169 components, all on side 0 —
this is a single-sided placement, so none of that is front/back aliasing).
Two independent methods, both landing on ~38: pad geometry accounts for
roughly a tenth of the baseline and **none** of the increment.

### 2. τ = 0.4 mm — a gap too narrow for *any* net class's trace, by a factor of at least 1.25×.

`courtyard_clearance_mm` = `default_clearance_mm + 2 × MASK_EXPANSION_MM` =
`0.2 + 2 × 0.1` = **0.40 mm** (`_encoder_solve.py:684-701`, `MASK_EXPANSION_MM
= 0.1` at line 32). Against the channel width each class's own trace needs
(`trace_width + 2 × clearance`, from `configs/netclass_rules.yaml`):

| class | trace_width | clearance | channel needed | τ = 0.40 mm suffices? |
|---|---:|---:|---:|:--|
| Signal | 0.20 | 0.15 | **0.50** | no |
| HighSpeed | 0.15 | 0.20 | **0.55** | no |
| FinePitch | 0.127 | 0.10 | **0.327** | yes (only class that fits) |
| Power | 0.50 | 0.25 | **1.00** | no |
| GateDriveHV/SELV | 0.40 | 0.25 | **0.90** | no |
| GND | 1.00 | 0.30 | **1.60** | no |
| HighVoltage / ACMains | 3.00 | 6.00 | **15.00** | no |

**This is the mechanism.** τ is dimensioned to stop solder-mask bridging
between two adjacent footprints — which it does, correctly, and the 38 → 0
pad-pair result is that working. It was never dimensioned to let a *trace
pass between* two components, and it doesn't. HPWL then drives every
unopposed pair to exactly this floor, and the router inherits a board whose
inter-component gaps are, by construction, unroutable. That is the same fact
#1052 measured downstream as "~94 disconnected regions."

### 3. Claim 1's "three constraint shapes" is about what the *board model posts*, not what the engine supports — and claim 3 is right, with a sharper number.

`main.rs` implements **ten** constraint types (`separated`, `adjacent`,
`aligned`, `anchored`, `enclosing`, `keepout`, `on_side`, `bounded`,
`fixed_rotation`, `loop_area`; lines 219-542). The real-board model posts
only three because the full PCL config is infeasible against the current
board geometry — documented separately in this branch's companion audit
(`2026-08-12-placement-model-expressiveness-gaps.md`, "Why courtyard +
netclass separation, not the full PCL config"). **`keepout`, `enclosing` and
`anchored` are live, tested, unused primitives** — Option 1 exploits exactly
this.

Claim 3 (flat τ backfill) is correct, and the isolation-barrier run gives
the exact split: **9,647 netclass + 12,301 courtyard = 21,948** over 168
components, against C(168,2) = 14,028 pairs. So **12,301 pairs (87.7 %) are
governed by the flat 0.40 mm backfill** and only 1,727 (12.3 %) carry a
constraint ≥ τ — those being the 6.0 mm HV rows, the only ones
`_generate_courtyard_separated_constraints` skips. The ~7,900 netclass
constraints in between (Signal↔GND at 0.30, Signal↔Power at 0.25) are
*posted but dominated*: they are strictly weaker than the τ they sit
alongside, and change nothing.

One real defect inside `generate_netclass_separated_constraints`, worth its
own issue: its skip test is `if hasattr(c, "a") and hasattr(c, "b")`
(netclass_constraints.py:90), which matches **`AdjacentConstraint` too**. Any
pair a human deliberately placed close therefore gets *no* netclass
clearance constraint at all and falls back to flat τ. Today that is masked
because τ ≥ most netclass values — but it would silently drop a 6.0 mm HV
separation for any HV pair that also carries an `adjacent` constraint.

---

## Facts recap (measured this session, not re-derived)

- Board **152 × 234 mm = 35,568 mm²**; **169 components / 527 pads**
  committed. (The 168/521 figure is the *reconciled candidate* board, never
  landed: −7 components/−18 pads, +6/+12.)
- **Sum of component box areas = 15,529.5 mm² → 43.66 % utilization.** The
  board is **not** globally area-starved. Inflating every box by δ per side:
  δ=0.2 → 46.2 %, δ=0.3 → 47.5 %, δ=0.5 → 50.2 %, δ=0.8 → 54.6 %. Congestion
  is *local*, not global — consistent with
  `2026-08-08-placement-remediation-analysis.md` finding 42 % of failing nets
  centroid into the MID-MID cell, 11.1 % of board area.
- Baseline board carries **2,290 track segments, 48 vias, 96 zones**.
- Pumpkin decides the 14,196-constraint box model **optimal in 0.9–2.0 s**;
  OR-Tools returns `unknown` at 26 s. Large headroom.
- The isolation barrier is **already at the edge**: all 8 isolators jointly
  UNSAT in 3.17 s (a proof, not a timeout); relaxing U6 alone → optimal in
  2.6 s.
- `comp.bounds` is the **union of courtyard/fab graphics and every pad's
  copper extent**, computed about the placement centre, with `bounds ⊇ pads`
  an invariant proven by construction (`_calculate_footprint_bounds`;
  P8/P9/P10 in `test_geometry_constraints_pbt.py`). **This is why box
  separation is already copper-sound for pad-to-pad** — see `domain_clearance.py`'s
  revised soundness proof, lines 43-127. It is also why Options 2 and 3 below
  are largely redundant.

### Pumpkin's actual constraint API (read, not assumed)

From `pumpkin-constraints-0.5.0/src/constraints/`: `absolute`,
`all_different`, `binary_{equals,not_equals,less_than,less_than_or_equals,
greater_than,greater_than_or_equals}`, `boolean_equals`,
`boolean_less_than_or_equals`, `clause`, `conjunction`, `cumulative`,
`cumulative_with_options`, `disjunctive_strict`, `division`, `element`,
`equals`, `greater_than{,_or_equals}`, `less_than{,_or_equals}`, `maximum`,
`minimum`, `negative_table`, `not_equals`, `plus`, `table`, `times`. The
`Constraint` trait offers `post` and `implied_by`; `NegatableConstraint`
additionally offers `reify` (full biconditional).

**There is no 2-D no-overlap / `diffn` / geometric packing constraint.**
OR-Tools' `AddNoOverlap2D` has no Pumpkin analogue — which is why the
Chebyshev disjunction is hand-rolled from four `implied_by` half-planes plus
a `clause`. Anything below that assumes `AddNoOverlap2D`-style machinery is
speculative for this codebase; I flag each option accordingly.

Two consequences worth stating because they enable options below:
`maximum` over four materialised linear expressions computes a **true
Chebyshev gap as an integer variable** (not merely a disjunctive bound), and
`maximum(gap_shortfall, 0)` gives a hinge penalty with no reification at all.
Soft margin terms are therefore *expressible*; see Option 4.

---

## Options

### Option 1 — Reserve routing corridors as first-class pseudo-components (RECOMMENDED)

**Mechanism.** Add K vertical and M horizontal *corridor* pseudo-components.
A vertical corridor is `(W × board_h − 2m)`, non-rotatable; a horizontal one
is `(board_w − 2m × W)`. Post `separated(corridor, component, 0.0)` for every
real component — forcing the band clear of component copper — and
`separated` between same-orientation corridors so they don't coincide.
**Deliberately do not** separate vertical from horizontal corridors: they
must cross, and those crossings are what make the reserved free space a
*connected grid* rather than isolated stripes. Width `W = trace_width +
2 × clearance` for the class the channel is intended to carry, so a trace on
the centreline has full clearance to component copper on both sides.

**Files that would change.** `_encoder_core.py` (a corridor generator
alongside `_generate_courtyard_separated_constraints`); the ModelSpec
serializer in the real-board harness. **No `main.rs` change** — verified by
building the unmodified binary and running it.

**Verified, not speculative.** Scratch generator + unmodified
`pumpkin_engine`, committed board, 30 s budget:

| config | components | constraints | status | objective |
|---|---:|---:|:--|---:|
| baseline (no corridors) | 169 | 14,196 | feasible | 2,005,980 |
| 3V+3H @ 1.6 mm | 175 | 15,216 (+7.2 %) | **feasible** | 2,040,217 |
| 4V+4H @ 1.6 mm | 177 | 15,560 (+9.6 %) | **feasible** | 2,190,938 |
| 3V+3H @ 0.6 mm | 175 | 15,216 | **feasible** | 1,658,634 |

Post-solve audit on the 3V+3H @ 1.6 mm solution, recomputed from returned
coordinates: **0 component-into-corridor intrusions**, **0 same-orientation
corridor overlaps**, **9 of 9 V–H crossings present**, and 4 of 14,196 τ
pairs short — all 4 by ≤ 0.0052 mm and all explained by the quantization
defect in "Findings" below, not by the corridor mechanism.

Area cost is small: 3×1.6×233 + 3×1.6×151 − 9×1.6² ≈ **1,820 mm² = 5.1 %** of
the board, taking utilization 43.7 % → 48.8 %.

**Caveat on the objective numbers.** Every run above hit the 30 s budget and
returned `feasible`, not `optimal`. The HPWL deltas are therefore *anytime*
values, not proven optima — note the 0.6 mm run scoring *better* than
baseline, which is search noise, not a corridor benefit. Feasibility and the
audit are the load-bearing results; the objective column is indicative only.

**R24 posture.** Item 1 is **satisfiable for the property the constraint
actually states, and not for `clearance`.** Provable conservatively: *if the
model is SAT, then a clear axis-aligned rectangle of width W spanning the
board exists, and the union of such rectangles is connected.* That follows
from the same Chebyshev argument `domain_clearance.py` already proves
(SAT ⇒ every point of box A is ≥ margin from every point of box B), applied
with the corridor as one of the boxes; and `bounds ⊇ pads` upgrades it from
boxes to copper for free. It is a conservative **lower bound on routing
resource**. It is **not** a bound on violation count, and cannot be made
one — the router may decline to use the corridor. State that in the module
docstring the way `domain_clearance.py` states its own limits.
Item 2 (BMC): directly testable — the corridor-vs-component predicate is the
existing `encode_separated` predicate, so the existing
`TestChebyshevSoundnessBMC` sweep covers it unchanged. Item 3 (audit): **I
implemented and ran it** (above); it is ~20 lines and recomputes rectangles
from coordinates.

**Interaction with the isolation barrier.** Good, and this is the strongest
argument for Option 1. The PD2 barrier is *already* a reserved horizontal
band at `y ∈ [113.0, 121.0]` — Option 1 is the same idea generalised, so the
two compose naturally rather than competing. Corridors are also the only
option here that does not uniformly tighten every pair, so it does not push
on the U6 joint-infeasibility edge the way Options 2/4 do. Untested risk:
whether a corridor grid remains feasible *jointly* with all 8 isolator
straddles, given 7-of-8 is already the ceiling. **Test that before
committing to it.**

**Interaction with HPWL.** Mild and controllable: corridors partition the
board, so HPWL pays whenever a net's components land on opposite sides. K and
M are the tuning knob. Note the corridors are placed *by the solver*, not
fixed by a human — the model chooses where channels go, which is the
feature.

**Cost.** ~150 lines of generator + audit, plus the harness wiring. Roughly
1–2 days including the isolator-joint-feasibility test.

**What it gets wrong.** It imposes a *topology* (a rectilinear grid of
full-span channels) rather than discovering the channel structure the
netlist actually wants; full-span channels are wasteful where demand is
local. And W must be picked per corridor from a routing-demand estimate that
is itself a heuristic — which is where the guarantee weakens, honestly.

### Option 2 — Inflate every component box by a per-net-class copper allowance

**Mechanism.** Grow each component's `w0_mm`/`h0_mm` by δ per side before
serializing. Post-inflation box separation at τ implies real gap ≥
τ + δ_a + δ_b.

**Files.** One line in the ModelSpec builder (`refs_sizes`), or
`_calculate_footprint_bounds`.

**Expected effect on the 113: near zero, and this is the option the
measurement kills.** Inflation buys margin *around footprint copper*, and
pad↔pad violations are already **0** on the candidate board. It adds nothing
where the violations are (track↔track and pad↔track). Cheap and sound, but
aimed at a solved problem.

**Is the error conservative or optimistic?** Conservative, cleanly: it grows
a box already proven to contain all pad copper, and the Chebyshev proof is
monotone in box size. That is its one virtue.

**R24 posture.** Item 1 trivially satisfied (monotone in an already-proven
bound). Items 2 and 3 inherit the existing SEPARATED machinery unchanged.
The problem is not soundness; it is relevance.

**Interaction with the isolation barrier: actively bad.** Inflation is
uniform over a component's pairs, so inflating an HV component raises its
6.0 mm separations to 6.0 + δ_a + δ_b as well. With U6 already jointly UNSAT,
spending the tightest constraint's slack to buy margin that isn't needed is
the wrong trade. A per-pair `min_distance` bump (Option 3) is strictly better
if you want this family at all.

**Cost.** Hours. Ranked low on value, not on effort.

### Option 3 — Per-pair channel-demand `min_distance`, replacing the flat τ

**Mechanism.** Replace the flat τ backfill with
`min_distance = max(τ, channel_demand(a, b))`, where `channel_demand`
estimates the width needed for traces likely to pass between a and b — e.g.
from the classes on their incident nets, or a fanout/pin-density estimate.
Pure data change; the SEPARATED handler and its proof are untouched.

**Files.** `_encoder_core.py::_generate_courtyard_separated_constraints`
only.

**Expected effect.** Potentially real, but unbounded downside: it is applied
to **all 12,301 backfill pairs**, and raising τ from 0.40 to even the Signal
channel 0.50 mm tightens 88 % of the model at once. Given U6 is already
UNSAT jointly, I would expect infeasibility quickly. It is also strictly
*less* targeted than Option 1: a wide gap between A and B does not mean the
router will route there, whereas a corridor is a contiguous reserved path.

**R24 posture.** Item 1 is **not** satisfiable as a conservative bound.
`channel_demand` is a heuristic about a routing decision that has not been
made; there is no proof that gap ≥ demand implies any clearance property of
the routed board. Weaker guarantee on offer: *pairwise free width ≥ W*, which
is genuinely conservative and auditable, but pairwise free width is not
composable into a route. Items 2/3 inherit existing machinery.

**Cost.** ~1 day, most of it in the demand estimator. Worth doing as a
*narrow* variant — apply it only to the handful of pairs on the measured
`U27`/`U26`/`rtd_pan` congestion axis, where 487 of 499 violations trace to
15 net pairs — rather than globally.

### Option 4 — Margin-aware soft objective (hinge penalty on proximity to the floor)

**Mechanism.** For each pair, materialise the true Chebyshev gap
`g = maximum([ax0−bx1, bx0−ax1, ay0−by1, by0−ay1])`, then a shortfall
`s = maximum([target − g, 0])`, and add `s` to the minimised objective. HPWL
then no longer packs to the floor unopposed.

**Verified expressible in Pumpkin.** `maximum` and `minimum` are real
constructors and are already used in this exact idiom in `main.rs` (the
`loop_area` and `hpwl_nets` handlers). **This replaces the 4-literal
disjunction with a functional encoding** — arguably cleaner than what's
there. I did *not* prototype it, because it requires editing `main.rs`,
which the brief forbids; so tractability is **unmeasured**.

**Files.** `main.rs` (new objective term + wire field) *and* the Python
serializer. This is the only recommended-tier option needing an engine
change.

**Expected effect on the 113.** Plausibly the largest of any option, because
it attacks the root cause named in claim 2 directly rather than bounding a
symptom — but see cost.

**R24 posture.** Item 1: **a soft term is not a constraint and has no
soundness obligation** — it cannot make the model claim margin it doesn't
have, because it never gates anything. That is a genuine advantage: a
mis-tuned weight produces a worse board, never an unsafe one. The flip side
is it offers **no guarantee at all**, only pressure. Items 2/3 are
correspondingly weaker: there is nothing to BMC, and the post-solve audit can
only report the realised gap distribution, not pass/fail it.

**Interaction with the isolation barrier.** Benign for feasibility — soft
terms cannot cause UNSAT. But it will *compete* with HPWL for a fixed 30 s
budget on a model that already returns `feasible` rather than `optimal` at
that budget, and every pair added to the objective enlarges the search. Per-pair
terms over 14,196 pairs would roughly triple the integer-variable count
(4 gap components + gap + shortfall each). **Restrict it to net-connected
pairs** (~104 HPWL nets' worth) or to a neighbour candidate set.

**Cost.** 2–4 days, most of it tuning weight against HPWL and re-measuring
solve time. Higher risk than Option 1, higher ceiling.

### Option 5 — Two-phase: place, measure real clearance, feed violated pairs back, re-solve

**Mechanism.** Solve, route, run DRC, map violations back to component pairs,
tighten those pairs' `min_distance`, re-solve. Classical cut-generation.

**Expected effect.** The convergence story is the problem and it is not
good. Each re-solve moves *every* component (HPWL is global), so the
violation set after iteration k+1 is not a subset of iteration k's — there is
no monotone quantity, so no termination argument. You would need a
trust-region (a displacement cap, which `minimize_displacement_to` already
provides) to force monotonicity, and even then you terminate at a fixed point
that is not an optimum. The full route is ~740 s per iteration
(`2026-08-08-placement-remediation-analysis.md`), so ten iterations is two
hours.

**R24 posture.** Item 1 not applicable in the usual sense — the tightened
bounds are *empirical*, derived from a measured violation, so each individual
constraint is sound (it encodes an observed fact) but the *procedure* has no
soundness or completeness guarantee. Item 3 is free and excellent: DRC is the
audit. Item 2 is meaningless here.

**Cost.** 3–5 days plus a lot of compute. **Worth keeping as a diagnostic**
(one iteration tells you which pairs matter, which directly feeds Option 3's
narrow variant) rather than as a production loop.

### Option 6 — Model pads, not components

**Mechanism.** Post separation between pad rectangles rather than component
AABBs.

**Tractability, measured.** Pad geometry is fully available at placement time
— `Pin` carries `position` (footprint-local, pre-rotation), `width`,
`height`, `shape`, `layer`, `net`, `pad_rotation_deg`, `roundrect_ratio`,
`is_pth` — with `pin_world_position_at(pin, comp, pos_override,
rotation_override)` as the canonical SSOT transform and `pad_axis_radius(...)`
giving the exact world-axis half-extent under rotation. So it is *buildable*.
Cost: **C(527,2) = 138,601 pad pairs vs 14,196 component pairs — 9.8×** — and
each pad's world position is rotation-dependent, so every pad needs `element`
tables on its parent's `rot` plus two linear ties, roughly **4 extra integer
variables per pad** (2,108 new variables) before any pairwise constraint. At
~1–2 s for 14,196 pairs there is headroom, but this is a different order of
model and I did not prototype it.

**Why I did not.** It is aimed at pad↔pad clearance, which is **already 0 on
the candidate board**, and it is *already sound* via `bounds ⊇ pads` — the
component box is the union of courtyard graphics and pad copper, so box
separation already implies pad separation at the same margin. Option 6 buys
**tightness** (less conservative packing), not **soundness**. Tightness is
the wrong currency here: the board is at 43.7 % utilization and not
area-limited.

**R24 posture.** Item 1 would be *exact* rather than conservative — the
strongest posture of any option. That is genuinely attractive and is why this
stays on the list rather than being rejected outright. Item 2 is a much
larger BMC surface (rotation × shape × pair). Item 3 is straightforward.

**Where it *would* pay.** Two places, both narrow: the 2-of-527 pads that
fell outside the board outline in the isolation-barrier run (an edge-margin
box approximation, exactly the gap this closes), and intra-footprint domain
crossings — though `domain_clearance.py` correctly proves placement can
*never* fix those, since rigid translation cannot change a component's own
pad-to-pad distances.

**Cost.** 1–2 weeks. Right answer eventually; wrong answer now.

---

## Options considered and rejected, with reasons

**R1. Fix it downstream in the router (corridor-aware A*, congestion-aware
ripup, any post-placement remedy).** Refuted by measurement before this
document: `2026-08-12-corridor-aware-plane-backbones.md` proved the mechanism
correct (0/N real trace-vs-obstacle intersections) and connectivity preserved
at floor, yet `clearance` stayed 499–501 across **five** distinct
obstacle/topology strategies, with window-size, clearance-value and topology
independence each verified separately. The corridor mask fragments into ~94
disconnected regions. Do not re-propose.

**R2. Raise `default_clearance_mm` (and hence τ) globally.** Tempting
one-liner; wrong. τ is already sufficient for the pad-to-pad job it does
(38 → 0). Raising it tightens 87.7 % of pairs uniformly to buy margin where
there is no violation, and pushes on a constraint set already proven jointly
UNSAT at U6. Strictly dominated by Option 1.

**R3. Rasterize a congestion/RUDY map and constrain bin density.** Classical
and effective in the literature, but requires a grid, and grid occupancy over
*continuous integer box coordinates* needs either `AddNoOverlap2D`-class
machinery (**absent in Pumpkin** — verified) or a reified
component-in-bin indicator per (component, bin) pair. At 169 components ×
even a coarse 20×30 grid that is 101,400 reified literals plus the
channelling constraints. Expressible in principle via `element`/`clause`;
not tractable at this scale without measurement I have not done, and the
bin-density bound would be *optimistic* about routability (low density does
not imply a connected channel). Option 1 gets the connectivity property
directly for +7 % constraints.

**R4. `cumulative` as a 1-D density proxy.** Pumpkin *does* ship
`cumulative`, so unlike R3 the primitive exists. But projecting a 2-D
placement onto one axis and bounding total width per x-slice bounds *area*,
not *channel connectivity* — a slice can be under capacity and still have no
gap wider than 0.4 mm anywhere in it. Optimistic in exactly the direction
that matters. Rejected on soundness, not tractability.

**R5. Assign components to front/back to relieve congestion.** The model has
no side variable and the board is **single-sided in placement** (all 169
components on side 0, verified). This would roughly halve local density and
is probably the single largest available lever — but it is a
board-architecture decision with thermal, assembly-cost and DFM
consequences far outside a clearance fix. Logged as a real option for a
human, deliberately not costed here.

**R6. Encode the `clearance` DRC count itself as a CP objective.** Not
expressible: the count is a function of the routed board, and the router is
not in the model. Any encoding would be a proxy, which is what every other
option already is — but named explicitly because it is the thing someone will
ask for.

---

## Findings that contradict or sharpen the four established claims

1. **Claim 1 ("never pads") is true literally but misleading in
   consequence.** `SEPARATED` does operate on boxes — but `comp.bounds` is
   the union of courtyard graphics *and every pad's copper extent*, computed
   about the placement centre, with `bounds ⊇ pads` proven by construction.
   So the encoding **is already copper-sound for pad-to-pad clearance**, and
   the measured 38 → 0 pad-pair result is that soundness working. What is
   genuinely missing is not pad awareness but *channel* awareness.

2. **Claim 1's "three constraint shapes" understates the engine.** Ten types
   are implemented and tested; the board model posts three because the full
   PCL config is infeasible against current geometry. `keepout`, `enclosing`
   and `anchored` are live and unused — Option 1 is cheap precisely because
   of this.

3. **Claim 4's premise is right but its target is wrong.** #1052 is correctly
   refuted, but the reason generalises further than stated: the +113 is
   **100 % routed copper**, and placement's contribution to `clearance` went
   *down* (38 → 0). No placement-side "copper clearance" notion can fix the
   113 by separating copper; it can only fix it by creating room to route.

4. **A real, previously unreported optimistic approximation in
   `to_units`** (`main.rs:69-74`). It rounds half-to-even and then **forces
   even parity by decrementing**, so a box dimension can be encoded up to
   **0.010282 mm smaller than the true footprint envelope** — meaning every
   SEPARATED constraint on that component is satisfied at up to ~0.021 mm
   less than nominal (both boxes can shrink). This surfaced as the 4
   sub-0.0052 mm shortfalls in my Option 1 audit and reproduces exactly:
   `30.130282 → 3013.0282 → 3013 (odd) → 3012 → 30.12 mm`. Scope is narrow —
   **6 of 338 dimensions**, on C2/C3/C4/C5 (30.130282), K1 (26.75), PS1
   (33.65) — and at 6.0 mm HV margins it is 0.34 % of margin, not a hazard.
   But it is *optimistic*, i.e. the wrong direction, and the companion audit
   on this branch explicitly reports "not found: an explicit numeric margin
   in the CP-SAT/Pumpkin model that overclaims safety." This is one, small.
   **Fix is one line: round dimensions *up* to even units.** Even parity is
   required (the `2·cx = 2·x0 + w` midpoint identity is unsatisfiable for odd
   `w`), so ceiling-to-even preserves the invariant while making the error
   conservative.

5. **Netclass SSOT drift.** `pcb/temper.kicad_pro` gives `HighVoltage`
   clearance **2.0 mm**; `configs/netclass_rules.yaml` gives **6.0 mm**. The
   generated `.kicad_dru`'s same-domain rules agree with the 2.0. The 6.0
   survives only in the placer config and the `AC Mains to LV` DRU rule. The
   placer is thus solving against a stricter HV figure than the DRC enforces
   — conservative, so not a hazard, but it means placer infeasibility (U6)
   is being driven partly by a number the fab rules don't require.

6. **The `hasattr(c, "a")` skip bug** in
   `netclass_constraints.py:90` (see framing correction 3) — an `adjacent`
   constraint silently suppresses a pair's netclass clearance.

---

## Ranking

1. **Option 1 (corridors).** Only option that attacks the measured failure
   (fragmented free space), verified feasible at real scale, no engine
   change, audit implemented and passing. Do the isolator-joint-feasibility
   test first.
2. **Option 4 (soft margin).** Highest ceiling, cannot cause UNSAT, cannot
   be unsafe. Needs an engine change and real tuning. Best paired with
   Option 1, not instead of it.
3. **Option 3, narrow variant.** Cheap and targeted if scoped to the
   measured `U27`/`U26`/`rtd_pan` axis. Global variant rejected.
4. **Option 5 as a one-shot diagnostic** to generate Option 3's pair list.
5. **Option 6 (pads).** Correct long-term model, wrong problem today.
6. **Option 2 (inflation).** Sound, cheap, aimed at a solved problem.

Independent of all of the above, and cheaper than any of them: **fix the
`to_units` rounding direction** (finding 4) and **the `hasattr` skip bug**
(finding 6).

## Questions only a human can answer

1. **Is 499 actually a blocker?** 98.6 % of it is a generic 0.2 mm track
   rule; safety-rule clearance went 26 → 1 and creepage −60 %. The candidate
   board is *safer* and better-connected. Is holding it back on a metric that
   measures routing quality the right call, or should the ratchet be
   re-based to accept a safer board with more track-clearance work
   outstanding?
2. **Two-sided placement (R5)?** Probably the largest single lever on
   congestion, and entirely outside a solver fix.
3. **Which HV clearance is authoritative** — 2.0 mm (`.kicad_pro` + DRU) or
   6.0 mm (placer config)? U6's joint infeasibility may partly dissolve at
   2.0.
4. **How many corridors, how wide, and carrying what?** Option 1's W must be
   chosen from routing demand; I used a uniform 1.6 mm (GND-class) as a
   feasibility probe, not a recommendation.

## Sources

- `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs` — engine; ten
  constraint types; `to_units` at 69-74; SEPARATED at 222-271; objective at
  545-614.
- `pumpkin-constraints-0.5.0` / `pumpkin-core-0.5.0` (cargo registry) —
  constraint constructors and the `Constraint`/`NegatableConstraint` traits.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_core.py`
  — τ backfill at 340-385.
- `.../cp_sat/netclass_constraints.py` — cross-class generator; skip bug at 90.
- `.../cp_sat/domain_clearance.py` — the R24 template; revised soundness
  proof at 43-127.
- `.../cp_sat/_encoder_solve.py:684-701` — `courtyard_clearance_mm`.
- `packages/temper-placer/configs/netclass_rules.yaml` — class widths and
  clearances.
- `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` — #1052
  refutation; 94 disconnected regions; no-plane baseline 392.
- `docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md` —
  21,948 constraints; U6 UNSAT in 3.17 s.
- `docs/evidence/2026-08-12-place-and-reroute-connectivity.md` — 386 → 499.
- `docs/evidence/2026-08-08-placement-remediation-analysis.md`,
  `docs/evidence/2026-08-11-stage4-placement-congestion-spike.md` —
  congestion localisation.
- `docs/brainstorms/2026-08-12-placement-model-expressiveness-gaps.md` —
  companion audit on this branch.
- `AGENTS.md` R24; `docs/physics-verification-methodology.md`.
- Prototypes and measurements this session: scratch ModelSpec generator +
  unmodified `pumpkin_engine`; DRC geometry-pair breakdown recomputed from
  raw `kicad-cli` JSON (reports are ephemeral and not checked in).
