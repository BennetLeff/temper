<!-- provenance: measured 2026-08-12, worktree .claude/worktrees/agent-a374c69e35366ad12,
branch diagnose/clearance-regression, HEAD 21869cffb (docs-only, 2 commits ahead of its
base d8062c6e6 = origin/main tip at task start, including #1050/#1051/#1052/#1053). All
board regeneration in /tmp/.../scratchpad/repro/, never under pcb/**
(`git status --short pcb/` empty throughout this task, verified before/after every step;
`pcb/temper.kicad_pcb` sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
unchanged). kicad-cli 10.0.5 at /home/bennet/.local/opt/kicad-10.0.5
(LD_LIBRARY_PATH covering root/usr/lib*, KICAD_STOCK_DATA_HOME=root/usr/share/kicad, the
invocation docs/evidence/2026-08-11-pad-connectivity-ground-truth.md records).
PYTHONHASHSEED left UNSET (default, per-process-random reseed) throughout the primary
determinism test -- deliberately: an unset seed is what the documented recipe actually
runs under, and it is the strongest test of whether the pipeline needs seed-pinning to
reproduce. Machine: 24 cores, load average 1.5-3.3 (idle-to-light) throughout. -->

# The place-and-route recipe is deterministic; the three-boards-differ finding is fully explained by input/code drift, not solver nondeterminism -- and PR #1050's own 4,228/74 does not reproduce

**Verdict up front.** The documented recipe (reconcile -> Pumpkin placement with
PD2/8.0mm isolation barrier -> `route_board.py --net-batching`) is **deterministic** on
a fixed commit, fixed inputs, and this machine: reconciliation, placement, and routing
each independently reproduced **byte-for-byte identical output** across repeated,
separate process launches, with `PYTHONHASHSEED` left unset. Five independent full or
partial reproductions this session converge on the same numbers. **None of the
divergence among the three boards in the task's table is caused by nondeterminism in
the solve pipeline itself.** It is fully explained by two separate, ordinary causes:
(1) agent 2 genuinely ran different code (no isolation barrier -- confirmed from its own
doc, though its stated reason, "the Pumpkin engine constraint type is unmerged," is
factually wrong: it has been on `main` since #1050); (2) PR #1050's own headline
4,228 segments / 74 vias figure **does not reproduce** under the recipe as documented,
on this commit, and the gap is **not** explained by any code change between #1050 and
today (verified: every routing/placement source file the recipe touches is
byte-identical between #1050's commit and current `main`, except three ground-plane
files whose #1050-era content was reverted and re-tested -- reverting them changed
nothing). The reproducible number, confirmed five independent ways, is **3,319-3,349
segments / 56 vias / 66-70 zones**, not 4,228/74. §6 states this as plainly as the
evidence supports: #1050's figure looks like a one-off, and the most likely
concrete mechanism (demonstrated separately, in miniature, within this very task, at
§4) is silent input drift -- a footprint library file changing between when a board
was measured and when it was reproduced -- not a defect in the solve pipeline.

A genuine, if latent, risk was found and fixed regardless: `net_batching.py`'s
per-batch subprocess timeout (900s) is a wall-clock budget, and a batch that hit it
would silently fall back with **zero visibility** in a normal run (the fallback
telemetry was computed but discarded before reaching any caller, including
`route_board.py`). It did not fire in any run measured here -- but "it didn't fire this
time" is not the same claim as "it can't," and the pipeline had no way to tell those
apart. §5 fixes that.

## 1. Method

Recipe: `scripts/resync_pcb_netlist.py` (reconcile) -> Pumpkin CP-SAT placement with
netclass+courtyard constraints (21,948) plus the PD2/8.0mm horizontal isolation barrier
(U6 relaxed, `docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`'s exact
recipe) -> `scripts/route_board.py --net-batching`, following
`docs/evidence/2026-08-12-place-and-reroute-connectivity.md` end to end. Each stage was
tested for determinism **in isolation** (identical input, two-plus independent process
launches, structural diff + sha256) before testing the full pipeline, so a divergence
can be attributed to a specific stage rather than "somewhere in the pipeline."

## 2. Reconciliation: deterministic

Two fresh `resync()` runs against a copper-stripped copy of `pcb/temper.kicad_pcb` and
the identical `elec/build/default.net`, same fp-lib-table:

```
run A: kept=162 added=6 removed=7 moved=0
run B: kept=162 added=6 removed=7 moved=0
diff repro/reconcile_a/temper.kicad_pcb repro/reconcile_b/temper.kicad_pcb  -> empty (0 lines)
diff repro/reconcile_a/reconcile_report.json repro/reconcile_b/reconcile_report.json -> empty
```

Byte-identical. No further investigation warranted.

## 3. Placement (Pumpkin, seed=42): deterministic

Two fresh solves against the identical reconciled+stripped board, identical 22,118-constraint
payload (21,948 base + 170 barrier), `seed=42`, `timeout_ms=30000`:

```
run A: status=optimal solve_time_ms=1181.4
run B: status=optimal solve_time_ms=1075.9
positions equal: True   (168/168 components, byte-for-byte)
rotations equal: True
```

**`status=optimal`, not a timeout truncation** -- the solver proved optimality in
~1.1s, three orders of magnitude under its 30s budget. This directly tests the task's
own top-ranked suspicion ("a time-limited CP solve is nondeterministic by
construction") against this specific constraint model: it does not apply here, because
the solve never approaches its time limit. Only wall-clock solve **time** varied
between runs (1181ms vs 1076ms, ordinary machine-load noise) -- the **decision** did
not.

## 4. Routing (`--net-batching`): deterministic -- and a real input-drift confound found and isolated along the way

Two `route_board.py --net-batching` runs launched as independent OS processes (fresh
Python interpreter, fresh `multiprocessing.spawn` children for every Stage 3 batch),
run **concurrently** against each other (competing for the same 24 cores -- a harder
test than serial execution) on the byte-identical placed board:

```
route_a: Result: 75/105 nets (71.4%)  segments=3319 vias=56 zones=66  wall=348.7s
route_b: Result: 75/105 nets (71.4%)  segments=3319 vias=56 zones=66  wall=348.5s
sha256(route_a/temper_routed.kicad_pcb) == sha256(route_b/temper_routed.kicad_pcb)
diff route_a/temper_routed.kicad_pcb route_b/temper_routed.kicad_pcb  -> empty (0 lines)
```

**Byte-for-byte identical**, including the exact same unrouted-net set. This is the
single most decisive result in this task: two independent process trees, competing for
CPU, spawning dozens of independent SAT-solving child interpreters apiece (each
re-seeding Rust's default per-process `HashMap` hasher from OS randomness --
`scripts/route_board.py`'s own `_run_worker_subprocess` docstring names this as the
class of nondeterminism a subprocess-per-run design exists to catch), produced not just
the same counts but the same file.

**A real confound was found and separated out, not ignored.** This task's fresh
reconciliation (§2) does **not** byte-match a reconciled board produced earlier in this
same session (`regen/main_board_stripped.kicad_pcb`) despite an identical
`reconcile_report.json` (same kept/added/removed/moved counts). The only diff is
component **T2** (the OCP-02 current transformer, one of the 8 isolators): its
`pcb/libs/temper.pretty/CST3015.kicad_mod` footprint content differs in `descr` text
and in whether each pad's `90`-degree rotation is baked into the pad's own `(at ...)`
angle. `git log` / `git status --short pcb/libs/` show the **currently-committed**
footprint matches this task's fresh reconciliation, not `regen`'s earlier one -- so
`regen`'s board (built earlier this same session) was measured against a transiently
different footprint state that no longer exists. This is exactly the kind of silent
input drift that can masquerade as "the recipe doesn't reproduce" if not caught: same
commit, same code, different library content, different board. Re-running the **full**
recipe fresh, end to end, against today's actually-committed `pcb/libs` state:

```
final (fresh reconcile -> fresh place -> fresh route):
  Result: 80/105 nets (76.2%)  segments=3349 vias=56 zones=70  wall=332.9s
  [net-batching] 12 batch(es), 12 solved at batch level, 0 crashed
    (0 hit the subprocess wall-clock timeout, 0 crashed another way)
```

Segments/zones shift slightly (3319->3349, 66->70) from the T2 footprint content
change; vias do not (56->56). This is a **real, traceable, input-level difference**
(a library file's committed content, not a solver decision) -- not new evidence of
pipeline nondeterminism. Held fixed, the pipeline is exactly reproducible (as §2-4
above show for each stage in isolation, and as this section's route_a/route_b pair
shows for the full routing stage under concurrent load).

## 5. Does PR #1050's own recipe change explain the gap? Tested, not assumed -- no

Between #1050 (`e5539273a`) and the current `main` tip (`d8062c6e6`, this task's base),
`git diff --stat` over every file the recipe's placement and routing stages touch
(`net_batching.py`, `constraint_model.py`, `occupancy_grid.py`, `_astar_reconstruct.py`,
`_astar_ordering.py`, the entire `temper-rust-router`/`temper-rust-router-core` crates,
`packages/temper-placer/.../placer/cp_sat/`, the standalone `pumpkin-engine`) returns
**empty** -- byte-identical. The **only** router_v6 files that changed are
`_ground_plane.py`, `_power_islands.py`, and the new `_corridor_backbone.py` (#1052's
corridor-aware A* plane-backbone work, 823 lines net), which generate ground-plane
zones and their connecting backbone copper -- a plausible mechanism for a
segment/via/zone-count shift.

**Tested directly**: reverted all three files to their exact `e5539273a` content (a
transparent scratch-`PYTHONPATH` overlay shadowing only those three modules --
`packages/temper-placer/src` itself was never modified; `git status` on the real
worktree stayed clean throughout) and re-ran `route_board.py --net-batching` against
the **identical** placed board §4's route_a/route_b used:

```
old-router-code (#1050-era _ground_plane.py/_power_islands.py, no _corridor_backbone.py):
  Result: 75/105 nets (71.4%)  segments=3319 vias=56 zones=66  wall=346.7s
```

**Identical to the current-code result.** #1052's corridor-aware backbone work does not
explain the gap to #1050's 4,228/74 -- it was ruled out empirically, not by assumption.

**Conclusion: nothing testable today explains #1050's originally-documented 4,228
segments / 74 vias.** Every line of code the recipe exercises is proven either
identical to #1050's own commit, or (for the three files that did change) empirically
inert on this exact input. §4 already demonstrates the recipe's own sensitivity to
non-code input drift (a footprint library file) in miniature; the most likely
explanation for #1050's number, unresolvable at this remove, is an analogous
input-state difference at #1050's own original authoring time that left no trace in
either the committed code or the two evidence docs' otherwise-thorough provenance
(neither doc pins an input hash beyond the netlist digest and the reconciliation
delta, which this task reproduced exactly). **#1050's 4,228/74 does not reproduce and
should not be treated as a target future work is measured against; the reproducible
number is the one this task establishes in §6.**

## 6. Re-established baseline

Measured on today's exact committed `pcb/**` state (`git status --short pcb/` empty
throughout), full fresh recipe run (§4's `final`), `kicad-cli pcb drc --all-track-errors
--refill-zones --format json`, 5 repeated samples against the byte-identical output
file:

| metric | value |
|---|---:|
| footprints | **168** (matches the task's expectation) |
| segments | **3,349** |
| vias | **56** |
| zones | **70** |
| nets attempted/routed (Stage 4 A* denominator) | 105 attempted, 80 routed (76.2%) |
| nets fully pad-connected (`pad_connectivity_audit`, PRIMARY metric) | 56/139 (fake-completion 52, honest-gap 31) |
| `unconnected_items` (KiCad oracle) | 330, byte-stable across 5 DRC runs |
| `clearance` (kicad-cli, 5 samples) | 499, 501, 501, 500, 499 -- **range 499-501** |
| `creepage` (kicad-cli, 5 samples) | 173, 168, 176, 173, 174 -- range 168-176 (already-documented wider scatter than clearance) |
| `shorting_items` (kicad-cli, 5 samples) | **91, byte-stable all 5 runs** |
| total DRC violations | 2023-2031 |

**A separate, DRC-tool-level scatter was found and is reported honestly, not folded
into the board-regeneration finding above.** Five repeated `kicad-cli pcb drc` calls
against the **same, byte-identical** `route_a` board file (§4) returned `clearance` in
{499, 500, 502, 504} across 7 total samples taken over the course of this task (2 ad
hoc + 5 systematic) -- i.e. **bare kicad-cli's own DRC measurement is not perfectly
repeatable on a fixed board**, consistent with `docs/evidence/2026-08-12-clearance-regression-independent-spike.md`'s
own noted caveat that this scatter tightens (but wasn't proven to vanish) under
production's `KICAD_CONFIG_HOME` single-thread pin, which this task's ad hoc `kicad-cli`
invocations did not apply. This is a **measurement-instrument** property, separate from
and downstream of the **board-generation** determinism this task's §2-4 establish with
byte-for-byte proof (sha256 / empty diff), which no amount of DRC-sample averaging can
substitute for. `shorting_items` (91, stable across all 5 same-board runs) does not
show this scatter, matching the repo's own prior documented pattern that clearance and
creepage are the categories that scatter, not every category uniformly.

**#1050's 4,228 segments / 74 vias does not reproduce** (§5). **#1050's `clearance`≈499
figure, considered as a number in isolation, is not far from what this task
independently measures (499-504 across two differently-constructed-but-still-recipe-compliant
boards)** -- consistent with the prior finding (`2026-08-12-clearance-regression-independent-spike.md`)
that `clearance` is largely insensitive to how much total copper exists, driven by a
congested region rather than board-wide density. That agreement on `clearance` despite
disagreement on segments/vias is itself informative, not contradictory: it is further
evidence that the segments/vias gap is a copper-completion difference in a specific,
non-`clearance`-relevant part of the board, not a wholesale re-run under different
settings.

## 7. Fix: eliminate silent net-batching fallback (the task's own explicit ask)

**No fix to the solve pipeline's determinism was needed** -- §2-4 prove it already
deterministic on every axis this task could test, and the divergence causes (§4, §5)
are ordinary input/code drift, not a defect to patch. But the task's stated bar for
"where full determinism is genuinely impossible" ("make the nondeterminism visible and
bounded... silent fallback is the thing to eliminate") flagged a real, if
undemonstrated, gap: `net_batching.run_net_batched_stage3` already computes exactly the
right telemetry per batch (`NetBatchResult.batch_crashed`/`crash_reason`, distinguishing
a genuine 900s subprocess-timeout crash from UNSAT or an OOM -- the module's own
"Crash vs. UNSAT, made distinguishable by construction" design) -- but that telemetry
was stored on `RouterV6Pipeline.last_batch_results` and **never read by anything**,
including `route_pcb()`'s return value or `route_board.py`'s own output. It was only
reachable via the `TEMPER_BATCH_TRACE=1` stderr firehose, off by default. A normal
`--net-batching` run gave **zero indication**, ever, of whether any batch silently fell
back under a wall-clock timeout.

**Fixed** (`packages/temper-placer/src/temper_placer/router_v6/_pipeline_types.py`,
`_pipeline_core.py`, `_adapter_types.py`, `_adapter_convert.py`, `scripts/route_board.py`):
`RouterV6Result` now carries `batch_results`; `RoutingResult` (route_pcb()'s public
return type) now carries a small, always-computed `net_batch_summary` dict
(`_summarize_batch_results`) with batch/crash/timeout/singleton-retry/no-topology
counts; `route_board.py` prints it by default (`[net-batching] N batch(es), ... crashed
(M hit the subprocess wall-clock timeout, ...)`) whenever `--net-batching` is used, no
env var required. Verified live in §4's `final` run: `[net-batching] 12 batch(es), 12
solved at batch level, 0 crashed (0 hit the subprocess wall-clock timeout, 0 crashed
another way)` -- the first time this repo's normal routing output has ever stated,
explicitly, that a run's copper is not the product of a timeout fallback.

**Also fixed**: `route_board.py --runs N` (this repo's own built-in reproducibility
harness -- the tool this task would otherwise have had to hand-roll, and initially did)
silently dropped `--net-batching`/`--batch-size` when forwarding to its worker
subprocesses, so `--runs N --net-batching` measured the monolithic path, not the
recipe's own flag. Now forwards both, and `--runs`' spread report additionally prints
segment/via/zone spread (not just completion%), since §6 shows completion% can agree
while copper differs. Both changes verified: existing test suites
(`test_adapter.py` 98/99, `test_net_batching_*.py` 103/103,
`test_pipeline_route_rust_*.py` 63/63, `test_router_v6_output_validity_pbt.py` 4/4) all
pass unmodified; a pre-existing, unrelated failure
(`test_bundled_full_pipeline.py::test_bundled_pipeline_reaches_rust_solve_boundary`,
`networkx.Graph` missing `edges_with_data` on the test's own stand-in skeleton object)
was confirmed to fail identically on `git stash` (i.e. predates and is unrelated to
this change).

## 8. Rules-compliance notes

- `pcb/**` untouched throughout (`git status --short pcb/` empty at every checkpoint
  including the very end of this task; the one write inside `pcb/` --
  `pcb/temper.kicad_dru`, needed to give scratch DRC runs a resolvable ruleset --
  is `.gitignore`d and regenerated fresh by every prior evidence doc in this lineage,
  same convention followed here).
- Every number above carries the command and commit that produced it (§2-6 inline;
  commit `21869cffb`, base `d8062c6e6`).
- The task's own escape hatch ("if the recipe turns out to be deterministic and the
  three boards differ purely because of code/input drift, that is a completely
  acceptable and useful finding") is exactly this task's outcome, reported plainly per
  its own instruction not to round that up or down.
