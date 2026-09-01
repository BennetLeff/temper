<!-- provenance: commit=d0b88a5053a12591b877d7edab67153f493d7586 dirty=true -->

# Two structural items — flagged, not fixed (owner decision required)

Per this task's explicit instruction: characterize precisely, do not act. Both
items carry large blast radius on a mains-voltage (IEC 60335-1) board and are
owner decisions, not agent decisions. This document adds direct verification
of the mechanism (file:line, not paraphrase) on top of what
`docs/HANDOFF-2026-08-17.md` §14 and
`docs/evidence/2026-08-17-python-deprecation-spike.md` §2 already established,
so the owner has one place with the exact control-flow trace.

---

## 1. `router_v6/_astar_nlayer.py` — a file labelled "prototype, not production"
   is the router's live default path

**File**: `packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py`,
1,335 LOC (grew from the 1,319 recorded 2026-08-16; still actively receiving
routing fixes). Its own module docstring, unedited:

> **Status: prototype, not production.** Branch `spike/nlayer-via-astar`, spun
> up to answer a design question, not to replace the production A* path.

**The exact control-flow trace that makes this false today**
(`packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:920-984`):

```python
920  all_grids = stage2.occupancy_grids or {}
921  routable_layers = _routable_signal_layers_for_pcb(pcb)
922  available_grids = {name: g for name, g in all_grids.items() if name in routable_layers}
...
936  use_nlayer = self.enable_nlayer_astar_spike or len(available_grids) > 2

938  if pathfinding_result is None and use_nlayer:
946      from temper_placer.router_v6._astar_nlayer import (
947          run_astar_pathfinding_nlayer, select_routing_grids_nlayer)
...                                              # <- the "prototype" path
976  elif pathfinding_result is None:
977      fcu_grid, bcu_grid = select_routing_grids(available_grids)
979      pathfinding_result = run_astar_pathfinding(...)  # <- the "production" path
```

`enable_nlayer_astar_spike` does default to `False` everywhere it is
constructed. But the guard is an `or`, and `available_grids` is the board's
declared routable-signal-layer count. PR #1178 (2026-08-15) declared the
6-layer stackup; that gives 4 usable signal grids (F.Cu, In3.Cu, In4.Cu,
B.Cu), so `len(available_grids) > 2` is `True` unconditionally on the board
this project ships. **The stackup decision — unrelated to this file, made two
days after it was written — silently flipped which branch is "production."**
Line 976's `elif` (the branch the docstring calls production) is dead code on
this board today, not the other way around. It is not incapable in general —
it would still run correctly on a genuine 2-layer board — it is simply
unreachable given the current stackup declaration, which is exactly the
"second, 2-layer path still present" the task brief refers to.

**This is not a stale, unmaintained spike.** Every routing fix landed this
session touches it directly: pad-layer landing (#1246), multi-pad routing
(#1245), width-aware C-space (#1249, referenced at `_pipeline_route.py:970-974`
as consuming `_astar_nlayer.py`'s "family helpers"), creepage-aware halos
(#1267), the PD3 clearance-halo fix (#1301). The file is de facto the
production N-layer router and has been developed as one, just never
relabelled or promoted through whatever process would normally accompany that
(design review, docstring/status update, moving out of a module that still
says "spike" in its own name).

**Partially de-risked, not resolved**, per PR #1303
(`docs/HANDOFF-2026-08-17.md` §14): its tests are now collected under
router_v6 **group 3** — the one router_v6 CI shard that is required and
unmasked (groups 1/2/4 are schedule-only or `continue-on-error`-masked, per
`.github/required-checks.json` / the workflow's router_v6 test-group wiring).
The blanket `# mypy: ignore-errors` suppression was removed (3 real errors
fixed, zero new `type: ignore`). That closes the "untested prototype in
production" risk; it does not close the "undocumented status, undocumented
promotion" risk — the module still says prototype, the two-line `or` that
promoted it is still undocumented at the point of use (no comment at
`_pipeline_route.py:936` explains that this is a promotion, only that it is a
threshold), and nothing prevents a future stackup change from silently
flipping the branch again in either direction.

**Owner decision needed, not attempted here**: either (a) formally promote
`_astar_nlayer.py` — rename/relabel it out of "spike" status, fold
`docs/evidence/2026-08-08-nlayer-via-astar-spike.md`'s findings into a real
design doc, and make `_pipeline_route.py:936`'s branch selection an explicit,
documented, tested decision rather than an accidental `or`; or (b) if the
2-layer path is meant to stay the intended default, gate the N-layer path
back behind an explicit opt-in and route today's 6-layer board through a
path that was actually designed to be production. Both are real work with
real blast radius on a board that is currently only 43.9% routed
(`docs/HANDOFF-2026-08-17.md` §4) using exactly this router. **Not touched by
this task** — flagging only, per the task's explicit instruction.

---

## 2. The Python-orchestration-over-Rust-kernel duality

**The shape**: `_astar_nlayer.py`'s actual pathfinding search is already
Rust. Per `docs/evidence/2026-08-17-python-deprecation-spike.md` §1c,
`router_v6/astar_core_rust.py` is a self-documented pure-delegation shim over
`astar_kernel_3d_py` — "the Rust kernel is now the sole backend" since
2026-07-31. The 1,335 Python lines in `_astar_nlayer.py` are not the search
algorithm; they are orchestration around it: grid selection
(`select_routing_grids_nlayer`), corridor/family construction from
`routing_spaces` (the width-aware C-space families referenced at
`_pipeline_route.py:970-974`), retry/coarse-to-fine control
(`enable_coarse_to_fine`, `coarse_factor`), batching, and escape-via wiring —
real control-flow logic, not a thin wrapper, so this is not a PR #1302-style
"delete the shim" candidate.

**The duality**: this Python orchestration layer exists *alongside*, not
instead of, a Rust-side orchestration layer for routing. `temper-orchestration`
already owns staged pipeline orchestration for other parts of the board build
— `packages/temper-orchestration/src/router_pipeline.rs` defines
`RouterStageLegalize` and sibling stages that call back into Python leaf
modules via `py.import(...)` (documented in
`docs/evidence/2026-08-17-python-deprecation-spike.md` §2:
`router_pipeline.rs:309` imports `temper_placer.router_v6.placement_legalization`
under `RouterStageLegalize::run`, gated by `enable_legalization`), and
`.unwired-kernel-inventory` records an entire family of Rust-orchestrated
"Phase D" stages (D2/D3/D6/D7 batches, e.g. `zone_geometry_stage.rs`,
`grid_fence.rs`, `drc_validation_stage.rs`, `hv_lv_partition_stage.rs`) that
already moved stage sequencing into Rust with Python reduced to leaf kernels
called back via `PyModule::import`. Pathfinding itself — the highest-LOC,
highest-churn stage in the whole router — has not received that treatment:
its orchestration is still Python-side, calling a Rust leaf kernel, rather
than Rust-side orchestration calling back into Python (or not needing to at
all, if the leaf kernel is already the only real work).

**Cost of leaving this as-is**: every future routing-quality fix (the pattern
of this entire session — #1246, #1249, #1259, #1261, #1267, #1301, all
touching this file or its Rust-boundary siblings) has to reason about a
Python orchestration layer that duplicates responsibility with an
already-established Rust orchestration pattern elsewhere in the same crate
family, on a codebase whose own stated direction is "Rust is preferred over
Python; the placer is actively migrating off Python" (project instructions).
Each fix is real work done twice over time: once to get the Python
orchestration correct, and — if the eventual direction is Rust-side stage
orchestration matching the D2/D3/D6/D7 pattern — again to port it. The
router is also the single most safety-relevant subsystem on this board (mains
creepage/clearance obstacle halos are computed in this exact code path per
#1259/#1261/#1267), so the migration, if undertaken, needs the same
oracle-pinned differential discipline as every other Rust port in this repo —
not a rewrite from a spec, a byte-exact port validated against pinned
behavior.

**Cost of migrating**: `_astar_nlayer.py` is 1,335 LOC of real, live,
actively-changing orchestration logic — a "Tier 3, real migration work" item
by PR #1302's own ranking (§3, tier 3 lists exactly this class:
`_ground_plane.py`, `_power_islands.py`, etc. — large, live, no single Rust
owner, "biggest behavioral-parity risk"). A migration attempted mid-session,
concurrently with the routing-quality fixes already landing in this same
file weekly, risks exactly the kind of divergent-behavior defect this whole
task is trying to reduce, not produce.

**Owner decision needed, not attempted here**: whether to (a) invest in
porting `_astar_nlayer.py`'s orchestration to Rust to match the D2/D3/D6/D7
pattern (real, multi-week migration work, needs a dedicated plan +
oracle-pinned differential, the same rigor as the Phase D program), (b)
formally accept the Python-orchestration-over-Rust-kernel split as the
long-term shape for this specific stage (pathfinding orchestration is
inherently stateful/iterative in a way that may not benefit from Rust-side
staging the way the more mechanical D-batch stages did), or (c) leave it
unresolved and accept the duplicated-reasoning cost documented above as an
ongoing tax. No code changed for this item.
