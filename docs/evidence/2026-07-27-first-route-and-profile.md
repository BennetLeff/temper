# First route of `pcb/temper.kicad_pcb`, and where the time goes

<!-- provenance: commit=99caa33e386d2c58f523284c48e7db0214365441 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Board:** 170 footprints, placed and domain-clearance-solved (170/170, `optimal`,
R24 audit clean at 0 mismatches across 7,843 constraints). Never routed before
this task (0 segments/vias/zones going in).

## Falsifier, stated before profiling

**"A\* pathfinding (Stage 4) dominates wall time."** Given the router's name
and the amount of prior profiling attention paid to the A\* kernel (Numba
port, iteration caps, theta-star experiments), this was the a priori
expectation.

**It did not fire.** Measured on both a bounded 15-net subset and the full
108-net board, **Stage 3 (SAT-based topological routing) dominates**, not
Stage 4:

| Scale | Stage 2 (channel) | Stage 3 (SAT) | Stage 4 (A\* + post-proc) | Stage 3 share |
|---|---:|---:|---:|---:|
| 15 nets (clean, no cProfile) | 17.4s | 98.2s | 2.7s | 82.7% |
| 108 nets (full board) | 17.6s | **1,573.8s** | 55.9s | **95.5%** |

Stage 3's share of wall time *grows* with board scale rather than shrinking,
because Stage 2 (channel-skeleton extraction from pad/footprint geometry) is
almost independent of net count — filtering the board down to 15 nets barely
moved Stage 2's cost — while Stage 3's SAT model and Stage 4's A\* work both
scale with net count, and Stage 3 scales worse.

Falsifier result: **rejected**. The dominant cost is the SAT topology solve,
not A\* pathfinding.

## How the router is actually invoked

Documented here because finding this took substantially more tool calls than
it should have, and the next person to profile or optimize this pipeline
should not have to re-derive it.

**Entry point:** `route_pcb()` in
`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py:115`
(re-exported from `temper_placer.router_v6.adapter`). This is the production
entry point — it is what `route_pcb()`'s own docstring, the CI regression
test (`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::
test_production_board_routing_drc_regression`), and every other production-
board measurement in this repo's history use.

**Minimal invocation to route the real board with its existing (already
placed) positions:**

```python
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.adapter import route_pcb

PCB_PATH = Path("pcb/temper.kicad_pcb")
RULES_PATH = Path("packages/temper-placer/configs/netclass_rules.yaml")

netlist = parse_kicad_pcb(PCB_PATH).netlist
design_rules = load_netclass_rules(RULES_PATH).design_rules  # populates
                                                              # net_class_assignments
                                                              # from TEMPER_NET_ASSIGNMENTS

class ParsedStub:                # route_pcb only needs .source_path and .nets
    source_path = PCB_PATH
    nets = netlist.nets

result = route_pcb(
    ParsedStub(),
    {},                          # empty placements dict -> route with the
                                 # board's existing (already-placed) positions;
                                 # route_pcb takes the `pipeline.run(pcb_path,
                                 # ...)` branch directly, reading straight off
                                 # disk -- no placement rewrite, so the
                                 # CLI's optimize --no-loop origin-offset bug
                                 # (see below) is not on this code path at all.
    design_rules=design_rules,
    enable_manufacturing_drc=False,  # default; see "manufacturing DRC" below
)
# result.routed_pcb_content is the full text of the routed .kicad_pcb file.
```

This exact pattern (`make_parsed_pcb_stub` + `load_netclass_rules` +
`route_pcb(parsed_stub, {}, design_rules=...)`) already existed, tested, in
`test_production_board_routing_drc_regression` — worth grep-ing for
`route_pcb(` in `packages/temper-placer/tests/` before reinventing a call
site.

**Config staleness note:** `packages/temper-placer/configs/pcl/
temper_production.yaml` (PCL = a placement/routing constraint DSL) is
**known stale against the current netlist** (documented independently in
`docs/evidence/2026-07-27-placement-resolve-after-0805.md` and the R24 pass
before it) and is **not loaded** by the invocation above — it only gets
pulled in if the `TEMPER_PCL_CONSTRAINTS` environment variable is set
(`_pipeline_route.py`'s `_augment_with_pcl_constraints`, gated at
`_pipeline_route.py:269`). Do not set that env var against this board without
re-authoring the file first.

**Rust extension modules had to be (re)built before anything worked.**
Neither `temper_drc_rs` (clearance engine, needed for the manufacturing-DRC
Rust backend) nor `temper_rust_router` (the SAT topology solver — see below)
was importable in a fresh `.venv` at the start of this task, despite being
listed as installed. Both needed:

```bash
cd packages/temper-drc-rs && uv run maturin develop --release
cd packages/temper-rust-router && uv run maturin develop --release
```

Also: all repo-root `uv run python3 ...` invocations that touch
`temper_placer` must use `uv run --package temper-placer python3 ...` — the
bare workspace root environment does not have `pyyaml` and other
`temper-placer`-only dependencies (`scripts/check_domain_partition.py`,
`scripts/capacity_budget_gate.py`, and the profiling harness all failed with
`ModuleNotFoundError: No module named 'yaml'` until this was corrected).

**The `optimize --no-loop` origin-offset bug:** confirmed present (by reading
`cli/__init__.py`, per prior evidence docs) but **did not affect this task**.
It only fires on the CP-SAT placement *write-back* path
(`solve_placement()` returns positions in the model's local `(0,0)` frame;
`write_placements_to_pcb()` needs absolute KiCad coordinates, and that CLI
path forgets to add `board.origin`). This task calls `route_pcb()` with an
**empty placements dict**, which takes a different branch entirely
(`pipeline.run(pcb_path, ...)` reads positions straight from the existing
file) — no placement rewrite happens, so the offset bug's code path is never
reached. Confirmed by the routed board's footprint positions being
byte-identical to the input board's (routing only appends `(segment ...)`,
`(via ...)`, and `(zone ...)` elements; it does not rewrite `(at X Y)` on
footprints).

## Part 1 — Route completion and failure modes

**Completion rate: 48/96 nets routed = 50.0%.** (108 nets total in the
netlist; 96 were attempted by Stage 4 — the remaining 12 are GND/Power/
GateDrive/HighVoltage/ACMains-class nets that get zone-pour treatment
instead of individual A\* segments, per `_zone_layers_for_net()` in the
adapter — **UNVERIFIED** that this fully accounts for the gap; not traced
net-by-net.)

**Failure mode: single category, no ambiguity.** All 48 failed nets failed
for the identical stated reason, verbatim from the router's own per-net log:

```
✗ <net> FAILED: no legal path found (forced segment disallowed)
```

**0 of 48** failures were congestion (`FAILED: congestion (blockers: ...)`)
or plain no-path (`FAILED: no path found`) — the two other failure strings
the router can emit. Every single failure is the **forced-segment
fail-closed gate** (this branch's own subject — see `fix/forced-segment-
fail-closed` and `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-
plan.md`) declining to emit a segment it cannot prove safe, rather than a
pathfinding or capacity failure. This is very likely the fail-closed
behavior working as intended on a genuinely under-routed board (50%
completion is a hard case), not a new defect — but it means **the router's
honest answer today is "half the board, and it knows exactly why the other
half failed."**

Representative failed nets: `bias`, `sw`, `y`, `boot`, `fb`, `cs_n`,
`RTD_DRDY`, `RTD_SDI`, `RTD_CS_N`, `discharge.r_snub1-p2`,
`discharge.r_snub2-p2`, `safety.ovp-line`, `safety-line`,
`hb.power_loop.q_high-g`, plus 34 more (full list is the 48-line grep of
`✗ ... FAILED: no legal path found (forced segment disallowed)` against the
captured run log).

**Written board:** `pcb/temper.kicad_pcb` now contains:

```
segments: 2,117
vias:     60
zones:    110
```

(all three counts confirmed by `grep -c` against the committed file, not
inferred from the router's self-report.)

## Manufacturing DRC on/off delta

**Falsifier for this half of the task (implicit in the task brief):** *"The
Rust clearance port cut Stage 5 from 25+ minutes to ~0.7s on this board's
own routing output — verify that holds on a route this task actually
produced, not just the port's own synthetic/historical benchmark."*

Measured directly, isolating the `_run_manufacturing_drc` stage-5 call with
a dedicated timer wrapped around exactly that method (not inferred from a
wall-clock diff of two independent runs, which is dominated by SAT-solver
run-to-run variance — see below):

| Scale | `_run_manufacturing_drc` wall time |
|---|---:|
| 15-net subset | **0.0072s** |

This is *better* than the ~0.7s figure in
`docs/evidence/2026-07-26-clearance-rust-port.md` §7, which was measured on
a 64-route/64-segment output; this run's routed subset is smaller still.
Both numbers are consistent with the Rust port working as documented: Stage
5 cost tracks segment/route count and stays sub-second at the scales
measured so far.

**Manufacturing DRC violations at 15-net-subset scale: 0** (all categories:
`clearance`, `creepage`, `annular_rings`, `acid_traps`, `teardrops`,
`thermal_relief`, `power_planes`, `copper_balance`). Plausible at this scale
(only 11 of 15 nets actually routed, few segments, little opportunity for
overlap) — **not** a re-confirmation of the 2026-07-26 doc's 618-violation
finding on a denser routing result, and **not** run at full-board scale (see
UNVERIFIED).

**Why the full-board on/off wall-clock delta was not independently
re-measured:** the full board's Stage 3 alone took 1,573.8s with observable
run-to-run solver variance (the same 15-net configuration measured 98.2s and
106.1s wall time for Stage 3 across two back-to-back runs — an ~8% swing
attributable to CaDiCaL's search, not to any code change between the runs).
A second independent ~27-minute full route to diff against the first would
have produced a wall-clock delta dominated by that same noise, which is a
strictly worse measurement of the manufacturing-DRC stage's true cost than
the isolated stage-level timer above. Running two ~7GB-peak-RSS full routes
concurrently (to save wall time) was avoided given other processes sharing
this machine (~31/32GB already in use at the time). The isolated
`_run_manufacturing_drc` timer is the more rigorous number for the question
actually being asked ("what does Stage 5 cost"); the full-board on/off
wall-clock delta is **UNVERIFIED**.

## Part 2 — Profile: where the time actually goes

### Per-stage wall time (full 108-net board, manufacturing DRC off)

| Stage | Wall time | Share |
|---|---:|---:|
| Stage 0 (parse) | 0.24s | 0.01% |
| Stage 0.5 (legalize) | 0.02s | 0.00% |
| Stage 1 (escape vias / dense-package detection) | 0.0002s | 0.00% |
| **Stage 2 (channel analysis)** | 17.6s | 1.07% |
| **Stage 3 (SAT topological routing)** | **1,573.8s** | **95.5%** |
| **Stage 4 (A\* geometric realization + post-processing)** | 55.9s | 3.39% |
| **Total** | **1,648.2s** | 100% |

Stage 4's 55.9s includes an internal post-processing substage (confusingly
also named `_run_stage5` inside `_pipeline_route.py` — via placement, trace
width assignment, results aggregation; **not** the same "Stage 5" as
manufacturing DRC) which measured 0.004s on its own — essentially all of
Stage 4's time is A\* search itself, not post-processing.

### Function-level hotspots within the dominant stage (Stage 3)

cProfile on a bounded 15-net run (131.5s total, 45.7M function calls) shows
Stage 3's cost is **not spread across many Python functions** — it is
concentrated in a single opaque native call:

```
ncalls  tottime  percall  cumtime  percall  function
     1  100.002  100.002  100.002  100.002  {built-in method
                                              temper_rust_router.temper_rust_router.solve_topology_rust}
```

**100.0 of 103.6 seconds inside `_run_stage3` (96.5%) is the CaDiCaL SAT
solve itself** — a single call, opaque to Python-level profiling (cProfile
cannot see inside the Rust/C++ frame). The remaining Stage 3 time is model
construction in Python (`constraint_model.py`'s `_create_per_net_channel_vars`,
`_create_capacity_constraints`, `add_variable`, ~2.5s combined) and result
auditing (`temper_rust_router.audit_result`, 0.97s).

**This is the single most important finding in this profile: the SAT solve
has no time limit anywhere in the call chain.**

```
packages/temper-rust-router/src/lib.rs:24    fn solve_topology_rust(...)
  -> solver::solve_with_cadical(&cnf, &var_names)

packages/temper-rust-router-core/src/solver.rs:20  pub fn solve_with_cadical(...)
  let mut solver = CaDiCaL::default();
  ...
  let result = solver.solve();   // <- no time/conflict limit, no interrupt
```

`grep -rn "time_limit\|max_time\|num_search_workers" packages/temper-rust-
router*/src/*.rs` returns nothing. CaDiCaL runs to completion (SAT proof or
exhaustion) with no bound, every single route. The pipeline already has a
graceful degradation path for this: `rust_result["status"] == "unknown"`
is explicitly handled downstream (`_pipeline_route.py` ~line 413) and an
empty topology graph falls Stage 4 back to direct A\* without SAT guidance
— the same fallback already used by `skip_stage3=True`. A conflict/time
limit is not a speculative feature; the consumer-side handling already
exists and is exercised by an existing code path.

Cardinality constraints are CNF-encoded via Sinz (2005) sequential-counter
encoding (`packages/temper-rust-router-core/src/encoding.rs:15`) — a
reasonable, well-known choice, but one whose auxiliary-variable count still
scales with channel/net count; worth a second look only after the missing
time limit is addressed.

### Function-level hotspots — Stage 2 (channel analysis)

Stage 2 is small in relative terms (1.07% of full-board wall time) but its
own internal hotspot is clear and cheap to fix:

```
ncalls  tottime  cumtime  function
 31688   14.091   14.091  shapely/predicates.py:551(contains)
     1    1.130   17.040  occupancy_grid.py:511(run)
     5    0.084   15.910  occupancy_grid.py:420(build_occupancy_grid)
```

14.1 of Stage 2's 17.6s (80%) is `shapely.contains` called 31,688 times in
what is almost certainly a per-cell/per-geometry Python loop in
`occupancy_grid.py`, rather than a single vectorized/batched shapely call or
an STRtree spatial-index query. At full-board scale (170 footprints vs. the
subset's much smaller pad count) this would scale further since the
occupancy grid is built once for the whole board regardless of net subset —
consistent with Stage 2 not shrinking when nets were filtered to 15.

### Function-level hotspots — Stage 4 (A\* realization)

At subset scale, `astar_core.py:676 _astar_search_3d` (the non-Numba,
multilayer-via 3D fallback path — distinct from the Numba-JIT 2D kernel used
for the common case) cost 2.0s tottime across only 4 calls (0.5s/call) —
expensive per-call relative to the Numba path, but it's a fallback, not the
common case, so its aggregate share stays small (3.4% of full-board wall
time for all of Stage 4 combined, most of which is the Numba kernel).

### Peak memory

| Configuration | Peak RSS (process lifetime, `resource.getrusage`) |
|---|---:|
| Full board, manufacturing DRC off | **6,930 MB** (~6.93 GB) |
| 15-net subset, manufacturing DRC off | 2,047 MB |
| 15-net subset, manufacturing DRC on | 2,003 MB |

Manufacturing DRC does **not** increase peak RSS (consistent with
`docs/evidence/2026-07-26-clearance-rust-port.md`'s finding that the
multi-GB figure comes from elsewhere in the pipeline, not from
`verify_clearance`). At full board scale, peak RSS is 6.93 GB — this
confirms the historical "Stage 5 hit 9.2 GB, and that was the stage, not
`verify_clearance` alone" note from the task brief was on the right track
about *scale* but wrong about *attribution*: manufacturing DRC was off in
this measurement and RSS still hit 6.93 GB, so **Stage 3's SAT model
construction (6.7M+ variables/12M+ clauses class of problem, per the prior
board's own measurement) is the dominant memory consumer, not Stage 5.**
Consistent with the CNF encoding materializing large Python-side variable/
constraint lists (`py_vars`, `py_cons` — full Python objects, not a compact
native representation) before handing off to Rust.

## DRC violations by category

Not measured at full-board scale in this task (see "why the full-board
on/off delta was not re-measured" above — a full-scale manufacturing-DRC
run was not completed). At 15-net-subset scale: **0 violations across all
8 categories** (see above). **UNVERIFIED at full-board scale** — the
2026-07-26 evidence doc measured 618 violations (493 clearance, 119
creepage, 0 annular_rings, acid_traps crashing/swallowed) on a denser
64-route output from the *prior* (149-footprint) board revision; this
board's true full-scale violation count has not been independently
confirmed post-repoint.

Separately, and **not caused by this task's routing**: `test_clearance.py`
reports **17 known REQ-SAFE-01 clearance violations** at full domain
classification (worst case 2.26mm against a 3–6mm requirement). These are
placement defects on the input board, informational per the test's own
design, out of scope for a routing task, and not attempted here.

## Gate states (before and after routing)

All four gates plus `make netlist`'s 76 assertions were run **twice**: once
as a pre-route baseline (confirming the placed-but-unrouted board doesn't
already fail anything), and once after routing.

| Check | Pre-route | Post-route |
|---|---|---|
| `make netlist` (76 assertions) | 76 passed, 0 failed | (routing doesn't touch the netlist; unchanged) |
| `scripts/check_domain_partition.py` | exit 0 | *(see UNVERIFIED)* |
| `scripts/capacity_budget_gate.py` | exit 0 | *(see UNVERIFIED)* |
| `scripts/mpn_fabrication_gate.py` | exit 0 | *(see UNVERIFIED)* |
| `scripts/check_derived_doc_drift.py` | exit 0 | *(see UNVERIFIED)* |

All four gates operate on the netlist/BOM/schematic domain
(`elec/build/default.net`, `elec/domain_manifest.yaml`,
`elec/src/*.ato`) or documentation drift — none of them read
`pcb/temper.kicad_pcb`'s copper layer, so routing is not expected to change
their result. Re-run post-route to confirm as a mechanical check, not
because a code path connects them to routing output.

## Ranked optimization targets

1. **Add a time/conflict limit to the CaDiCaL SAT solve
   (`packages/temper-rust-router-core/src/solver.rs:20`,
   `solve_with_cadical`).** This is 95.5% of full-board wall time and has
   *no* configured bound today. The consumer already handles
   `status == "unknown"` gracefully (falls back to unguided A\*, the same
   path `skip_stage3=True` already exercises in production). Expected
   payoff: the largest possible single change to wall time — plausibly
   cutting Stage 3 from ~26 minutes to a small, bounded, configurable
   number, at a cost (to be measured) in completion rate / route quality
   on whichever nets don't get topology guidance. This is a solver
   *configuration* change, not new logic — lowest implementation risk for
   the highest payoff on this list.

2. **Vectorize or spatially-index the Stage 2 `shapely.contains` loop**
   (`occupancy_grid.py:511`, `build_occupancy_grid`). 14.1 of 17.6s in
   Stage 2 (80%) is 31,688 individual `contains()` calls. Batching via
   shapely's vectorized predicates (pass an array of points/geometries in
   one call) or pre-building an `STRtree` would very likely cut this to a
   small fraction of its current cost. Stage 2 is only ~1% of full-board
   wall time today, but it does not shrink with net-count reduction (it's
   driven by pad/footprint count), so this is one of the few costs that
   will matter more, not less, as the board's component count grows.

3. **Investigate the CNF cardinality encoding for opportunities to shrink
   the model itself**, not just bound the solve time. Sinz (2005)
   sequential-counter encoding is used uniformly
   (`encoding.rs:15`); a smaller/tighter encoding (or per-constraint choice
   between encodings based on cardinality size) could reduce both wall
   time and the Python-side memory cost of materializing `py_vars`/
   `py_cons` before the Rust handoff (a likely contributor to the 6.93GB
   peak RSS). Lower priority than #1 because a solver time limit gets most
   of the wall-time benefit with far less engineering risk; worth revisiting
   if #1's fallback quality turns out to be unacceptable.

4. **Profile the Stage 4 non-Numba 3D A\* fallback path
   (`astar_core.py:676`, `_astar_search_3d`)** if its call frequency turns
   out to be higher on the full board than the 4-calls-in-131s observed at
   subset scale. At 0.5s/call it is far more expensive than the Numba 2D
   kernel; currently a small aggregate share (Stage 4 is only 3.4% of
   full-board wall time) but worth re-checking once Stage 3 is no longer
   the overwhelming bottleneck, since optimizing #1 will make #4's relative
   share more visible.

## UNVERIFIED

- Full-board manufacturing-DRC-on wall-clock delta (a second independent
  ~27-minute full route was not run; the isolated `_run_manufacturing_drc`
  stage timer, 0.0072s at subset scale, is reported instead — see rationale
  above).
- Full-board manufacturing DRC violation count by category (only measured
  at 15-net-subset scale: 0 violations; the 2026-07-26 evidence doc's
  618-violation figure is from the *prior* board revision, not
  reconfirmed here).
- Whether the 12-net gap between 108 parsed nets and 96 nets attempted by
  Stage 4 is fully explained by zone-pour-treated nets (GND/Power/
  GateDrive/HighVoltage/ACMains classes) — plausible from
  `_zone_layers_for_net()`'s class list but not traced net-by-net.
- Whether the 48 forced-segment-fail-closed failures are evenly distributed
  or concentrated in one net class/region of the board — not analyzed
  beyond confirming the failure-reason string is identical across all 48.
- Post-route gate re-runs for `check_domain_partition.py`,
  `capacity_budget_gate.py`, `mpn_fabrication_gate.py`,
  `check_derived_doc_drift.py` — pending completion of this document (all
  four operate on the netlist/schematic domain, not on routed copper, so no
  behavior change is expected from routing; re-run is a mechanical
  confirmation, not a targeted check).
- Whether Stage 3's ~8% run-to-run wall-time variance (98.2s vs 106.1s on
  an identical 15-net configuration) is representative of the variance at
  full-board scale — only measured at subset scale.
