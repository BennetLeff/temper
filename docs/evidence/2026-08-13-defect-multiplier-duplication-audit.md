# Defect-multiplier duplication audit — 2026-08-13

<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=true -->

Base commit `a3fbaff37afd739b72f2b109847813b30ceb8e88`
(`origin/fix/board-schematic-resync`); `dirty=true` because this doc is
itself part of the changeset it describes (the measurement, the
consolidations, and the gate all land together).

## Why

Four defect families investigated the same day were all the same shape:
the same logic independently reimplemented in several places, so one
defect became N.

1. Pin/pad resolution (`_net_pad_positions`) — PR #1177/#1180: 10 call
   sites carried the identical first-match-collapse bug; 3 were
   independent copies of a function literally named `_net_pad_positions`.
2. Net-name boundary matching — PR #1162/#1174: the `(?:^|_)kw(?:$|[\d_])`
   shape existed in 3 independently-maintained matcher families plus 3
   more inline copies; a hyphenated net fell through to a class with
   `creepage_mm = 0.0`.
3. Footprint bounds — PR #1179: `fp_circle` dropped from bounds
   independently in Rust and in the pinned Python oracle; the differential
   test agreed only because both arms shared the bug.
4. Rotation units — PR #1167: `initial_rotation` (a 0–3 quadrant index,
   not degrees) misread at multiple sites, five of them carrying their own
   defensive comment about the trap.

This audit (a) measures how much of this pattern remains, (b) classifies
each finding as accidental (should be one shared implementation) or
deliberate (a pinned oracle / intentional cross-check, must stay
duplicated), (c) consolidates the highest-value accidental cases, and (d)
adds a fail-closed gate — `scripts/check_duplicate_predicates.py` /
`scripts/duplicate_predicate_registry.py` — so a new copy of a
consolidated predicate is a named CI failure, not a rediscovery six
months later.

## Method

Two parallel read-only research passes (agent forks, instructed not to
edit files) plus direct grep/AST verification of every claim before acting
on it: (1) re-derive the current state of the four named families
post-fix, to avoid redoing PR #1177/#1180/#1162/#1174/#1179/#1167's work;
(2) a broader name-frequency + docstring-fragment sweep for undocumented
duplication elsewhere in the Python+Rust tree. One research pass made an
unauthorized file edit while sharing this worktree's live filesystem
(mid-investigation, despite an explicit read-only instruction) — it was
reverted, and the same consolidation was then independently re-derived,
verified (differential check against ~30 net names plus the real test
suite), and re-applied deliberately. Noted here because it is itself a
small instance of this doc's own theme: an unreviewed second copy of a
"fix" is not automatically trustworthy just because it looks plausible.

**A name-based sweep systematically undercounts.** The first pass of the
`point_to_segment_distance` count (5 sites) missed a 6th production Rust
copy, `fixed_copper.rs::point_segment_distance` — renamed with no
underscore between "point" and "segment" specifically so a `grep
point_to_segment` search does not find it. That copy turned out to be
**deliberate** (see below) — but the fact that a rename hid it from the
same search technique that (per the motivating PR #1180) already missed
copies of `_net_pad_positions` once is the sharpest evidence in this audit
that name-based duplicate search is not sufficient on its own.

## Ranked findings

| # | What's duplicated | Copies | Agree today? | Class | Status |
|---|---|---|---|---|---|
| 1 | `point_to_segment_distance` (degenerate-segment epsilon) | **12 total.** 4 accidental Rust kernels beyond the canonical (`creepage_check.rs` + `drc_constraints_geometry.rs`, `geometry_kernels.rs`, `temper-constraint-compiler/mod.rs`, `temper-rust-router-core/pruning.rs`) behind 3 different pyo3 bindings Python calls into; 6+ pinned Python oracles (deliberate); 1 renamed Rust copy in `fixed_copper.rs` (`point_segment_distance` — no underscore, evades name search; **deliberate**, explicitly documented) | **NO — the 4 accidental Rust kernels diverge.** Thresholds `1e-10`, `1e-12`, exact `==0.0`, canonical `denom==0.0‖!finite` — a segment whose squared length falls between two thresholds takes a different branch. None carry a documented rationale, unlike `fixed_copper.rs`'s explicit "these deliberately disagree" header | 4 Accidental (undocumented) + 1 Deliberate (documented) + 6 Deliberate (pinned oracles) | **Flagged, not fixed** (the accidental 4 touch creepage/DRC-adjacent Rust geometry; out of this change's safety-value scope). `fixed_copper.rs`'s copy registered as deliberate so it is never mistaken for part of the accidental cluster |
| 2 | `_net_pad_positions` (net → world pad coordinates) | 3 independent Python copies (`_pipeline_grid.py`, `capacity_check.py`, `bundle_analyzer.py`) + 1 already-delegating import site (`_pipeline_route.py`) | **NO — diverged.** `_pipeline_grid.py` applied rotation (`pin_world_position`); `capacity_check.py` and `bundle_analyzer.py` summed `comp.initial_position + pin.position` directly, silently skipping rotation, wrong for 148/169 (87.6%) of this board's components | Accidental | **Consolidated this PR** — SSOT `core.pin_geometry.net_pad_positions`; gated |
| 3 | `_is_hv_keyword_match` / HV-keyword word-boundary regex | 4 production-ish copies: `clearance_engine._kw_boundary_match` (already delegating), `creepage_check._is_high_voltage_net` (already delegating, different kernel), `clearance_check._is_hv_keyword_match` (was independent), 2 pinned oracles | Agreed on production semantics (verified: 0 mismatches across ~30 net names spanning the documented false-positive history) but `clearance_check.py`'s copy was an independent, hand-typed 4th implementation of an already-consolidated mechanism | Accidental (the 2 oracle copies are deliberate) | **Consolidated this PR** — `clearance_check.py` now delegates to `temper_geometry.kw_boundary_match_py`; gated |
| 4 | `kw_boundary_match_py` — Rust symbol SHADOWING, not just duplication | 2 (`trace_width_assignment.rs:90`, `via_clearance.rs:410`), both registered under the identical pyo3 name in `lib.rs` | Behaviorally equivalent today (verified), but this is worse than a divergence: one registration silently overwrites the other (`via_clearance`'s wins, `trace_width_assignment`'s is dead code with its own tests giving false confidence) | Accidental | **Flagged, not fixed** — Rust registration bug, not Python-AST-scannable by this PR's gate; needs its own Rust rebuild+test cycle |
| 5 | `_point_to_segment_distance` in `physics/thermal_fdm.py` | 1 dead copy (own 1e-18 threshold, never called — `_trace_to_cell_coverage` calls the Rust kernel directly) | N/A — unreachable | Accidental (dead code) | **Deleted this PR**; gated against reintroduction |
| 6 | `get_rules_for_net` | 2 (`router_v6/net_batching.py:709`, `router_v6/stage0_data.py:106`) | **Unverified** — not byte-compared this PR | Unclassified | **Flagged, not fixed** — first-priority correctness follow-up (same shape as finding #3's family: net-name → class rules) |
| 7 | `load_allowlist` (CI gate config loader) | 14 near-identical loaders across `scripts/check_*.py` | Low-stakes boilerplate, not compared | Accidental, low priority | **Flagged, not fixed** — `scripts/_lib/gate_allowlist.py` is a plausible target |
| 8 | Pinned Python oracles (`_*_py_oracle.py`) vs. their Rust ports | 167 files | By design, not compared 1:1 (that is the point) | **Deliberate** | Already registered + gated: `scripts/oracle_hashes.json` / `scripts/check_oracle_hashes.py` (decision 2026-08-06). Shared-bug risk (the #1179 shape) is real and NOT mechanically checkable by that gate — flagged as a tracked, open risk in `scripts/duplicate_predicate_registry.py`'s `DELIBERATE_DUPLICATE_REGISTRIES`, not assumed away |
| 9 | **Oracle registry's own discovery glob has a confirmed blind spot** | `packages/temper-placer/tests/io/_parse_engine_py_oracle/` — a PACKAGE (8 files: `kicad_parser.py`, `_parse_nets.py`, `_kicad_types.py`, `kicad_metadata.py`, `_parse_zones.py`, `_parse_modules.py`, `__init__.py`, `_parse_board.py`, `_parse_tracks.py`) pinning the KiCad parse engine's pre-migration reference | `update_oracle_hashes.py`'s `ORACLE_GLOB = "_*_py_oracle.py"` only matches FILES named exactly that; none of these 8 files individually match, so the whole package is invisible to `check_oracle_hashes.py`'s drift detection | N/A — a gap in the deliberate-duplication registry itself | **Flagged, not fixed** — highest-priority follow-up this audit found; widening a sibling gate's glob is outside duplicate-predicate scope and needs its own verification pass for other multi-file oracle packages |

Findings #1, #4, #6, and #9 are the highest-value *unfixed* items. #1
because 4 of its copies are already demonstrably diverged and two feed
creepage/DRC-adjacent code. #4 because a silently-shadowed Rust symbol is
strictly worse than an obviously-duplicated one — it looks single-source
from the Python side. #6 because it is exactly the net-classification
shape that produced finding #3 and the original PR #1162/#1174 defect,
and was not verified this PR only for time, not because it looks safe. #9
because it means the registry this whole audit leans on for "the oracle
universe is covered" has a confirmed hole — exactly the #1179 risk this
task asked to check for, found in the meta-layer rather than in a single
oracle.

## Bonus finding (not a duplication case, found during the sweep)

`packages/temper-placer/src/temper_placer/validation/results/battery_run.py::
_board_bounds` reads `board.origin_x` / `board.origin_y` via
`getattr(..., 0.0)` defaults. If the real `board` object never carries
`origin_x`/`origin_y` attributes (not verified against every board
construction path this PR), this function always silently returns the
origin regardless of the board's real placement. Not a duplication issue,
not touched, but worth a human look — flagged here rather than dropped
because "worth reporting even if you do not fix it" applies to correctness
findings encountered en route, not only to duplication findings.

## The four named families: post-fix state (this audit's own verification, not re-litigated)

- **Pin/pad resolution** — `Component.get_pin` (not `get_pin_occurrences` —
  no such name exists in this tree) is the Rust match-predicate SSOT
  (`temper-design-bundle/src/netlist_contracts.rs`), already delegated to
  by Python via pyo3. The remaining accidental duplication was in *world
  position* resolution (finding #2 above), not pin/pad *matching* — a
  different bug in the same historically-named function, now fixed.
- **Net-name boundary matching** — `temper_geometry.kw_boundary_match_py`
  is the Rust SSOT; `clearance_engine._kw_boundary_match` was already the
  established Python delegate. Finding #3 closes the last unregistered
  hand-typed copy in production code.
- **Footprint bounds** (PR #1179) — see companion research; not
  re-investigated in depth this PR beyond confirming the relevant oracle
  is present in `scripts/oracle_hashes.json`'s registry (already gated).
- **Rotation units** (PR #1167) — not re-investigated in depth this PR;
  no new independent copy of `initial_rotation` misuse was found during
  the broader sweep.

## What this PR does NOT do (scoped out, stated plainly)

- Does not touch the 4-way accidental `point_to_segment_distance`
  Rust-kernel divergence (finding #1) — consolidating creepage/DRC-adjacent
  geometry kernels is explicitly outside this change's hard constraints (no
  clearance/creepage/safety-value edits). A safe follow-up would
  differentially test all 4 against the canonical kernel across the
  degenerate-segment boundary first, the same falsification step issue
  #987's own spike did before merging its 3. `fixed_copper.rs`'s own
  deliberately-different copy is registered, not touched.
- Does not fix the `kw_boundary_match_py` Rust symbol shadowing (finding
  #4) — a registration bug, not a Python-scannable duplicate; needs a
  Rust rebuild+test cycle this PR did not undertake.
- Does not verify or consolidate `get_rules_for_net` (finding #6).
- Does not migrate the 14 `load_allowlist` copies (finding #7).
- Does not touch any pinned oracle (finding #8) or its Rust counterpart.
- Does not widen `update_oracle_hashes.py`'s discovery glob to cover the
  `_parse_engine_py_oracle/` package (finding #9) — flagged as the
  single highest-priority follow-up, but fixing a sibling gate's core
  discovery logic is outside this PR's duplicate-predicate scope and
  needs its own audit for other multi-file oracle packages first.
- Does not add type-level enforcement. This is a structural/lint problem
  (an independent reimplementation is a valid Python function with a
  valid type signature; nothing about its type stops it from computing
  the wrong thing) — a type-system claim here would be a stronger claim
  than the mechanism actually supports, so none is made. The gate
  (`check_duplicate_predicates.py`) plus the SSOT is the enforcement.

## The gate

`scripts/duplicate_predicate_registry.py` registers `ConsolidatedFamily`
entries (accidental duplication, now fixed — SSOT + `scan_paths` + the
call every legitimate delegate must make) and `OpenFinding` entries
(identified, deliberately not yet fixed). `scripts/check_duplicate_
predicates.py` AST-scans every `ConsolidatedFamily`'s `scan_paths` for a
definition of its `def_names` whose body does not call its
`delegate_call_name` — a new independent copy, or a regression back to
inline logic. Registered in `gate_input_registry._CI_SCRIPT_SURVEY` and
wired into `.github/workflows/python-tests.yml`.
`scripts/tests/test_check_duplicate_predicates.py` proves: a synthetic
independent reimplementation is caught and named (not just counted, for a
2-copy case); a delegating shim is silent; the real repo is currently
clean; and the standard anti-vacuity backstops (missing SSOT, empty scan
paths, unparseable file) fail closed rather than reporting a false clean.
