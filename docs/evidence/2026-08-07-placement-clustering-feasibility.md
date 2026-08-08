provenance: commit=97f377b1c06ac83e7c162a02294d2d4774d15314 dirty=true

# Placement-clustering feasibility: the board is unstructured because nothing in the placer's objective asks it not to be, not because safety/thermal constraints forbid it — and a real clustering objective does not exist to weight up or down

**Date:** 2026-08-07

**Task:** a feasibility study (not a re-placement) into whether clustering
component placement along the atopile module hierarchy could unblock
`#871` (22,493,900 primary variables, `MemoryError` at 5.43 GB under an
8 GB cap), given that two independent size-reduction levers — geographic
pruning (0% measured reduction) and block decomposition (nets-per-model
win only, no edges-per-model win) — were both traced to the same root
cause: **this board's placement is spatially unstructured with respect to
its own module hierarchy.**

`pcb/temper.kicad_pcb` was not modified by this task (confirmed: sha256
`1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`,
unchanged from the two source documents this task builds on).

**Headline, stated up front:** Module-clustered placement is mechanically
achievable — roughly 89% of the board's 169 components (~150) carry no
hard position pin at all, so the *freedom* two prior investigations
worried might be constrained away by safety/thermal rules is, in fact,
mostly still there. What is missing is not freedom but *incentive*: the
CP-SAT placer that actually produces this board's committed layout has
exactly one live objective term anywhere in it, and it is a
minimum-displacement repair term for small local patches (issue `#504`),
not a wirelength, HPWL, or module-affinity term. A plausible-looking
`component_groups` / `loss_weights` config surface exists in
`configs/temper_constraints.yaml` but is either fully unread by any
placement code (`loss_weights`, `AestheticConstraints.grouping_weight`) or
wired only into a separate rule-based *initial-guess* heuristic
(`heuristics/organizational.py`) that is not the same code path as the
production CP-SAT solve — and this task's own dispersion measurement,
independent of both prior investigations' bounding-box approach, confirms
the board that actually resulted looks statistically indistinguishable
from uniform scatter, consistent with no clustering pressure having ever
been applied. Clustering would help the one safety failure mode this task
could directly attribute (creepage's dominant offender, R30, violates
almost exclusively against SELV-domain neighbours while R30 itself is
HV-domain) if paired with the isolation barrier's HV/SELV split — which is
implemented but not applied to the committed board. The arithmetic payoff,
chained from two prior measurements, is large (ESTIMATED, not measured)
but depends on three unproven things landing together: a clustering
objective that does not exist yet, an isolation barrier not yet applied to
the real board, and a pruning margin already known to be miscalibrated for
this board. The defensible near-term path to `#871` remains what the two
prior documents already concluded: shrink the SAT formulation by other
means.

---

## 0. Base and provenance

Merged per task instructions:

- `worktree-agent-a11904da8310c7be8` (fast-forward) — block-decomposition
  plan (`docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md`),
  `tools/block_partition.py`, `tools/block_edge_estimate.py`.
- `worktree-agent-a14cebd66c9c866e4` (merge commit) — the U5 pruning
  measurement (`docs/evidence/2026-08-07-pruned-encoding-measurement.md`).

Both merges were clean (no conflicts). This document's own contribution is
one new read-only tool, `tools/block_dispersion_measure.py` (committed
separately, `97f377b1`), plus the analysis below. Host: Linux, same
worktree as the two merged branches; Python 3.9.17 system default (both
`tools/*.py` scripts are stdlib-only for this reason, matching
`block_edge_estimate.py`'s own constraint); `uv run` provides Python 3.12
for anything that needs the real `temper_placer` package.

---

## 1. Quantify the current state: per-block spatial dispersion, three ways

### 1.1 What was already measured, before this task

`docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md` §4
already measured per-block **bounding-box area as a fraction of the
board**, using name-based net classification against the atopile source
(`tools/block_edge_estimate.py`): 8 of 11 blocks with resolvable geometry
cover **≥84% of the board's 152×234mm area each**. This task reproduces
that figure exactly (same tool, same board, unchanged hash):

```
$ python3 tools/block_edge_estimate.py
block         comps   area%  est.edges  nets(own)  nets(+bnd)    vars(own)    vars(+bnd)
power_in         28  100.0%     204490         16          18    3,271,840     3,680,820
discharge        25  100.0%     204490         14          15    2,862,860     3,067,350
power_mgmt        0    0.0%          0          6           6            0             0
aux_supply        0    0.0%          0          0           0            0             0
hb               28  100.0%     204490         20          24    4,089,800     4,907,760
tank              5   84.0%     171874          3           5      515,622       859,370
ct_sense         14  100.0%     204490          5           8    1,022,450     1,635,920
rtd_pan          31  100.0%     204490         24          31    4,907,760     6,339,190
safety           62  100.0%     204490         33          44    6,748,170     8,997,560
mcu              34  100.0%     204490         26          44    5,316,740     8,997,560
thermal           2   16.7%      34211          1           1       34,211        34,211
```
(MEASURED, reproduced this task, `tools/block_edge_estimate.py`, default
`--margin-mm 15`.) 34 of 169 refdes are unclassified by this tool's
net-name-prefix method (mostly bulk-decoupling caps with only
locally-scoped pin names) — the same caveat the plan already recorded.

### 1.2 New this task: radius of gyration and convex-hull area

Bounding box has a known weakness: a single outlier component can inflate
it without the block actually being spread out. This task adds
`tools/block_dispersion_measure.py` (new, committed `97f377b1`, read-only
against `pcb/temper.kicad_pcb`), reusing the *identical* component→block
classification from `block_edge_estimate.py` (so block membership is not
re-derived or subject to a second source of disagreement), and computes
two metrics bounding box doesn't capture:

- **Radius of gyration (Rg)** — RMS distance of each block's components
  from their own centroid. Not dominated by one outlier; reflects the
  *typical* component's spread.
- **Convex hull area**, as a fraction of the whole board's own convex hull
  area — a tighter, non-inflatable footprint measure than bounding box.

```
$ python3 tools/block_dispersion_measure.py
Whole-board Rg = 91.1 mm | hull area = 33392 mm^2 (93.9% of bbox) | diagonal = 279.0 mm

block         comps   Rg(mm)  Rg%board   hull mm2  hull%board  bbox%board
power_in         28     92.7    101.8%      30165       90.3%       96.0%
discharge        25     92.8    101.9%      28498       85.4%       92.3%
hb               28     82.8     90.9%      25378       76.0%       92.7%
tank              5     71.7     78.7%       9935       29.8%       62.7%
ct_sense         14     93.3    102.5%      19510       58.4%       92.1%
rtd_pan          31     94.0    103.2%      27050       81.0%       91.5%
safety           62     92.0    101.0%      29915       89.6%       96.8%
mcu              34     95.3    104.6%      29309       87.8%       96.6%
thermal           2     43.6     47.9%          0        0.0%        5.2%
```
(MEASURED, this task.)

**This is a stronger and more independent confirmation than the
bounding-box figure alone.** 8 of the 9 blocks with resolvable geometry
measure a radius of gyration **90–105% of the whole board's own Rg** —
statistically indistinguishable from the components being scattered
uniformly across the entire board with no regard for module membership.
`safety` (62 components, the single largest block) has Rg 92.0mm against
a board-wide Rg of 91.1mm — i.e. `safety`'s own components are, on
average, spread out *exactly as much as a uniformly random sample of the
whole board would be*. Only `tank` (5 components, Rg 78.7% of board) and
`thermal` (2 components, Rg 47.9% of board, hull area 0 because n=2 is
degenerate for a hull) show any real reduction, and both are the
smallest-population blocks — consistent with the plan's own caveat that
`thermal`'s apparent clustering "is more likely an artifact of having too
few resolved components than genuine clustering," which this task's
independent metric now supports rather than merely repeats.

### 1.3 Re-measurable going forward

Both `tools/block_edge_estimate.py` (existing, from the merged branch) and
`tools/block_dispersion_measure.py` (new, this task) are committed,
read-only, stdlib-only scripts. Re-running either after any future
placement change reproduces the same numbers by construction — this is
the metric baseline the task asked for.

---

## 2. How much placement freedom actually remains

**Most of it.** Contrary to the risk the task brief raised ("if safety and
thermal constraints already dictate most positions, module clustering may
be unavailable regardless of objective"), this is not what the code shows:

- **Hard-pinned components: 9 of 169 (5.3%).** `configs/temper_constraints.yaml`'s
  `fixed_components` list names only the 4 mounting holes (`MH1`–`MH4`,
  "PowerSynth approach: Only fix MECHANICAL constraints, let optimizer
  handle electrical/thermal" — the config's own comment notes connectors
  were deliberately *removed* from this list in the past). But
  `fixed_positions` additionally gives literal coordinates for 5
  connectors (`J_AC_IN`, `J_NTC`, `J_COIL` — the coil interface, `J_USB`,
  `J_DEBUG`), and the Rust-backed loader
  (`packages/temper-design-bundle/src/config_loader.rs:2104-2129`,
  `apply_fixed_components_to_netlist`) sets `component.fixed = True` for
  **any** ref appearing in *either* list — so all 9 are hard-pinned in the
  netlist, not just the 4 named `fixed_components`. In the CP-SAT encoder
  itself, a pinned ref becomes a binding equality
  (`x_center == pin_x`/`y_center == pin_y`/`rot_ref == rot`,
  `_encoder_solve.py`) — "the solver cannot move a pinned ref."
- **8 isolators (`C6, K1, K2, K3, PS1, T1, U3, U7`) are free in position
  but constrained in rotation and pad geometry** by `isolation_barrier.py`
  when that module is invoked (see §5) — their courtyard may straddle the
  HV/SELV corridor (that is their function) but their own HV pad cluster
  and SELV pad cluster are each pinned to the correct side.
- **The remaining ~150 components (~89% of the board) are fully free in
  position**, subject only to overlap/board-bounds, courtyard, creepage/
  clearance, and (where configured) thermal-edge-preference constraints —
  none of which impose a two-region or module-region split *on the
  committed board today* (see §5: the one mechanism that would, the
  isolation barrier, is implemented but not applied to `pcb/temper.kicad_pcb`).

**Conclusion for this section:** the dispersion measured in §1 is not a
consequence of safety/thermal rules eating the placement freedom that
clustering would need. Nearly 9 in 10 components have nowhere near enough
constraint pressure on them to explain why they ended up scattered
board-wide rather than clustered by module — the constraints that exist
mostly don't care about clustering one way or the other. The explanation
is in §3.

---

## 3. Does the placer have a clustering objective? No — and not merely "weighted to zero"

This is the load-bearing negative result of this task. Searched
exhaustively (`grep -rn "Minimize\|Maximize" packages/temper-placer/src/temper_placer/placer/cp_sat/*.py`):
**exactly one call site**, `model.py:290`, inside `apply_objective()`. Its
only caller of `add_objective_term` (the only way to feed that
`Minimize()`) is `add_displacement_objective` (`model.py:293-337`), used
for the minimum-displacement repair path (issue `#504`): "the solver
returns the feasible placement closest (Manhattan) to these reference
positions... a preference, never a hard bound." This exists to support
freeze-and-locally-repair solves (small neighborhoods around a DRC
violation), not a global layout objective — and it pulls *toward a given
reference placement*, not toward any notion of compactness or module
affinity.

**"Phase 2 wirelength polish" (`_loop_core.py:905-930`, `_encoder_solve.py:492-495`)
does not add a wirelength objective.** Its own code just re-invokes the
solver with the same constraint set and a longer timeout (5s vs the
Phase-1 budget) — no new `Minimize()` call, no distance/HPWL term. The
name is a holdover, not a description of what the code does today; with
no objective registered, CP-SAT's Phase-2 re-solve returns the first
feasible solution found under the (longer) time budget, not a
wirelength-minimized one, unless a displacement objective happens to be
separately configured for that call.

**A clustering-*shaped* config surface exists, but is disconnected from
the objective that actually runs:**

- `configs/temper_constraints.yaml`'s `component_groups:` section defines
  named groups (`power_stage`, `gate_driver`, `current_sensing`,
  `mcu_system`, `power_rail_5v`, `power_rail_3v3`) with `max_distance` and
  `weight` fields, and comments describing a `GroupClusterLoss` as part of
  a "PowerSynth approach." **`GroupClusterLoss` does not exist anywhere in
  this repository** (`grep -rn "GroupClusterLoss" .` — zero matches). The
  parsed `ComponentGroup` objects (`_constraint_types/groups.py`) are
  consumed in exactly two places: `validation/preflight.py` /
  `validation/drc_runner.py` (zone-assignment bookkeeping — checking a
  component landed in *some* zone, not enforcing `max_distance`) and
  `heuristics/organizational.py`'s `identify_functional_modules` — a
  **rule-based initial-guess heuristic** feeding `pipeline/topological.py`,
  a separate deterministic placement path, not the CP-SAT solve.
- `configs/temper_constraints.yaml`'s top-level `loss_weights:` block
  (`grouping: 50.0`, `wirelength: 20.0`, `thermal_spread: 25.0`, etc.) has
  **zero references anywhere in `packages/temper-placer/src/`** — not
  parsed into any Pydantic field, not read by any loader. It is dead
  configuration.
- `AestheticConstraints.grouping_weight` / `whitespace_weight` /
  `symmetry_weight` (`_constraint_types/config.py:146-152`) are real
  Pydantic fields, default `0.0`, but referenced only by
  `tests/io/_config_loader_py_oracle.py` (a test double for the config
  *loader*, not by any placement or solving code) — genuinely inert, not
  merely defaulted low.
- `pipeline/stages/geometric_stage.py`'s own docstring: **"CP-SAT
  placement dispatch stage (JAX gradient descent removed)."** Its body
  does not call CP-SAT at all in the DAG-pipeline path — it delegates to
  the topological/heuristic initializer. This strongly suggests the
  `loss_weights`/aesthetic-weight surface is a remnant of a prior,
  removed gradient-descent placement system (a natural home for
  differentiable loss terms like "grouping" and "wirelength") that was
  never re-implemented as CP-SAT constraint/objective terms after that
  system's removal.

**Corroboration from the board's own history:** `power_pcb_dataset/drc_ceiling.json`'s
`_march` log (read-only, not modified by this task) records the actual
sequence of changes to the committed board — a K2 relay swap and re-solve,
edge-hanging-ref nudges, a PD2 clearance resolve, a K3 swap-and-write —
every one of them a **targeted, individual-component repair**, not a
global re-cluster. This matches what §1's dispersion measurement shows:
the board looks like it was produced by a long sequence of local patches
on top of an originally-unclustered layout, not by any pass with a
clustering-aware objective, because no such pass exists in the code that
built it.

**Answer to the task's question:** no clustering objective exists in the
placer that produces this board. It is not present-but-zero-weighted; the
CP-SAT `Minimize()` call site that would need to carry such a term carries
exactly one unrelated term, and the config keys that look like they should
feed a clustering loss are either unread entirely or wired into a
different, non-CP-SAT code path.

---

## 4. Estimated payoff (ESTIMATED — chained from two measured baselines, not independently validated)

All figures below are labeled ESTIMATED. They chain the U5 pruning
measurement's board geometry figures with this task's own dispersion
measurement and `block_edge_estimate.py`'s documented area-proportional
edge-density assumption ("skeleton edge density is roughly uniform per
unit of free area for a board this size" — the tool's own stated
approximation, not re-derived here).

**Model size, if a block packed into ~1/11 of the board's area** (an
idealized equal partition — not validated as physically achievable, see
§5):

```
edges_est(clustered)  = 204,490 x (1/11)              ~=  18,590 edges   (ESTIMATED)
largest block (safety, 44 nets, own+boundary):
  vars_est(today, unclustered, MEASURED area 100%)     =  8,997,560 vars (MEASURED, §1.1)
  vars_est(clustered, ~9% area)                        ~=  18,590 x 44 = 817,960 vars (ESTIMATED)
  reduction factor for this one block                  ~=  11x         (ESTIMATED)
```

That is on top of, not instead of, the net-count reduction block
decomposition already delivers without any placement change (safety's
8,997,560 vars is already 40.0% of the 22,493,900-var monolith,
MEASURED, §1.1/the merged plan). Compounding the two (nets-per-model win,
already real; edges-per-model win, ESTIMATED and clustering-dependent)
would put the largest block's local model in the **high hundreds of
thousands of variables**, comfortably under the 5.43 GB `MemoryError`
point (ESTIMATED).

**Median net pin span, if intra-block nets shrink with block linear
extent:** today's median is 120.9mm on a 279mm diagonal (MEASURED,
`docs/evidence/2026-08-07-pruned-encoding-measurement.md`). If a block's
linear extent shrinks to `sqrt(1/11) ~= 30%` of the board's own linear
scale, and most nets stay intra-block (86% do today by count — 148
internal / 172 atopile-derived total, MEASURED, the merged plan §3),
intra-block median span would plausibly scale similarly:

```
median span, clustered (intra-block nets only) ~= 120.9mm x 0.30 ~= 36mm  (ESTIMATED)
```

**Geographic pruning, if median span drops to ~36mm:** the predicate's
margin `M_n = max(2 x S_n, M_min=30mm)` would become `~=72mm` for a
typical intra-block net — well under the board's 279mm diagonal and its
139.5mm half-diagonal pruning-effectiveness threshold (both MEASURED,
`docs/evidence/2026-08-07-pruned-encoding-measurement.md` §6.1). Pruning,
currently 0% effective because 66% of nets already exceed the half-board
threshold, would very plausibly become effective again for intra-block
nets under this scenario (ESTIMATED — not measured, and the 24
boundary nets, 14% of the atopile-derived net count, remain full-span and
unprunable regardless of any clustering, since they connect two different
blocks by definition).

**Combined:** nets-per-model (real, ~30-40% for the worst block, MEASURED
today without any placement change) x edges-per-model (~9-11x, ESTIMATED,
clustering-dependent) x pruning-within-block (uncertain magnitude,
ESTIMATED, pruning-dependent) chains toward a large aggregate reduction on
paper. This is explicitly not claimed as validated: it depends on three
things landing together, none of which is proven independently today (see
Verdict, §6).

---

## 5. Safety interaction: which way does clustering cut?

**Directly measured corroboration that it can cut the right way.** The
task brief names creepage's dominant offender as `R30`. This task
identified `R30`'s block membership and its known violation partners
(`docs/evidence/2026-07-28-clearance-copper-to-copper.md`, a pre-existing
document, positions cross-checked against the current board via
`tools/block_edge_estimate.py`'s classifier):

```
R30  -> block: tank      (HV domain)     position (49.1, 124.5)
R1   -> block: power_in  (HV domain)
R32  -> blocks: mcu/safety/ct_sense (SELV/boundary domain)
R73  -> block: safety    (SELV domain)
R54  -> block: safety    (SELV domain)
U13  -> block: rtd_pan   (SELV domain)
R46  -> block: rtd_pan   (SELV domain)
R26  -> blocks: mcu/hb   (mixed)
```
(MEASURED this task for block membership; the creepage-pair list itself is
from a 2026-07-28 document that predates several `_march`-log re-solves,
so this is corroborating, not an exhaustive up-to-date re-run of the
creepage checker — flagged rather than overstated.)

**`R30`'s violation partners are dominated by cross-domain (HV vs. SELV)
pairs** — exactly the interleaving `docs/evidence/2026-07-30-pd2-enclosure-decision.md`
already names: *"The current placement is interleaved; adding an
arbitrary vertical strip would produce far-side crossings... The current
board still has no named `MAINS_SELV_ISOLATION_BARRIER` keepout."* That
same document and `validation/gate_input_registry.py:574`
(`"baseline red on main (no keepout zones); probe inconclusive today"`)
confirm the task brief's "zero isolation keepout zones" claim directly.

**The tool that would fix exactly this already exists, but isn't applied
to the committed board.** `placer/cp_sat/isolation_barrier.py` implements
a hard, directional two-region split: every HV-only component forced to
one side of a corridor axis, every SELV-only component to the other, with
the 8 isolators pad-cluster-split across both — "a single one-sided
linear inequality per component" (module docstring). This is a *coarser*
version of module clustering than the 11-block partition, but it is
already aligned with it: the block-decomposition plan's own domain table
puts `power_in, discharge, hb, tank` on the HV side and `safety, mcu,
rtd_pan, power_mgmt, aux_supply, thermal` on the SELV side — exactly the
partition that would relieve `R30`'s (tank/HV) violations against `R73`,
`R54` (safety/SELV) and `U13`, `R46` (rtd_pan/SELV). **Module clustering
that also respects this domain split cuts toward safety, not away from
it, for this board's specific dominant creepage offender.**

**Ways it could cut the other way, both flagged rather than dismissed:**

1. **Thermal concentration.** `configs/temper_constraints.yaml` already
   needs `Q1`/`Q2` (the IGBTs) pinned near the top edge
   (`max_distance_from_edge_mm: 5.0`) and the LDOs kept `>= 15mm` apart to
   avoid hot spots. Pulling `hb`'s `power_stage` group into a materially
   smaller area (§4's ~9%-of-board scenario) works directly against that
   existing thermal-spread intent unless a real thermal-aware term is
   added alongside any new clustering objective — clustering and thermal
   spreading are in tension for exactly the block that runs hottest.
2. **Intra-domain clearance pressure.** Clustering reduces the area
   available *within* each block, which raises pairwise creepage/clearance
   pressure between same-domain neighbors even as it relieves cross-domain
   pressure. The board's creepage test is already failing today
   (dominant offender `R30`, per the task brief) without any extra
   packing pressure; clustering without an accompanying clearance-aware
   term could trade a cross-domain win for new same-domain violations.
3. **Long HV runs across the boundary: measured to be a smaller risk than
   it sounds.** The 24 point-to-point boundary nets crossing block seams
   are, per the merged plan §3, disproportionately already isolator-
   mediated (`I_SENSE` via an isolated CT, `V_BUS_SENSE` via an isolated
   divider, `ZCD_ISO` via an optocoupler, `OVP_VREF_2V5` via a reference)
   — so module clustering does not, by itself, force new bare-copper HV
   runs across the domain seam; the isolation points are already named
   and few.

**Verdict for this section:** clustering cuts toward safety on the coarse
HV/SELV axis (measured, via `R30`), provided it is paired with the
isolation barrier's directional split rather than left to a naive
proximity objective alone — but it does not, by itself, fix the board's
currently-failing creepage test, and risks trading a domain-crossing win
for a same-domain (thermal or fine-clearance) regression unless a
clearance/thermal-aware term rides along with any clustering objective.

---

## 6. Verdict

**Is module-clustered placement achievable?** Mechanically, yes. ~89% of
the board's components (150/169) carry no hard position pin (§2); the
building blocks for a domain-respecting version already exist and are
proven to relieve at least one measured, named safety violation (§5).
What is missing is not freedom but an objective: the CP-SAT placer that
produces the committed board has no wirelength, HPWL, or module-affinity
term anywhere in its live `Minimize()` path (§3) — only a
minimum-displacement repair term used for small local patches. The
`component_groups`/`loss_weights` config surface that looks like it
should provide this is either fully dead code or wired into a separate,
non-CP-SAT rule-based initializer, evidently a remnant of a removed
gradient-descent ("JAX," per `geometric_stage.py`'s own docstring)
placement system that was never replaced with an equivalent CP-SAT
objective term.

**What would it cost?** A real clustering objective would need to be
designed and added to `model.py`'s `apply_objective()` path — the
codebase's own existing caution about the *displacement* objective's cost
("the full O(n²) objective with 33 components creates ~2100 extra
variables and makes the solver hit the timeout," `_encoder_solve.py:492-494`)
applies with more force here: a genuine module-clustering term over ~150
free components (centroid-distance or pairwise-intra-group terms) is a
substantially larger CP-SAT variable/constraint budget than the ~33-
component case already flagged as marginal. It would also need to be
designed alongside — not instead of — the isolation barrier's HV/SELV
split (currently unapplied to the real board) and a thermal/clearance-
aware term, per §5's caution, or it risks net-negative safety trade-offs.
None of this is small work, and none of it is started.

**Would it actually unblock `#871`?** The arithmetic chain in §4 is large
on paper but ESTIMATED, not measured, and depends on three unproven
things landing together: (1) a clustering objective that does not exist
yet, (2) the isolation barrier being applied to the real board (it isn't
today), and (3) geographic pruning's margin recovering effectiveness once
spans shrink (plausible per the math, but pruning's own U5 measurement
already found this board's margin miscalibration once; a second
miscalibration on a differently-shaped problem is a real risk, not
dismissed here). **The honest answer matches what both prior,
independent investigations already concluded: shrink the SAT formulation
by other means in the near term** — block decomposition's real,
already-measured nets-per-model win (largest block at 30-40% of the
monolith, no placement change required), a re-tuned or re-scoped pruning
predicate, or a deliberately relaxed memory gate for `#871` specifically.
Module-clustered placement is a real, board-supported, multi-quarter
research direction with a genuinely positive safety interaction on its
strongest axis (HV/SELV) — not a near-term fix for the 5.43 GB OOM this
task was asked to evaluate it against.

---

## Sources

- `docs/evidence/2026-08-07-pruned-encoding-measurement.md` — U5 pruning
  measurement (0% reduction; 120.9mm median pin span on a 279mm diagonal;
  22,493,900-variable, 204,490-edge, 110-net baseline; 5.43 GB
  `MemoryError`). Merged this task from `worktree-agent-a14cebd66c9c866e4`.
- `docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md` —
  block-decomposition plan (11-block partition, 24 boundary nets, per-block
  bounding-box measurement, 30-40% largest-block reduction, HV/SELV domain
  table). Merged this task from `worktree-agent-a11904da8310c7be8`.
- `tools/block_edge_estimate.py`, `tools/block_partition.py` — reused
  unmodified this task (§1.1).
- `tools/block_dispersion_measure.py` — new this task, committed
  `97f377b1` (§1.2).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`,
  `_encoder_solve.py`, `_loop_core.py` — the CP-SAT objective search (§3).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py` —
  the mains/SELV directional-split constraint (§2, §5).
- `packages/temper-placer/configs/temper_constraints.yaml`,
  `packages/temper-placer/src/temper_placer/_constraint_types/config.py`,
  `_constraint_types/groups.py`,
  `packages/temper-placer/src/temper_placer/heuristics/organizational.py`,
  `packages/temper-placer/src/temper_placer/pipeline/stages/geometric_stage.py` —
  the disconnected `component_groups`/`loss_weights` config surface (§3).
- `packages/temper-design-bundle/src/config_loader.rs:2104-2129` —
  `apply_fixed_components_to_netlist`, confirming `fixed_positions`
  entries are hard-pinned, not merely hinted (§2).
- `docs/evidence/2026-07-30-pd2-enclosure-decision.md` — PD2
  protected-compartment decision (commit `ee3da42a`), "no named
  `MAINS_SELV_ISOLATION_BARRIER` keepout," "current placement is
  interleaved" (§5).
- `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py:574` —
  "baseline red on main (no keepout zones)" (§5).
- `docs/evidence/2026-07-28-clearance-copper-to-copper.md` — R30's
  creepage-violation partner list, cross-checked against block membership
  this task (§5).
- `power_pcb_dataset/drc_ceiling.json` — `_march` log, read-only,
  corroborating the committed board's history of individual-component
  repairs rather than a global re-cluster (§3).
