<!-- provenance: measured 2026-08-12, worktree .claude/worktrees/fix-scipy-migration-regression,
branch fix/scipy-migration-regression, commit cff390182 (the fix) on top of
origin/main 66a277d94. pcb/temper.kicad_pcb untouched throughout (`git status
--short pcb/` empty before/after every step; sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, matching the
hash independently recorded in docs/evidence/2026-08-12-board-recipe-reproducibility.md's
own provenance block for the same committed board). All comparisons below ran
in a scratch dir outside pcb/**. -->

# The scipy->Rust connected-components swap in `_corridor_backbone.py` is board-neutral: byte-identical output, directly measured

**Verdict.** The fix (`cff390182`: swap `scipy.ndimage.label` for
`temper_geometry.connected_components_8_transform`, wrapped as
`_connected_components_8`) produces **byte-for-byte identical output**
(SHA256-verified) to the pre-fix scipy code, on the real committed board,
through both production call sites of `_corridor_backbone.py`. A full
`route_board.py` end-to-end re-route was attempted but is not the evidence
this document relies on — see §3 for why, and §2 for the more precise
test that was used instead.

## 1. Why label *ordering* was the real risk, and why it doesn't apply here

`_corridor_backbone.py`'s only two uses of the label array
(`corridor_aware_spanning_edges`'s `groups.setdefault(comp_id, ...)` and
`_nearest_label`'s growing-radius search returning the first nonzero label
found in raster order) both consume labels purely as **partition/equality
markers** — grouping positions that share a label, or testing
"is this cell labelled at all" — never comparing label *values* to each
other numerically or relying on a specific numbering convention. Confirmed
by direct code reading (`_corridor_backbone.py:483-587` in the fixed tree).
This matters because Rust's `connected_components_8_transform` is not
*contractually* required to match scipy's exact label numbering (only the
partition) — but per
`docs/evidence/2026-08-07-rust-connected-components-spike.md`, it does, in
every one of ~8.9M measured cells (33 curated cases + 300 random trials, 0
mismatches, both numeric AND partition). Since this module's logic doesn't
depend on numbering anyway, even a hypothetical future numbering divergence
between the two implementations would not change this module's output — the
risk the task flagged is real in general but structurally inert at this
specific call site.

## 2. Direct measurement: both production call sites, real board, byte-identical

`_corridor_backbone.py` is imported by exactly two production modules
(confirmed: `grep -rln "_corridor_backbone" packages/temper-placer/src/`
returns only these two):

- `_ground_plane.py` -> `generate_ground_plane_content(pcb_path)`
- `_power_islands.py` -> `generate_power_islands_content(pcb_path)`

Both are self-contained, side-effect-free functions: given a `.kicad_pcb`
path, they return `(new_board_content: str, result)` without writing
anything (the caller decides whether/where to write). This makes them a
precise, cheap way to exercise `_corridor_backbone.py`'s exact production
code path against the real board, without running the full multi-stage
`route_board.py` pipeline (which OOM-killed twice in this environment under
concurrent multi-agent load — see §3).

**Method:** ran each function twice against the real, unmodified
`pcb/temper.kicad_pcb` — once with the fix (`_connected_components_8` /
Rust), once with the pre-fix scipy code restored via a scratch patch
(applied and reverted in-place, never committed) — and compared the
returned board content byte-for-byte.

```
$ uv run python3 -c "
from pathlib import Path
from temper_placer.router_v6._ground_plane import generate_ground_plane_content
content, result = generate_ground_plane_content(Path('pcb/temper.kicad_pcb'))
print(result)
"
GroundPlaneResult(pads=86, drop_vias=79, mst_edges=73, zone_polygons=2,
  keepout_established=True, keepout_area_mm2=19054.1, pour_area_mm2=12230.4,
  keepout_zones=15, via_skipped_through_hole=6, via_offset=46,
  via_unresolved_conflict=1, mst_edges_astar_routed=15, mst_edges_fallback=70)
```

Identical `GroundPlaneResult` (same 12 fields, same values) from both the
Rust and scipy code paths. **`mst_edges_astar_routed=15`** confirms the
corridor-mask/connected-components code path was genuinely exercised (not
short-circuited to 0) — 15 of 73 MST edges were resolved via
`corridor_aware_spanning_edges`, which is exactly the function this fix
touches.

```
$ sha256sum gnd_after_fix.txt gnd_before_fix_scipy.txt
a72d25032635b548f27366ffd84a56b56510ace9246c69358e7f3813d80913ec  gnd_after_fix.txt
a72d25032635b548f27366ffd84a56b56510ace9246c69358e7f3813d80913ec  gnd_before_fix_scipy.txt
$ diff gnd_after_fix.txt gnd_before_fix_scipy.txt   # empty, exit 0
```

Same test for `generate_power_islands_content` (all four power-island rails
in one call: `+3V3`, `vcc`, `+15V`, `V_BUS_SENSE`):

```
PWR RESULT: {'+3V3': PowerIslandResult(..., mst_edges_astar_routed=7, ...),
             'vcc': PowerIslandResult(..., mst_edges_astar_routed=0, ...),
             '+15V': PowerIslandResult(..., mst_edges_astar_routed=0, ...),
             'V_BUS_SENSE': PowerIslandResult(..., mst_edges_astar_routed=0, ...)}
```

Identical result objects from both code paths (`+3V3`'s
`mst_edges_astar_routed=7` again confirms real exercise of the changed
code, not a vacuous 0/0 pass).

```
$ sha256sum pwr_after_fix.txt pwr_before_fix_scipy.txt
bee24d088317361c19295e531840c0d885892fd102fa55afdd6ca24662a75613  pwr_after_fix.txt
bee24d088317361c19295e531840c0d885892fd102fa55afdd6ca24662a75613  pwr_before_fix_scipy.txt
$ diff pwr_after_fix.txt pwr_before_fix_scipy.txt   # empty, exit 0
```

**Both of `_corridor_backbone.py`'s only two production callers produce
byte-identical output before and after the fix, on the real committed
board.** Because these two functions' returned string is exactly the new
board content the router pipeline later writes (unmodified by anything
downstream of them for this content), byte-identical output from both
callers is equivalent to byte-identical final routed-board output for the
segments/vias/zones this module is responsible for — the rest of
`route_board.py` (Stage 0-4 net-by-net A* routing for the other ~100 nets)
never imports or calls anything in `_corridor_backbone.py`, confirmed by
the same `grep` above.

## 3. Why a full `route_board.py` run isn't this document's evidence

A full end-to-end `route_board.py --pcb pcb/temper.kicad_pcb --output
<scratch>` run (matching
`docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s own recipe,
baseline 168 footprints / 3,349 segments / 56 vias / 70 zones / 80/105 nets)
was attempted twice in this worktree, before and after the fix. **Both runs
were killed by the OS OOM killer** (`dmesg`: `Out of memory: Killed process
... (python3) ... anon-rss:59777272kB` and `anon-rss:59470444kB` — ~59.5GB
resident, on a 62GB-total machine under concurrent load from dozens of other
agent worktrees sharing this host). This is an environment resource
constraint, not a defect in the fix or in `route_board.py` — the
reproducibility doc's own baseline was measured on a less-contended machine
at a different time. Rather than retry indefinitely against unstable shared
capacity, §2's narrower, targeted test was used instead: it exercises
exactly the changed function against exactly the real board, at ~380MB peak
RSS and ~17s wall time (measured, `/usr/bin/time -v`), and is strictly more
precise for this specific question than a full-board diff would have been
(a full-board diff would also be sensitive to Stage 0-4 net-batching
subprocess nondeterminism unrelated to this fix, which is exactly the
confound the reproducibility doc's own §4-5 had to separately rule out).

## 4. Conclusion

**Board-neutral, with direct evidence**: both call sites of the changed
code, run against the real, unmodified `pcb/temper.kicad_pcb`
(sha256 `6928b7c8...0544b64`, unchanged throughout), produce byte-identical
output whether the connected-component labeling comes from scipy or from
the Rust replacement. Combined with §1's structural argument (the module
only ever uses labels for equality/partition, never ordering), this is a
converging, not merely additive, case: the code doesn't depend on label
ordering, and measured real-board output confirms it.
