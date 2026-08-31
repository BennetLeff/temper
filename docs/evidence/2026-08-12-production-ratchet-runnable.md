<!-- provenance: commit=c47761757de8f62dc307c3bb79d1180ebe412ef3 dirty=UNKNOWN -->
/home/bennet/Desktop/temper-worktrees/production-ratchet-runnable, branch
fix/production-ratchet-runnable, base b33056c95 (= origin/main tip at task
start). Own .venv (make venv-isolate, 10/10 pyo3 extensions fresh, venv
identity verified with scripts/check_venv_integrity.py -- 0 violations).
pumpkin_engine identity gate VERIFIED (sha256 7ff153f4..., source_commit
5bbf650d4). kicad-cli 10.0.5 via the repo's PATH shim. pcb/temper.kicad_pcb
UNTOUCHED throughout (`git status --short pcb/` empty; sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- the same
digest docs/evidence/2026-08-12-board-recipe-reproducibility.md's provenance
block cites, confirming this is the same committed board state that document
measured). The one write under pcb/ is pcb/temper.kicad_dru,
.gitignore'd and regenerated fresh by `scripts/generate_kicad_dru.py`, the
same convention every prior evidence doc in this lineage follows. -->

# The production ratchet test is now runnable: net-batching, not monolithic, 3.9 GB peak RSS not 58.9 GB, and the first real verdict on the committed board's `shorting_items`/`unconnected_items`

**Verdict up front.**
`test_production_board_routing_drc_regression` called `route_pcb()` with
every net-batching kwarg at its default (`False`) -- the monolithic Stage-3
path. On this board that path OOMs (measured elsewhere today: 8.8 -> 17.9
-> 37.7 -> 58.9 GB RSS, then `oom_reaper` SIGKILL; not re-run here per this
task's own instruction not to relaunch a run that already OOMs). **Production
does not ship that path.** The documented recipe that actually produces a
board (`docs/evidence/2026-08-12-board-recipe-reproducibility.md` §1,
already on `main`) is reconcile -> Pumpkin placement -> `scripts/
route_board.py --net-batching`, and `docs/plans/2026-08-12-003-fix-sat-
capacity-encoding-plan.md` independently establishes that net-batching and
monolithic are different algorithms at the Stage-3 SAT level, not two
routes to the same board. Switching this test to `enable_net_batching=True,
net_batch_size=net_batching.DEFAULT_BATCH_SIZE` therefore does not weaken
what it guards -- it points the guard at the path that ships, for the first
time makes the gate completable, and the resulting run peaked at **3.92 GB
RSS**, comfortably inside this machine's headroom.

The test **ran to a real, measured verdict**: `shorting_items` (115, N=5,
zero scatter) and `unconnected_items` (427) both clear the existing
178/463 bars; the test's separate `total` DRC-violation-count assertion
does **not** (1621 > 1514) -- reported honestly below, not hidden or
worked around.

## 1. What changed

`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`,
`test_production_board_routing_drc_regression`: the `route_pcb(...)` call
now passes

```python
enable_net_batching=True,
net_batch_size=DEFAULT_BATCH_SIZE,   # from temper_placer.router_v6.net_batching, = 10
```

Nothing else about the test changed -- same board (`pcb/temper.kicad_pcb`,
untouched), same rules, same `_drc_median(..., runs=PRODUCTION_DRC_SAMPLE_
RUNS)` (N=5) sampling protocol, same three assertions (`shorting_items`,
`unconnected_items`, `total`), same threshold constants
(`PRODUCTION_ROUTER_OUTPUT_SHORTING_ITEMS=178`, `_UNCONNECTED=463`,
`_TOTAL_DVIOLATIONS=1514`) -- **none of the three threshold constants were
edited**, per this task's explicit instruction not to silently re-baseline
a ratchet. The test's docstring and each assertion's failure message were
extended (not shortened) to say explicitly that those three constants were
seeded against the *monolithic* path and have not been re-derived for
net-batching's output -- so a future reader hitting a red `total` assertion
is told why, instead of being invited to "just raise the number."

## 2. Which path production actually uses -- the reasoning, not just the conclusion

Two independent pieces of evidence, both already on `main` before this
task started, agree:

1. **`docs/evidence/2026-08-12-board-recipe-reproducibility.md` §1, §4, §6**
   measured the documented recipe end-to-end, twice, with byte-for-byte
   determinism proof (sha256/empty-diff across independent process trees
   under concurrent CPU load): `scripts/resync_pcb_netlist.py` -> Pumpkin
   CP-SAT placement -> **`scripts/route_board.py --net-batching`**. Every
   headline number in that document (168 footprints, 3,349 segments, 56
   vias, 70 zones, 80/105 nets routed, `shorting_items` 91) was produced
   with `--net-batching` set. The monolithic path does not appear anywhere
   in that document's own recipe.
2. **`docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md`**
   independently measured (its own §"Goal Capsule", live instrumented run)
   that at `net_batching.DEFAULT_BATCH_SIZE = 10` the Stage-3 `AtMostK`
   capacity guard never fires (mean K ~ 17.3-17.5 > 10), so under
   net-batching, channel capacity is enforced by neither the SAT encoding
   nor the cross-batch greedy bookkeeping (measured receiving zero data)
   -- Stage 4's occupancy-grid A* is the whole story. This is **not** true
   of the monolithic path, where capacity genuinely is encoded into the
   CNF (the same plan cites `docs/evidence/2026-07-27-stage3-model-and-
   rewrite.md` for the monolithic case). That is a real, structural
   difference in what gets solved, not a flag that only changes
   scheduling.

Both documents converge on the same fact from different directions: what
ships is net-batching, and net-batching is a different algorithm from
monolithic, not an equivalent re-partitioning of the same one. A ratchet
that only the monolithic path can run therefore guards an artefact nobody
produces. `scripts/route_board.py`'s own bare default is also
`enable_net_batching=False` (matching this test's prior default) -- but
that default is for the *driver*, invoked without `--net-batching`; the
*recipe* that is actually run always adds the flag. The distinction that
matters is the recipe, not the driver's unset default.

## 3. The run: 3.92 GB peak RSS, not 58.9 GB

Command:

```
cd packages/temper-placer
.venv/bin/python -m pytest \
  tests/placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression \
  -s -v --tb=long
```

wrapped in a peak-RSS monitor that sums `psutil` RSS over the full process
tree (pytest + every net-batching subprocess batch) every 5 seconds for
the whole run.

| metric | value |
|---|---:|
| peak RSS (process tree, 5 s samples) | **3.924 GB** (at t=115.3 s) |
| wall time | 390.9 s (6 min 31 s) |
| exit | 1 (FAILED -- see §4; not an infra failure) |
| net-batching summary | 11 batches, 11 solved at batch level, 0 crashed, 0 timed out |
| router completion signal | `completion_rate=0.0680`, `unrouted=96` |

RSS never approached even 4 GB, let alone this machine's ~56 GB available
headroom or the 58.9 GB the monolithic path was measured at elsewhere
today. The RSS curve stayed in a 1-4 GB band across all 79 samples taken
over the run's 391 s -- a rise-and-fall pattern consistent with each of the
11 net-batching subprocess batches peaking independently and releasing
memory on exit, not a monotonically climbing leak. No memory-related risk
was found; the fix here is algorithmic (which path runs), not a memory
optimization of either path.

**On `completion_rate=0.068`**: this is expected, not a regression signal.
This call (like the test's prior monolithic-path call) does not strip the
board's existing committed copper first -- unlike `route_board.py`'s own
`route_once`, which strips by default. `route_pcb()` therefore "appends to
existing copper" (the test's own long-standing docstring language,
unchanged by this task): most of the board's 110 nets already have
committed traces from `pcb/temper.kicad_pcb`'s own copper, so only a small
residual fraction have anything left to route through the Stage 3/4
pipeline. `docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s own
76.2% completion figure is a different measurement entirely -- one where
the recipe first stripped copper and routed the board from scratch. The
two completion rates are not comparable, and neither was expected to be;
noted here only so `0.068` is not misread as a routing failure.

## 4. The verdict: `shorting_items`/`unconnected_items` on the committed board, N=5

DRC sampling protocol matches the file's own established convention
exactly (`PRODUCTION_DRC_SAMPLE_RUNS = 5`, ambient-threaded kicad-cli, no
extra pinning added or removed by this task):

| metric | this run (N=5) | existing threshold | verdict |
|---|---:|---:|---|
| `shorting_items` | **115** (samples: 115, 115, 115, 115, 115 -- zero scatter) | <= 178 | **PASS**, 63 of margin |
| `unconnected_items` | **427** (median; see caveat below) | <= 463 | **PASS**, 36 of margin |
| `total` DRC violations | **1621** (samples: 1621 x5 -- zero scatter) | <= 1514 | **FAIL**, exceeds by 107 |

**Caveat on `unconnected_items`'s scatter, stated precisely rather than
assumed**: `_drc_median()` returns only the reduced median for
`unconnected`, not the per-run list (unlike `shorting_items` and `total`,
whose per-run lists this test's own assertion messages print). The
`total` and `shorting_items` per-run lists were both **exactly identical
across all 5 samples** (`[1621]*5`, `[115]*5`) -- since `total` is the sum
over every category including `unconnected_items` in the same JSON
payload, 5 bit-identical totals over 5 separately-invoked `kicad-cli`
processes is strong indirect evidence `unconnected_items` was equally
stable, but this is inference from the total, not a value this task
independently re-verified against the raw per-run list. Recorded as such,
not rounded up to "confirmed."

**These are `kicad-cli`'s `unconnected_items` DRC-oracle count, not the
router's own `pad_connectivity_audit` "fully pad-connected nets" metric**
(the primary metric `scripts/route_board.py --runs` reports separately --
see its module docstring). This task measured and reports the former only,
matching exactly what the two existing threshold constants
(`PRODUCTION_ROUTER_OUTPUT_UNCONNECTED`) already gate on; it did not run
`audit_pad_connectivity` against this run's output, and does not claim a
pad-connectivity figure here.

**Full DRC breakdown, this run (last of the 5 samples, identical to the
other 4 by the `total` invariance above):**

```
annular_width=4  clearance=267  copper_edge_clearance=14  courtyards_overlap=11
creepage=206  drill_out_of_range=4  hole_clearance=7  hole_to_hole=3
lib_footprint_issues=169  missing_courtyard=5  pth_inside_courtyard=1
shorting_items=115  silk_edge_clearance=1  silk_over_copper=172
silk_overlap=199  solder_mask_bridge=154  track_dangling=49  track_width=199
tracks_crossing=5  via_dangling=32  via_diameter=4
```

## 5. Do the existing 178/463 bars still apply? Explicit answer, not a silent edit

**Yes, in the narrow sense that both measured values fall under them** --
115 <= 178 and 427 <= 463, both with real margin (63 and 36 respectively).
The test **passes** its `shorting_items` and `unconnected_items`
assertions today, for the first time this path has ever produced a
measurement to check them against.

**No, in the sense the task asks about**: those two constants were seeded
entirely against the monolithic path (every dated re-measurement in this
file's own provenance block above them -- 2026-07-29 through 2026-08-04 --
ran `route_pcb()` at its net-batching-disabled default). Net-batching is a
demonstrably different algorithm (§2) producing a different completion
rate (0.068 here vs. the monolithic baseline's own differently-obtained
figures) and different copper. That the net-batching numbers happen to
clear the monolithic-seeded bars is not proof the bars are *calibrated*
for net-batching -- it is one data point that they are not obviously too
tight. **This task does not re-baseline `PRODUCTION_ROUTER_OUTPUT_
SHORTING_ITEMS`/`_UNCONNECTED` to net-batching-derived numbers, and did
not touch either constant.** Doing that properly needs this file's own
established protocol for a re-seed -- multiple independent measurement
epochs, N>=5 (ideally N>=11, matching the original Category B seeding) runs
with median/range, and a dated provenance paragraph -- which is future
work, not something to fold into the fix that makes the test runnable at
all.

**`PRODUCTION_ROUTER_OUTPUT_TOTAL_DVIOLATIONS = 1514` is a different
story: it does NOT hold** (1621 measured). This constant was never named
in this task's brief (which asks specifically about `shorting_items`/
`unconnected_items`), and it is **left unchanged and red** here for the
same reason the other two are left unchanged: this task's job is to make
the test runnable and report what it finds, not to make it pass by
weakening or silently re-baselining a threshold. The `total` failure is a
real, reportable outcome of switching to the algorithm that ships --
whether it represents a genuine capability gap in net-batching's output
(lib_footprint_issues, track_width, and silk categories dominate the
count, none of them safety-critical shorts) or simply a threshold that was
never calibrated for this artefact is exactly the kind of question the
re-baseline protocol above exists to answer, and is out of this task's
scope.

## 6. Rules-compliance notes

- `pcb/temper.kicad_pcb` untouched throughout: `git status --short pcb/`
  empty before, during, and after; sha256 unchanged and matches the
  digest already on record in
  `docs/evidence/2026-08-12-board-recipe-reproducibility.md`.
- `drc_ceiling.json` (`power_pcb_dataset/drc_ceiling.json`) not read,
  referenced, or modified -- it gates the corpus board, a different
  artefact from the production board this task measures.
- `scripts/verify_pumpkin_engine.py` exited 0 before this task ran any
  solve-adjacent code (the production routing test itself does not solve
  placement, but the gate was still run first per protocol).
- No `<<<<<<< ` conflict markers anywhere in the diff
  (`git grep -l "^<<<<<<< " -- '*.py' '*.rs' '*.yaml' '*.yml'` empty).
- Work done in an isolated worktree
  (`fix/production-ratchet-runnable`, branched from `origin/main`) with
  its own `.venv` (`make venv-isolate`), venv identity independently
  verified (`scripts/check_venv_integrity.py`, 0 violations) so this
  measurement is provably against this worktree's own code, not a stale
  or hijacked shared venv.
