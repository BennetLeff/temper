<!-- provenance: own worktree /home/bennet/Desktop/temper/.claude/worktrees/route-6layer-measurement,
branch measure/6layer-routing, based on origin/fix/layer-architecture-ssot @ eaef53cbf (PR #1178,
unmerged as of this writing). pcb/temper.kicad_pcb sha256
`1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d` verified byte-identical before
and after every measurement in this document -- confirmed again below. All routing output lives
under a scratch directory outside the
repo (/tmp/.../scratchpad/route6l/); nothing in this document required editing the board, a DRU
threshold, or a ratchet ceiling. -->

# 6-layer routing measurement: the stackup declaration does not change what the router routes

**Headline: 6-layer route = 53/139 nets fully pad-connected -- identical to the 2-layer baseline's
53/139, down to the exact same 46 fake-completion / 40 honest-gap split.** PR #1178 declared
`In3.Cu`/`In4.Cu` as signal layers, taking declared utilisation from 1.31 (infeasible) to 0.657
(comfortable). This measurement routed the board with that declaration in place and found the
router placed **zero** copper on either new layer: every one of 3331 segments, 26 vias, and 80
zones landed on `F.Cu`/`B.Cu` only. The 6-layer decision is real and correctly reasoned (Sec 1 of
`2026-08-13-layer-architecture-decision.md`), but nothing in the router's Stage-4 pathfinding path
consults it -- three independent hardcoded 2-layer constants sit between the declaration and the
router, and PR #1178's own new `board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS` accessor, built
specifically to catch this gap, was never widened to admit the new layers (Sec 3).

## 1. Method -- like-for-like with PR #1172's 53/139 figure

Same board, same command family, same metric:

```
uv run python3 scripts/route_board.py --output <scratch>/temper_routed_6layer.kicad_pcb \
    --net-batching --batch-size 10
```

`--pcb`/`--rules` left at default, which resolve relative to the script's own location -- this
worktree's `pcb/temper.kicad_pcb` (6-layer declaration confirmed present, Sec 2) and
`packages/temper-placer/configs/netclass_rules.yaml`. `route_once()` strips all committed
copper/zones first (a from-scratch route, comparable to PR #1172's own from-scratch measurement),
then calls `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file()` on the result -- the
same primary-metric call PR #1172 used to produce 53/139.

`pcb/temper.kicad_pcb` sha256 before routing:
`1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d`. After: identical (routing
wrote only to `--output`, never to the input path;
`route_board.py` itself refuses `--output == --pcb`). `git status --porcelain` clean throughout.

Environment: `make venv-isolate` (own `.venv`, unset `CONDA_PREFIX` first), all 10 pyo3/maturin
extensions rebuilt and independently import-verified (`temper-geometry` needed an explicit
`touch src/lib.rs` + rebuild -- the shared `target-shared` cache had picked up a build of that
crate from a concurrent worktree/session with the `python` pyo3 feature *not* enabled, so the
first `maturin develop` silently linked a `.so` with no `PyInit_temper_geometry` symbol; verified
fixed by direct `importlib.import_module` of all 10 extensions, not just the freshness gate).
`make netlist` run in this worktree (`elec/src` diffed byte-identical against the main checkout
first, but the build was already in flight and completed on its own -- 125193-byte
`elec/build/default.net`, digest `8cfd715e60a3...`).

## 2. Layer declaration confirmed present

```
(0 "F.Cu" signal)
(3 "In3.Cu" signal)
(1 "In1.Cu" power)
(2 "In2.Cu" power)
(4 "In4.Cu" signal)
(31 "B.Cu" signal)
```

`scripts/check_layer_utilization_gate.py`: declared signal layers `['F.Cu', 'In3.Cu', 'In4.Cu',
'B.Cu']`, demand 11236.6 mm^2, capacity 17092.0 mm^2 (4 x 4273.0 mm^2/layer), **utilisation
0.657**, gate PASSED. This matches the task brief's cited figure exactly and confirms the
*declaration* half of PR #1178 is live on this branch.

## 3. Result: identical connectivity, zero copper on the new layers

```
Result: 70/106 nets (66.0%)  segments=3331 vias=26 zones=80  wall=536.8s
[net-batching] 12 batch(es), 12 solved at batch level, 0 crashed (0 timed out, 0 crashed other)
Result (pad connectivity, PRIMARY metric): 53/139 nets fully pad-connected  fake-completion=46 honest-gap=40
```

| Metric (primary: pad-connectivity) | 2-layer baseline (PR #1172, reproduced) | 6-layer (this measurement) |
|---|---|---|
| Fully pad-connected | 53/139 | **53/139** |
| Fake-completion (copper exists, doesn't join all pads) | 46 | **46** |
| Honest gap (no copper at all) | 40 | **40** |

Not "close to" -- the same three integers. `net_batching` reported 0 crashes and 0 subprocess
timeouts, ruling out the run-to-run nondeterminism sources that document warns about; this is a
clean, comparable measurement.

**Copper-level confirmation the new layers were never touched** (grep of the routed output,
`(segment ...)`/`(via ...)`/`(zone ...)` blocks only):

```
segment layers:  1848 F.Cu, 1483 B.Cu           (3331 total -- 100%)
via layer-pairs:   13 F.Cu<->B.Cu (x2 directions) (26 total -- 100%)
zone layers:       40 F.Cu, 40 B.Cu             (80 total -- 100%)
mentions of "In3.Cu"/"In4.Cu" in the output: 4, all inside the inherited
  (layers ...) declaration and (stackup) thickness block -- zero inside
  any segment/via/zone
```

All 36 nets that reached Stage 4's A* and failed show the identical signature PR #1172 diagnosed
on the 2-layer board:

```
grep "FAILED" route_run.log | sed -E 's/^\s*✗ [^ ]+ FAILED: //' | sort | uniq -c
     36 no legal path found (forced segment disallowed)
```

36/36, no other failure shape -- not a timeout, not a batch crash, not a Stage-3 topology miss.
`forced_segment_count > 0`: A* found candidate paths, every one needed an illegal (clearance-
violating) segment, and the fail-closed policy correctly refused, exactly as PR #1172 established.
The remaining 4 of the 40 honest-gap nets are outside Stage 4 entirely (`_should_route()`-excluded
power/ground/HV nets relying on zone-pour delivery that didn't reach every pad) -- the same
"zone-pour delivery gap" PR #1172 flagged as reported-but-not-root-caused, unchanged here.

**Conclusion: the failure mode has not changed, because the channel the router actually searches
has not changed.** 6 declared signal layers, 2 used.

## 4. Root cause: three hardcoded 2-layer constants between the declaration and the router

`packages/temper-placer/src/temper_placer/core/board_layer_roles.py`, added by PR #1178 itself,
exists specifically to prevent this class of gap -- it distinguishes `signal_layer_names()` ("what
does the board declare") from `routable_signal_layers()` ("what can the router actually target",
the declaration intersected with `ENGINE_SUPPORTED_SIGNAL_LAYERS`). Its own docstring names
"widening the router's real capability" as "a one-line change" to that constant. That change was
never made:

```python
# board_layer_roles.py:137
ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED: tuple[str, ...] = ("F.Cu", "B.Cu")
```

So `routable_signal_layers()` on this branch's own board still returns `["F.Cu", "B.Cu"]` --
intersecting the declared 4-layer set with an unwidened 2-layer engine-capability set throws the
new layers away by construction. The plumbing this PR built to catch a future stackup edit
silently disagreeing with the router is itself the thing still disagreeing.

Worse: two of the three call sites that actually gate Stage 4 pathfinding don't even go through
that accessor -- they hardcode the pair directly, independently of `board_layer_roles` entirely:

- `packages/temper-placer/src/temper_placer/router_v6/grid_prep_stage.py:43` --
  `GridPrepStage.run()`, Stage 4.0, builds the occupancy grids A* searches:
  `for layer in ("F.Cu", "B.Cu"):` -- no board read, no declaration lookup. Its own validator
  (line 72) checks presence of exactly those two grids and nothing else, so a stackup edit
  can't even fail this stage loudly; it's structurally invisible to it.
- `packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py:156` --
  `preferred_order = ["F.Cu", "B.Cu"]`, the layer-preference ordering for the (spike) N-layer A*
  path.
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` -- `LAYER_TO_KICAD =
  {1: "F.Cu", 4: "B.Cu"}` and a `preferred_layer: str = "F.Cu"` default.
- `packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py` is the one call site
  that *does* route through `board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` (its own
  comment cites this explicitly as replacing a second hardcoded literal) -- but since the
  constant itself is unwidened, this correctly-wired call site still only ever emits zone pours
  on `F.Cu`/`B.Cu`.

**This is the finding the task brief asked to check for, confirmed at the code level and then
proven empirically by the route in Sec 3**: a 6-layer board declaration routed as if it were a
2-layer board, because `GridPrepStage` (the stage that actually allocates pathfinding capacity)
never reads the stackup at all, and the one accessor purpose-built to prevent silent disagreement
between declaration and engine capability was left holding its old value.

## 5. Clearance / courtyard measurement (uncapped, real DRU, this run's routed output)

Ran via `scripts/measure_uncapped_drc.py`'s own importable functions (`make_scratch_board`,
`run_kicad_drc`, `category_counts`, `measure_category_exhaustive`, `net_class_map`) against a
scratch copy of this run's routed board, with the project's real generated DRU
(`scripts/generate_kicad_dru.py generate_dru()`) applied -- not the bare kicad-cli default. Never
touched `pcb/temper.kicad_pcb`; scratch board lives under `--scratch-dir` outside the repo.

Raw kicad-cli DRC (real DRU, extended cap 499 for `clearance`/`unconnected_items`, 199 else):

| category | raw count | at/near cap? |
|---|---:|---|
| clearance | 499 | **yes (saturated)** |
| track_width | 199 | **yes (saturated)** |
| silk_overlap | 199 | **yes (saturated)** |
| creepage | 101 | no |
| hole_clearance | 58 | no |
| courtyards_overlap | **8** | no -- trusted as-is |
| (14 other categories) | ≤29 each | no |
| **total (raw, capped)** | **1393** | |

Exhaustive (uncapped, band-bisection) re-measure for the saturated DRU-governed categories:

| category | raw (capped) | **TRUE (uncapped)** |
|---|---:|---:|
| clearance | 499 | **811** |
| track_width | 199 | **523** |

`silk_overlap` is not DRU-governed (no `rule` attribution in kicad-cli's own JSON) and was left
at its raw capped count of 199 -- the task named clearance and courtyards_overlap specifically;
an exhaustive silk_overlap count would need the physical-partition path
(`measure_uncapped_drc.py physical-category`), not exercised here.

**courtyards_overlap = 8**, well under its 199 cap, so this raw count is already the true count --
no exhaustive re-measure needed.

These numbers describe *this run's* from-scratch 6-layer-declared-but-2-layer-executed route.
There is no directly comparable from-scratch 2-layer DRC baseline measured with this same
methodology in prior evidence (PR #1172's diagnosis is pad-connectivity/failure-attribution
focused, not a DRC violation count) -- reported here as this measurement's own number, not as a
delta, and not re-derived for the 2-layer case in this session to avoid re-routing a second full
board under time/disk constraints already tight from the fleet-wide 91%-full disk. Given Sec 3's
finding that the router used identically zero of the new layers, there is no structural reason to
expect the clearance picture to differ from a 2-layer-declared route of the same netlist -- but
that is an inference from the routing-behavior identity proven above, not an independent
measurement.

## 6. What this does and doesn't answer

**Answers**: whether declaring more signal layers, by itself, unblocks routing capacity on this
board. It does not -- not because the capacity math is wrong (Sec 1's 0.657 utilisation is real
arithmetic on real declared layers), but because the router's Stage-4 occupancy-grid construction
(`GridPrepStage`) and two of its three layer-selection call sites never read the stackup at all,
and the one call site that does read it (via `board_layer_roles`) reads a capability constant that
was never widened alongside the declaration.

**Does not answer**: whether widening `GridPrepStage`, `_astar_nlayer.py`'s preferred order, and
`channel_mapping.py`'s layer map to actually build occupancy grids and pathfind on `In3.Cu`/
`In4.Cu` would close the gap -- that is real Stage-2/Stage-4 infrastructure work (per-layer
occupancy grids, inter-layer via cost modeling, A* extended to a 4-layer search space), not a
one-line constant change, and out of scope for this measurement task.

## 7. Hard constraints honored

- [x] `pcb/temper.kicad_pcb` never modified -- sha256
  `1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d` identical before and after
  every measurement in this document
- [x] No clearance/creepage/DRU threshold or ratchet ceiling changed
- [x] No net reported as connected that isn't -- pad-connectivity audit is the reported primary
  metric throughout; the 46 fake-completion nets are reported as fake, not folded into the 53
- [x] `git status --porcelain` / `git grep -l "^<<<<<<< "` clean before this commit
- [x] `make venv-isolate`; `scripts/check_stale_extensions.py` 10/10 fresh AND all 10 extensions
  independently import-verified (not just the freshness gate -- see Sec 1 on the `temper-geometry`
  false-fresh case this caught)
- [x] `make netlist` run in this worktree
