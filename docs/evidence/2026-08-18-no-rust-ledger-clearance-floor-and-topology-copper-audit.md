# Two `NO_RUST` ledger targets, audited before porting: both are dark

provenance: commit=e63028ccde1be397032479e0735f2a7c1f710d95 dirty=false

**Verdict: neither module is ported. Both audits terminate in a
darkness finding that outranks the port, and one of them is a live
can't-fail metric.**

Brief: port `router_v6/clearance_floor.py` (174 lines, safety-adjacent)
and `router_v6/topology_copper_audit.py` (366 lines, largest unported
module) out of the `.rust-coverage-illusion-inventory` `NO_RUST` set,
auditing each first.

## 0. Conditions

| | |
|---|---|
| worktree | `.claude/worktrees/agent-clearance-floor`, cut from `origin/main` `e63028ccd` |
| `pcb/temper.kicad_pcb` | sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`, **unmodified** (re-verified after every step) |
| env | `make venv-isolate` (`uv sync --all-packages` + `env -u CONDA_PREFIX make extensions`), this worktree's own `.venv` |
| `scripts/check_stale_extensions.py` | run immediately before the measurement: **10/10 fresh**, stale=0 unloadable=0 missing=0 |
| route flags | `scripts/route_board.py --pcb pcb/temper.kicad_pcb --output <tmp>` — **default recipe**: no `--net-batching`, no `--pruning`, no `--nlayer-astar-spike` |
| cProfile | **not attached** |
| machine | 24 cores, load average 3.6–6.1 through the run (shared box, 32 sessions) |
| wall | ~11 min (instrumentation adds per-call Python wrappers; the un-instrumented reference for this recipe is ~206–301 s) |

### Baseline reproduced exactly

```
segments 4553   vias 169   zones 151
routed-content sha256[:16]  6d4e17337bcf2633
routed-file    sha256       6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981
```

Matches the brief's stated baseline (4553/169/151, digest `6d4e1733…`) on
every figure.

**Re-measured after this branch's edits**, un-instrumented, fresh process,
`scripts/check_stale_extensions.py` 10/10 fresh immediately before:

```
Result: 34/105 nets (32.4%)  segments=4553 vias=169 zones=151  wall=230.9s
sha256  6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981
```

**Byte-identical to the instrumented run. The digest did not move.** (The
only changes in this branch are docstrings and this file; the two routes
also cross-check determinism across independent processes.)

## 1. `router_v6/clearance_floor.py` — every function is dark; only the constant is live

### 1.1 Measurement

Call counters wrapped onto the live function objects **and** onto every
already-imported binding of them (`_astar_reconstruct` does
`from … import effective_blocking_clearance`, so patching only the defining
module would have measured nothing and read as a pass). One full production
route:

| symbol | calls |
|---|---:|
| `clearance_floor.blocking_clearance_mm` | **0** |
| `clearance_floor.effective_blocking_clearance` | **0** |
| …same, via the `_astar_reconstruct` binding | **0** |
| `clearance_floor.rasterised_pitch_mm` | **0** |
| `clearance_floor.rasterised_gap_mm` | **0** |
| `_astar_nlayer._family_signature` (the one live `DEFAULT_ROUTING_CLEARANCE_MM` reader) | 105 |
| `run_astar_pathfinding_nlayer` | 1 |
| `run_astar_pathfinding` (legacy 2-layer) | **0** |
| `profile_grids.build_profile_grids` | **0** |
| `pair_clearance.ClearanceProfiles.stamp_clearance_mm` | **0** |

Of 174 lines, the entire executable surface is unreached. The live symbol
is the module-level constant `DEFAULT_ROUTING_CLEARANCE_MM = 0.2`.

### 1.2 Why — two independent gates, both closed

1. **The legacy driver never runs.** `_pipeline_route.py:936`
   `use_nlayer = self.enable_nlayer_astar_spike or len(available_grids) > 2`.
   This board declares four routable signal layers, so Stage 4 always takes
   `_astar_nlayer.run_astar_pathfinding_nlayer`. The three
   `effective_blocking_clearance` call sites all live in
   `_astar_reconstruct.run_astar_pathfinding`, which is the *other* branch.
2. **Even inside that branch they are behind a second gate.** All three sites
   (`_astar_reconstruct.py:274, 437, 484`) are inside `if profile_grids is None:`.
   `profile_grids` is `None` only when `enable_pair_clearance=False`, and
   `git grep enable_pair_clearance` finds **no caller anywhere in the repo
   that passes it** — the parameter has defaulted to `True` since 2026-08-12
   and has no user-facing switch (`docs/evidence/2026-08-12-router-safety-clearances.md:508`
   says so explicitly).

So the functions have been unreachable on this board's production path since
the day the pair-clearance work landed — which is the same PR series that
introduced them.

### 1.3 It is also obsolete by construction, not merely unreached

`blocking_clearance_mm` exists to compensate for a **missing neighbour
half-width**. Under the single-grid stamp the radius is `w_self/2 + c`, the
rasteriser expands by `ceil(radius / cell)`, and the next centreline may sit
at `(expansion + 1) * cell`, so the achieved edge gap is
`c + cell − w_other/2` — *below* `c` whenever `w_other > 2·cell`
(0.25 mm track, 0.1 mm cell: short by 0.025 mm). That is the 2026-08-12
defect, and `blocking_clearance_mm` is a step-function inverse for it.

Both live stamping paths already add the missing term directly:

* `_astar_nlayer.py:1459` stamps every routed net into every width family at
  `trace_width=w_F`, `clearance = max(cl_F, C_family, creepage) + W_family/2`.
* `pair_clearance.ClearanceProfiles.stamp_clearance_mm` (the legacy path's
  equivalent) returns `max(required, cl_marked) + w_searching/2`.

With the two-sided radius `w_F/2 + req + W/2`, the lattice rounding
`(expansion+1)*cell ≥ radius + cell` makes the achieved edge gap
`≥ req + cell` — it **over**-reserves. There is nothing left for
`blocking_clearance_mm` to correct, and its own documented limitation runs
the other way: it "assumes the neighbour has the same width", which
`docs/evidence/2026-08-12-clearance-floor-reland.md:402` measured as 352
mixed-width violations (`0.0460` bucket 70, `0.1460` bucket 52). Porting it
would move a strictly-worse, superseded formula into Rust.

### 1.4 The docstring cites a test that has never existed

`clearance_floor.py:39-40`:

> Measured against the real kernel (``tests/router_v6/test_clearance_floor.py``
> probes it, it is not asserted from this docstring)

`packages/temper-placer/tests/router_v6/test_clearance_floor.py` **does not
exist, and `git log --all --diff-filter=A -- '*/test_clearance_floor.py'` is
empty** — it has never been added on any branch. `git grep` for
`blocking_clearance_mm|effective_blocking_clearance|rasterised_pitch_mm|rasterised_gap_mm`
across the whole tree returns only the module itself, the two dead
`_astar_reconstruct` branches, and prose in `docs/`. **No test anywhere
executes any of the four functions.** The five measured rows in the
docstring (`w=0.25 c=0.15 → gap 0.1500`, …) are unpinned, and the
disclaimer that they are "not asserted from this docstring" is exactly
backwards: the docstring is their only home.

`scripts/check_router_clearance_floor.py` does not close this. Its P1–P5
assert that four *constants* agree (`generate_kicad_dru`, `netclass_rules.yaml`,
`temper.kicad_pro`, parsed `DesignRules`) plus an AST scan for literal
`default_clearance_mm` writes. It never calls `blocking_clearance_mm`.
It passes (exit 0, P1–P5 OK) and is unaffected by any of this.

This branch corrects the citation in place. Nothing else in the module is
touched.

### 1.5 Disposition

**Port refused.** Recommended follow-ups, none taken here (each is a
behaviour change needing its own measurement):

* Delete `blocking_clearance_mm` / `effective_blocking_clearance` /
  `rasterised_pitch_mm` / `rasterised_gap_mm` and the two dead
  `_astar_reconstruct` branches, keeping `DEFAULT_ROUTING_CLEARANCE_MM`.
  The ledger row then resolves by deletion rather than by a port.
* Or, if the `enable_pair_clearance=False` branch is to stay reachable,
  give it a caller and a test — today it is neither.

## 2. `router_v6/topology_copper_audit.py` — the anti-vacuity audit itself never runs

### 2.1 Measurement, same route

| symbol | calls |
|---|---:|
| `net_number_to_name_map` | 5 |
| `nets_with_copper` | **0** |
| `nets_carrying_copper` | **0** |
| `is_self_referential_net` | **0** |
| `audit_topology_vs_copper` | **0** |

The 5 live calls come from `_ground_plane.generate_ground_plane_content`,
`_power_islands.generate_power_islands_content`, and
`pad_connectivity_audit`'s `_parse_segments_and_vias` / `_parse_zones`
(reached from `route_board.py`'s `audit_pad_connectivity` ->
`audit_pcb_file`), which also use the private `_extract_top_level_blocks`.
The live surface is therefore
`_extract_top_level_blocks` + `net_number_to_name_map`, about 30 of 366
lines. Everything else — `nets_with_copper`, `nets_carrying_copper`,
`is_self_referential_net`, `NetCopperOutcome`, `TopologyCopperAudit`,
`audit_topology_vs_copper` — is dark on the default recipe.

### 2.2 Why, and why it matters

`scripts/route_board.py:246`:

```python
if content and result.topology_solved_nets:
    ...
    audit = audit_topology_vs_copper(result.topology_solved_nets, content, net_pins)
```

`content` is non-empty (4553 segments), so `result.topology_solved_nets` was
`[]`. That is not an accident: the 2026-08-16 SAT-vacuity fix
(`docs/evidence/2026-08-16-sat-vacuity-noop-vs-direct-solver.md`) made the
default, non-batched Stage 3 a structural no-op that claims no topology at
all, and `test_topology_copper_audit.py:466` already asserts
`result.topology_solved_nets == []` for exactly that reason.

The consequence was not carried across. This module was written to stop
`net_batching.py`'s topology-level trace from reading green while nets
emitted no copper — an anti-vacuity gate. **On the default production recipe
the gate is now vacuous itself**: it is guarded by the very quantity the
vacuity fix zeroed, so it reports nothing, on every run, and prints no line
saying it did not run. It executes only under `--net-batching`, a
non-default CLI branch.

This is not confined to a local invocation. `make route` (Makefile:109) and
`.github/workflows/board-regeneration.yml:132` both call `route_board.py`
with no `--net-batching`, so the audit is skipped in CI's board regeneration
too.

Directly visible in the run above: `route_board.py:468` prints
`copper_audit_report` only when it is non-empty, and `grep -c "copper-audit"`
over the full un-instrumented route log is **0**. The audit's absence is
silent — nothing in the output distinguishes "audited, no gaps" from "never
ran".

The audit's own end-to-end test survives this the same way: with
`topology_solved_nets == []`, `audit.unexplained_gap == []` is satisfied over
an empty outcome set. It passes (17/17 in this tree) without the audit having
classified a single net.

### 2.3 Disposition

**Port refused.** Porting 366 lines of which ~330 never execute — and whose
headline function is a gate that has stopped firing — would harden the
inertness rather than fix it. The live ~30 lines are pure text kernels
(`_extract_top_level_blocks`, `net_number_to_name_map`) whose natural Rust
home is `packages/temper-io-types/src/strip_copper.rs`'s crate; that port is
real but small, and it is not the finding.

Recommended follow-ups, none taken here:

* Make `route_board.py` report the audit unconditionally, or print an
  explicit "audit skipped: Stage 3 claimed no topology" line. It is
  reporting-only and cannot move the routed digest.
* Give `test_full_pipeline_run_surfaces_the_same_unexplained_gap` a non-empty
  claim set (it currently asserts the empty one), or the assertion is
  vacuous by construction.

## 3. What was checked and not changed

| | |
|---|---|
| `pcb/temper.kicad_pcb` | sha256 unchanged, `git status --short pcb/` empty |
| routed digest | `6d4e17337bcf2633`, 4553/169/151 — equal to the brief's baseline |
| `scripts/oracle_hashes.json` | untouched; no oracle added, none re-pinned |
| clearance/creepage/copper-weight/DRU thresholds | untouched |
| `scripts/check_router_clearance_floor.py` | exit 0, P1–P5 |
| `test_topology_copper_audit.py` | 17 passed |
| `.rust-coverage-illusion-inventory` | untouched — both rows still hold, and correctly so |
