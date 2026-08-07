# Wave 4 triage: `router_v6/constraints_spatial_index.py` — no port (JUSTIFIED-KEEP + dead code)

<!-- provenance: commit=af5aa02c84c73c542d696d53941b405df52c64e9 dirty=false -->

Target crate assigned: `packages/temper-drc-rs`. Source:
`packages/temper-placer/src/temper_placer/router_v6/constraints_spatial_index.py`
(403 LOC at origin/main `af5aa02c8`).

**Verdict: no port.** The file has three parts once triaged: a `scipy.spatial.cKDTree`
wrapper (`PCBGeometry`) that is a library boundary matching this repo's own recorded
precedent for scipy, one function with zero callers anywhere in the repo
(`merge_collinear_tracks`) plus four more dead members inside the live classes, and a
handful of one-line dataclass glue methods (`Track.midpoint`/`.to_segment`/
`.is_diff_pair_with`, `Pad.rot_rect`) that are live but operate on `Point`/`LineSegment`/
`RotatedRect` — types this file does not define and that belong to
`constraints_geometry.py`, explicitly out of scope here (sibling agents own
`temper-geometry`/`temper-io-types`; porting these four glue methods without those
types would mean forking a second, divergent copy of them into `temper-drc-rs`, the
exact "three copies, one wrong" failure mode this program is trying to eliminate,
per `pymath::py_hypot`'s own doc comment at `packages/temper-drc-rs/src/pymath.rs:258-289`).
No separable numeric/geometric kernel exists to FFI across.

## What the file actually is

- Lines 23-48: `Track` — a `@dataclass` (`start`, `end`, `width`, `net`, `layer`, `id`,
  `diff_pair_companion`) with three one-line methods: `is_diff_pair_with` (equality
  check), `to_segment` (wraps `start`/`end` in a `LineSegment`), `midpoint` (average of
  two `Point`s). All three are live — called from
  `router_v6/constraints_drc_oracle.py` (e.g. lines 471, 632, 647, 651, 700, 712).
- Lines 51-67: `Via` — a `@dataclass` plus `conductive_layers` (one-line ternary over a
  `frozenset`). **Dead** — zero callers (below).
- Lines 70-103: `Pad` — a `@dataclass` plus `conductive_layers` (dead, same shape as
  `Via`'s), `rot_rect` (live — wraps fields in a `RotatedRect`, called from
  `constraints_drc_oracle.py:412,539,716,743` and
  `deterministic/stages/connectivity_validation.py:258,259,267,281`), and `radius`
  (circumscribed-circle property — **dead**, below).
- Lines 106-282: `PCBGeometry` — `add_track`/`add_via`/`add_pad` (dict/list bookkeeping
  plus index invalidation), `get_geometry_by_id` (dead, below), `rebuild_index`
  (builds `numpy` arrays and constructs three `scipy.spatial.cKDTree`s), the three
  `query_*_near` methods (`cKDTree.query_ball_point` + a Python-side layer filter),
  and `clear`. This class's only actual compute is the `cKDTree` construction/query —
  everything else is container bookkeeping around it.
- Lines 284-403: `merge_collinear_tracks` — a real geometric algorithm (groups tracks
  by net+layer, splits into horizontal/vertical/other, sorts, and merges collinear
  runs). **Dead** — zero callers anywhere in the repo (below). This is the one
  candidate in the file that would otherwise read as a genuine porting target; it is
  excluded solely because nothing calls it.

## Candidate kernels considered and rejected

1. **`PCBGeometry` (the `cKDTree` wrap)** — this is the file's real compute, and it is
   a library boundary, not a port. `packages/temper-drc-rs/src/validation.rs:19-22`
   already documents the same call for `scipy.spatial.ConvexHull` in this exact crate
   ("NOT reimplementable — Qhull is not bit-reproducible outside scipy — those calls
   stay Python-side"), and the KTD8 (`edt` crate rejected, scipy EDT kept) / KTD9
   (`scipy.sparse.linalg.spsolve` kept, ~5e-13 K measured parity) verdicts recorded in
   `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md:145-146` are the
   same shape of call for a different scipy subsystem. `cKDTree.query_ball_point`'s
   ball-tree traversal and floating-point tie handling are not published as a bit-exact
   algorithm; reproducing scipy's exact output (including on the boundary-radius ties
   the DRC clearance checks depend on) would require reimplementing scipy's own
   ball-tree C code, which is out of proportion to a 403-line file and has no measured
   perf case made for it here.
2. **`Track.midpoint`/`.to_segment`/`.is_diff_pair_with`, `Pad.rot_rect`** — each is a
   single-line field wrap/average/comparison. They are live, but every one of them
   returns or reads `Point`/`LineSegment`/`RotatedRect` from
   `router_v6/constraints_geometry.py`, not this file. Two ways to port them: (a)
   duplicate `Point`/`LineSegment`/`RotatedRect` inside `temper-drc-rs`, which is the
   divergent-copy trap already called out in this crate's own `py_hypot` history (two
   copies of `hypot`'s NaN/inf guard order disagreed until one was found and fixed
   in-source, `pymath.rs:277-289`), or (b) depend on `temper-geometry`'s types before
   that sibling migration has landed and stabilized. Neither is safe to do from this
   task in isolation, and there is no separable numeric kernel here in any case — it's
   struct construction.
   Independent confirmation that the migration program itself treats these classes as
   Python-side plumbing rather than a porting target: `connectivity_validation.py`
   already moved its real per-net compute into *this exact crate*
   (`temper-drc-rs::connectivity_validate_net_py`,
   `packages/temper-drc-rs/src/deterministic_connectivity.rs`), and its differential
   test (`tests/deterministic/stages/test_connectivity_validation_rust_differential.py:37-47`)
   crosses the FFI boundary by flattening `Pad`/`Track`/`Via` into plain tuples
   (`_flatten_pads`/`_flatten_tracks`/`_flatten_vias`) rather than porting the
   dataclasses or their glue methods. That is the established pattern for this file's
   live consumers, and this triage follows it rather than deviating.
3. **`merge_collinear_tracks`** — real geometry (collinear-run merging with an
   epsilon-tolerant touch test), but it has zero callers repo-wide (below), so there is
   nothing to port; a Rust kernel with no call site would be unverifiable and
   unmaintained. Flagged as a RETIRE candidate for the residual-decision ledger, not
   deleted in this pass (see Process notes).
4. **`Via.conductive_layers`, `Pad.conductive_layers`, `Pad.radius`,
   `PCBGeometry.get_geometry_by_id`** — each is dead (below); nothing to port.

## Dead-code check

Checked by import edge, not substring match, per the false-positive risk this program
has already hit twice (`net_class_manager.py`'s `is_power_net` collision;
`channel_skeleton.py`'s import-edge miss) — grepped every absolute
`from temper_placer.router_v6.constraints_spatial_index import ...` site, every
relative-import variant (`from .constraints_spatial_index`, `from ..router_v6...`) repo-
wide, and then grepped each specific symbol name for callers outside its own
definition:

- `merge_collinear_tracks` — **zero callers anywhere in the repo** (only its own
  definition matches a repo-wide grep for the name).
- `PCBGeometry.get_geometry_by_id` — **zero callers**.
- `Via.conductive_layers` / `Pad.conductive_layers` — **zero callers** (grepped
  `conductive_layers` repo-wide; only the two definitions match).
- `Pad.radius` — **zero callers on this class.** A repo-wide grep for `.radius` inside
  `router_v6/`, `deterministic/`, and `tests/` turns up several hits, but every one
  resolves to a *different* `.radius` on a *different* type — the exact same-name
  false-positive class already documented in this program (`net_class_manager.py`'s
  `is_power_net`): `deterministic/geometry/via_placement.py:24` reads `pad.radius` on
  its own local `PadInfo` dataclass (defined in that file, not imported from here);
  `router_v6/placement_suggestions.py` and its oracle read `region.radius` on a
  congestion-region type; `tests/wave4_phase2/_core_py_oracle.py` and
  `io/_parse_engine_py_oracle/_parse_modules.py` read `.radius` on core-contract `Pin`
  and kicad-parse pad objects, respectively. None of these import
  `constraints_spatial_index.Pad`.
- Everything else in the file (`Track`, `Via`, `Pad` core fields, `add_track`/
  `add_via`/`add_pad`, `rebuild_index`, the three `query_*_near` methods, `clear`,
  `is_diff_pair_with`, `to_segment`, `midpoint`, `rot_rect`) — **live**, confirmed
  against callers in `router_v6/constraints_drc_oracle.py`,
  `deterministic/stages/connectivity_validation.py`,
  `deterministic/stages/setup.py`, and the two `deterministic/stages/test_*` files
  that import this module directly.

## Why this stays Python for now

Same shape as the program's other recorded scipy-boundary verdicts: the file's one
real kernel (`PCBGeometry`'s `cKDTree` queries) is a call into a C library whose exact
output isn't reproducible from a from-scratch Rust ball-tree without matching scipy's
internal traversal and tie-breaking bit-for-bit, and this crate has already made that
same call for `scipy.spatial.ConvexHull` (`validation.rs:19-22`). The rest of the file
is either dead (five members, confirmed above) or single-line struct glue over
`temper-geometry`-owned types that this task is explicitly scoped away from
duplicating.

## Process notes

- No Rust code was written; `packages/temper-drc-rs` is unchanged by this branch, so
  no build was run (nothing to compile).
- `df -g /Users/bennet` was checked before starting: 26 GB free, above the 8 GB floor.
- `merge_collinear_tracks`, `get_geometry_by_id`, `Via.conductive_layers`,
  `Pad.conductive_layers`, and `Pad.radius` are confirmed dead but were **not**
  deleted in this pass — this task's scope is the Rust migration decision, not a
  Python retirement PR, and five concurrent Wave-4 agents are touching adjacent
  `router_v6`/`deterministic` files today; deleting here risks a conflict with work
  in flight elsewhere. Recorded as a RETIRE recommendation for the residual ledger
  (`docs/wave4-verdicts.yaml`, not edited by this branch) to pick up.
- No PBT/differential/oracle scaffolding was added, since there is no kernel to pin.
