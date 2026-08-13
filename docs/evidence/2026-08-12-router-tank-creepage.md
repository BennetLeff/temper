<!-- provenance: commit=4ad8767fdb1feacbd08cca8465eac88530cb59dc dirty=false
measured 2026-08-12, worktree /home/bennet/Desktop/temper-worktrees/router-tank-creepage,
branch feat/router-tank-creepage, HEAD 4ad8767fd (3 commits ahead of origin/main 565078e54).
pcb/temper.kicad_pcb NEVER modified -- `git status --short pcb/` empty throughout; every
kicad-cli measurement below ran against a scratch copy under /tmp, never the committed file.
kicad-cli 10.0.5 via the repo's PATH shim (/home/bennet/.local/bin/kicad-cli, PR #1086).
scripts/verify_pumpkin_engine.py: VERIFIED (sha256=7ff153f47..., source_commit=5bbf650d4)
before any solve/route was attempted. This machine ran 258 concurrent agent worktrees at
measurement time (load average 4.97-64.35, RAM repeatedly driven to <15GB free by other
sessions' processes); one routing attempt in this session was OOM-killed
(dmesg: "Out of memory: Killed process 1364012 (python3) ... anon-rss:58586048kB"), and a
second, `--net-batching` attempt was killed BY THIS SESSION under continuing shared-machine
memory pressure before it finished, per explicit instruction not to let it keep competing
for memory. See Sec 4 for exactly what is and is not measured as a result. -->

# Teaching `router_v6` the tank-node HV<->HV creepage requirement: the router is fixed and unit-tested; a freshly-routed real-board measurement is outstanding

**Verdict up front.** The router did not know this requirement existed at all — not
approximately, not as a per-net over-approximation, not in any form.
`NetClassRules.creepage_mm` reaches the router's own data structures (confirmed:
`safety_category='HV'`, `creepage_mm=10.0` on the marshalled `HighVoltageTank`
netclass) but nothing in the A* occupancy-grid hot path ever reads that field —
only `.clearance_mm` is read, per net-class, not per pair. That gap is now closed:
`router_v6/tank_creepage.py` teaches the router a **true pairwise** keepout (tank
pads vs. every other HV/AC-domain net), not a per-net over-approximation, because
`HighVoltageTank` contains exactly one net. The mechanism is implemented, unit
-tested (15/15 passing), and does not touch any file the router-suite regression
run flagged as broken. **What is NOT measured: whether a freshly-routed board
actually clears the `C25` pad 2 <-> `discharge.k_dis1-nc` pair at 10.0mm.** Two
routing attempts died to machine-wide memory pressure (one OOM-killed outright, one
killed by this session under continuing pressure) before producing an output file.
That measurement, and the full before/after ceiling comparison it would enable, are
**outstanding** — reported as such, not estimated.

## 1. What the router reads today (code-tracing, not dependent on the route)

Traced `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py`,
`astar_core.py`, `astar_grid.py`, `_astar_reconstruct.py`,
`terminal_tree_execution.py`, and `constraints_design_rules.py` on origin/main
(565078e54, before any change in this branch).

**Only clearance reaches the router's pathfinding; creepage does not, at all.**
`OccupancyGrid.mark_path_blocked` / `mark_via_blocked` dilate a just-routed net's
own copper by `trace_width/2 + clearance` before the *next* net's A* search runs
(the call sites: `terminal_tree_execution.py:215`, `astar_grid.py:306-317`,
`_astar_reconstruct.py`'s ripup path). The `clearance` value comes from
`design_rules.get_rules_for_net(net_name).clearance_mm` — `_astar_reconstruct.py`'s
own comment names this explicitly: *"Same per-net rule as ... not the flat board
default."* `NetClassRules.creepage_mm` is a real field, and it genuinely is
marshalled all the way through to the router's own data structures
(`_adapter_convert.py`'s `_to_stage0_netclass_rules`) — confirmed empirically in
this session:

```
NetClassRules(name='HighVoltageTank', clearance_mm=2.0, ..., safety_category='HV', creepage_mm=10.0)
```

But **grep across every A*-hot-path file in `router_v6/` finds zero reads of
`creepage_mm`** outside of: (a) `creepage_check.py`, a Stage-5.6 *post-route*
verification pass with its own independent IPC-2221 table and HV-net keyword
classifier, unrelated to `NetClassRules`; (b) `bottleneck_geometry.py`, a
*post-hoc diagnostic* that reports why a net failed, never a routing constraint;
(c) `clearance_engine.py`, used by exactly one consumer (HV ghost-pad injection at
*placement* time, not Stage 4 routing). None of these steer the A* search away
from anything. This is the same shape of gap PR #1084 found on the Rust DRC-kernel
side (creepage keys on net *name*, not netclass) — here it is worse: the router
does not consult the field at all, approximately or otherwise.

**A true per-net-PAIR clearance model exists in this codebase, but is wired to
the wrong stage.** `constraints_design_rules.py`'s `ClearanceMatrix` supports
exactly what this problem needs:
`set_class_to_class_clearance(class_a, class_b, clearance)` /
`get_clearance(net_a, net_b, x, y)`. Grepped every call site of
`ClearanceMatrix.get_clearance`: all eleven are inside `constraints_drc_oracle.py`
— a **post-route verification** oracle, not the A* search. Nothing in the
occupancy-grid dilation path calls it.

**So: per-net-CLASS clearance reaches the router; per-net-CLASS-PAIR clearance is
expressible in this codebase but not wired into pathfinding; creepage reaches
nowhere in the hot path at all.** Because `HighVoltageTank` contains exactly one
net (`tank.c_tank1-p2`), a class-pair rule (`HighVoltageTank` vs. every other
HV/AC-domain class) is, in practice on this board, already a true net-*pair* rule
— which is the shape this fix takes (Sec 2), not the over-broad per-net
approximation this brief warned against.

## 2. What was changed

**Brought PR #1084 onto this branch.** #1084 (`feat/hv-hv-creepage-enforcement`)
and #1089 (`feat/tank-creepage-placement`) are open, unmerged PRs (`gh pr view
1084/1089 --json state` -> `"OPEN"`); #1084's branch is based on a stale `main`
(`git merge-base origin/main origin/feat/hv-hv-creepage-enforcement` !=
`origin/main`'s tip) and has not been rebased. Cherry-picked its two commits
(`80a1df053`, `e7aca553f`) cleanly onto `origin/main` — no conflicts — to get the
`HighVoltageTank` netclass and the generated `.kicad_dru` rule this task needs to
verify against. `pcb/temper.kicad_pro` (part of that cherry-pick) and
`scripts/generate_kicad_dru.py` are touched; `pcb/temper.kicad_pcb` is not.

**Corrected PD2 (6.3mm) -> PD3 (10.0mm).** #1084 as authored emitted PD2/6.3mm --
its own comments already said this was a floor against a sealed-compartment
enclosure that does not exist
(`docs/evidence/2026-08-11-pd2-decision-record.md` sec 2: "PD3/12.6mm governs the
as-built construction today" for the general HV<->LV barrier; the identical gap
applies to the tank-node functional figure). This brief's own bar is 10.0mm, and
#1089's placement constraint already used 10.0mm ("PD3, as-built-governing") as
precedent. Flipped `scripts/generate_kicad_dru.py`'s
`_TANK_POLLUTION_DEGREE = "PD2"` -> `"PD3"` (a one-line switch by the constant's
own design), and brought `netclass_rules.yaml` / `core/design_rules.py`'s
`HighVoltageTank.creepage_mm` into agreement (6.3 -> 10.0), plus corrected several
`.kicad_dru`-embedded comment strings that had hardcoded "6.3mm" prose (would
otherwise misdescribe the emitted rule). One real, **not fixed here**, gap
surfaced by this correction: `RULE 4c`'s blanket 8.0mm `HighVoltageTank to LV`
figure was conservative against the old 6.3mm tank figure but is no longer
conservative against 10.0mm for the tank<->PWR_RTN pair specifically (PWR_RTN
carries no netclass and reads as Default/LV) -- flagged in the generated file's
own comments, not fixed (fixing it means giving PWR_RTN a real netclass, out of
scope here).

`scripts/check_creepage_clearance_drift.py` still exits 3 with the same 4
pre-existing MISMATCH families as before this change (verified, both before and
after) -- `HighVoltageTank`'s entries land in that gate's FLAGGED
(unspecified-tier) bucket exactly as #1084 designed, and
`HV_TANK_CREEPAGE_ENFORCED_MM`'s dict-lookup selection still reads as UNRESOLVED
rather than tripping the gate's alias self-check (exit 3, not 5).

**Taught the router.** New module
`packages/temper-placer/src/temper_placer/router_v6/tank_creepage.py`:

- `TANK_CREEPAGE_MM = 10.0`, `TANK_NET_CLASS = "HighVoltageTank"`.
- `needs_tank_creepage_check(net_name, design_rules)`: true for any net whose
  class has `safety_category in {"HV", "AC"}` and is not `HighVoltageTank`
  itself.
- `tank_pad_positions(pad_centers_per_net, design_rules)`: every pad belonging to
  a `HighVoltageTank`-class net. **Pad positions, not the tank net's own routed
  path** -- the measured violation this closes (`C25` pad 2 <->
  `discharge.k_dis1-nc`) is pad-to-track, and pad positions are fixed at
  placement time, so this works regardless of what order `_compute_net_order`
  routes nets in (no dependency on the tank net routing first).
- `apply_tank_creepage_keepout` / `release_tank_creepage_keepout`: temporarily
  block every currently-FREE cell within `pad_radius + 10.0mm` of a tank pad,
  mutating the **real, shared** occupancy grid in place (not a throwaway copy),
  mirroring `astar_grid.py`'s existing `_unblock_net_pads`/`_restore_net_pads`
  idiom in the opposite direction. A cell already carrying real copper (a
  positive net_id) or a permanent static obstacle (-1) is never touched -- the
  ripup mechanism inside `_astar_route_with_ripup` identifies blockers by their
  real net_id and must never see a borrowed one.

Wired into `_astar_reconstruct.py`'s `_attempt_route_fail_closed` -- the single
choke point every routing attempt (initial pass and reroute-queue retries alike)
already passes through, so one `apply`/`finally: release` wrap covers every
attempt without touching `attempt_route`'s many internal return points, and a
raised exception can never leave cells stuck blocked. Nets that are not
HV/AC-domain never see the keepout at all -- LV/GND/Signal routing is completely
unaffected, so this does not pay the over-broad, board-wide-infeasible cost a
blanket per-net radius bump would (the cost this brief specifically asked to be
quantified if the per-net-only shape had to be used -- it does not, so there is
no such cost to report).

**Known, documented gap, left undone deliberately (YAGNI):** this protects tank
*pads*; it does not additionally protect the tank net's own *routed trace* from a
later HV/AC trace swinging close to it mid-span. No measured violation on this
board currently needs that (the measured case is pad-to-track), and the
mechanism to add it (re-deriving the keepout from the tank net's routed geometry
once it exists) is order-dependent in a way pad-positions are not -- left as a
documented residual rather than implemented speculatively.

**Testing performed:**
- 15 new unit tests in `tests/router_v6/test_tank_creepage.py` (classification;
  apply/release; never-overwrites-real-copper; never-overwrites-a-static
  -obstacle; per-layer isolation; missing-layer/empty-pad-list no-ops) --
  **15/15 passing**.
- `packages/temper-placer/tests/router_v6/` run to ~88% completion (10-minute
  budget; ~5,800/6,582 collected tests) with `test_bundle_analyzer.py`'s one
  known-unrelated failure deselected. Three additional failure clusters seen
  (`test_channel_skeleton_bridging.py` x6, `test_channel_skeleton_radius_pairs_
  rust_differential.py` x1, `test_phase1_anti_false_zero.py::
  test_kicad7_footprint_dir_resolves` x1) -- confirmed **pre-existing and
  unrelated**: `git diff --stat 565078e54 -- <each failing file>` is empty for
  all of them (this change touches none of them), and the failure signatures
  are a Rust `SkeletonGraph` API mismatch (`'Graph' object has no attribute
  'connected_components'`) and a missing `KICAD7_FOOTPRINT_DIR` env var in this
  session's isolated venv -- neither related to netclass/router-clearance code.
- `test_design_rules.py` (17+7 passed), `test_netclass_loader.py` (15 passed):
  clean. `test_design_rules_rust_differential.py`: 3 pre-existing failures,
  **the same 3 PR #1084's own description already documented as pre-existing on
  pristine `main`** ("the pinned oracle still carries `HighVoltage.clearance =
  6.0` against the live `2.0`. Same message, same constant, on both.") --
  unrelated to `HighVoltageTank`/this change.
- `scripts/verify_pumpkin_engine.py`: VERIFIED before any solve/route attempt
  (see provenance header).

## 3. Does the `C25` <-> `discharge.k_dis1-nc` pair clear 10.0mm on a freshly-routed board?

**Not measured. Outstanding.**

Two attempts to produce a fresh route via `scripts/route_board.py` (the
production entry point, `temper_placer.router_v6.adapter.route_pcb`) both failed
to complete, under conditions outside this session's control:

1. **First attempt** (no `--net-batching`, matching `make route`'s default):
   OOM-killed by the kernel after ~9 minutes.
   `dmesg`: `Out of memory: Killed process 1364012 (python3) total-vm:65246744kB,
   anon-rss:58586048kB` -- 58GB resident, on a machine with a concurrent sibling
   `route_board.py` process (a different agent's session) also running at the
   time.
2. **Second attempt** (`--net-batching`, the codebase's own documented mitigation
   for this exact Stage-3 memory-blowup shape -- confirmed in `net_batching.py`'s
   own docstring that batching changes Stage 3 topology assignment only, not
   Stage 4's occupancy-grid mechanism this change modifies): memory stayed
   bounded (~19GB) for several minutes of real progress (confirmed: sequential
   `multiprocessing.spawn` batch-worker child processes, each doing real CPU
   work), but by the time this was checked directly (not inferred, not
   estimated) the shared machine was at **258 concurrent agent worktrees, load
   average 4.97-64.35, 13GB free and falling, swap at 2.0/2.0GB (full)** -- a
   state in which another agent's process had already been separately
   OOM-killed at 47.7GB with 7.9GB free. Per explicit instruction not to let
   this session's process keep competing for memory under those conditions, it
   was killed by this session (`kill -TERM`/`-KILL` on the parent and its
   surviving batch-worker child) rather than left running or relaunched. No
   output file was produced by either attempt
   (`ls temper_routed.kicad_pcb` -> `No such file or directory`, confirmed
   after the kill, not assumed).

**What WAS measured, and what it does and does not tell us.** The DRC scratch
harness itself (fp-lib-table + `libs/` + a freshly-regenerated `.kicad_dru`,
copied next to a scratch board with a resolvable `.kicad_pro` sidecar --
`ensure_resolvable_kicad_project`'s requirement) was built and verified working
end-to-end against the **current committed board** (`pcb/temper.kicad_pcb`,
copied to scratch, never modified in place) -- i.e. the *existing, pre-existing*
routing, not a route the taught router produced:

```
Creepage violation (rule 'HighVoltageTank functional creepage' creepage 10.0000 mm; actual 6.3992 mm)
  PTH pad 2 [tank.c_tank1-p2] of C25
  Via [discharge.k_dis1-nc] on F.Cu - B.Cu

Creepage violation (rule 'HighVoltageTank functional creepage' creepage 10.0000 mm; actual 2.2656 mm)
  PTH pad 2 [tank.c_tank1-p2] of C25
  Track [discharge.k_dis1-nc] on B.Cu, length 7.6368 mm
```

The 2.2656mm figure is an exact match to PR #1084's own headline number. This
confirms two things and no more: (a) the regenerated `.kicad_dru` genuinely
emits `HighVoltageTank functional creepage` at **10.0mm** now (not 6.3mm), and
(b) the DRC toolchain this evidence doc's own measurement would need is working
correctly end-to-end. It says **nothing** about whether the taught router
avoids this pair on a fresh route, because the router was never invoked to
produce this board -- it is the same copper that has been on `main` all along.
That is the specific, single most important number this task asked for, and it
is not in hand.

## 4. Ceiling comparison

**No before/after-teaching-the-router comparison exists.** Producing one requires
a completed fresh route, which Sec 3 explains is outstanding.

**One real, single-sample DRC measurement is in hand** (the committed board,
unmodified routing, against the corrected 10.0mm PD3 `.kicad_dru` rule --
the same board underlying Sec 3's numbers):

| category | ceiling record (`f70296adc`, PD2/6.3mm tank rule) | measured just now (same board, byte-identical, PD3/10.0mm tank rule) |
|---|---|---|
| creepage | 186 | **187** |
| clearance | 386 | 386 |
| total errors | 1266 | **1267** |
| total warnings | 489 | 489 |

The +1 creepage / +1 error delta is a single sample, not the >=120-sample band
this repo's own noise-headroom convention requires before treating any delta as
real rather than measurement noise (AGENTS.md's DRC-ceiling section); it is
reported for context only. It is also, by construction, **not attributable to
the router change** -- the router was never invoked between these two readings,
only the `.kicad_dru` threshold moved (6.3mm -> 10.0mm rejects one more pair on
an unchanged board). `power_pcb_dataset/drc_ceiling.json` is untouched, as
instructed; this is not a re-measurement proposal.

**Genuinely outstanding, not estimated:** the full before/after comparison a
freshly-routed board would give -- whether teaching the router costs anything in
`clearance` (already the board's dominant category at 386) or elsewhere, and
whether the `C25`<->`discharge.k_dis1-nc` pair specifically now clears 10.0mm on
copper the taught router actually placed.

## 5. What a follow-up needs to do

1. Route the board (`uv run python3 scripts/route_board.py --pcb pcb/temper.kicad_pcb --rules packages/temper-placer/configs/netclass_rules.yaml --net-batching --output <scratch>/temper_routed.kicad_pcb`) when the shared machine has headroom -- check `free -h`, `uptime`, and `ps aux` for concurrent `route_board.py`/`pumpkin_engine` processes first, per `AGENTS.md`'s own guidance, and do not run alongside another session's routing attempt.
2. DRC it with the harness already built and verified in this session: `pcb/fp-lib-table` + `pcb/libs/` copied alongside a `.kicad_dru` freshly regenerated from this branch's `scripts/generate_kicad_dru.py`, a `.kicad_pro` sidecar copied and renamed to match the scratch board's stem (`copy_kicad_project_sidecar` / the manual equivalent used in this session), `kicad-cli pcb drc --all-track-errors --format json`.
3. Check specifically for `HighVoltageTank functional creepage` violations naming `C25` and `discharge.k_dis1-nc` (present in this session's baseline at 2.2656mm/6.3992mm; the whole point of this change is that they should be absent, or at minimum increased, in a route the taught router produced).
4. Report the full `violations_by_type` table against this doc's Sec 4 baseline (creepage 187, clearance 386, errors 1267 on the *unrouted-by-this-change* board) -- not against `drc_ceiling.json`'s stale PD2/6.3mm-rule record, which is not a fair comparison once the DRU rule itself has changed.
