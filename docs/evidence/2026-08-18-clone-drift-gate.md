<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-afcc97cd16c4d5843, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "A clone-drift gate: catching 'one file cloned from another, then diverging' (the STITCH_TRACE_WIDTH_MM / _blocked() incident)"
date: 2026-08-18
module: scripts
tags: [ci-gate, clone-drift, ast-similarity, power-islands, ground-plane, zone-pour]
problem_type: gate-design
status: in-progress
---

# Clone-drift gate

**Status: IN PROGRESS**, committed incrementally per this project's survival
rule (a worktree with no commits is destroyed on stop).

## Task

Build a gate that catches "one file cloned from another and then
diverging" — distinct from `scripts/check_fact_registry_drift.py` (catches
one scalar FACT duplicated across homes) and
`scripts/check_duplicate_predicates.py` (catches a NEW copy of an
ALREADY-consolidated predicate). The motivating incident: `_power_islands.py`
was cloned from `_ground_plane.py`, and on 2026-08-17 three separate
divergences were found between them in one day (`STITCH_TRACE_WIDTH_MM`
0.3 vs 1.0mm; a false "identical" comment; `_blocked()`/via-drop-stub
missing a foreign-copper collision check that `_ground_plane.py` had
already been fixed to include). Both files are now fixed on main
(`d33c0446e` #1143, `7979a0ee1` #1329, `4d7373eca` #1332).

This document will be appended incrementally as the gate is built,
measured, and wired in.

(To be continued in this same file.)

## Progress log

- 2026-08-18: stub committed. Registry (`scripts/clone_drift_registry.py`)
  and gate (`scripts/check_clone_drift.py`) written and passing against the
  real repo (3 registered pairs, all clean): `power_islands_ground_plane_
  blocked` (sim 0.877, floor 0.80), `power_islands_ground_plane_emit_segment`
  (sim 0.883, floor 0.80), `zone_pour_clearance_creepage_required` (sim
  0.949, floor 0.85). Mechanism: normalized-AST structural similarity
  (Name/Attribute-base/Constant/arg leaves collapsed to placeholders,
  control-flow shape and call names preserved), difflib.SequenceMatcher
  ratio, explicit hand-reviewed registry (mirrors
  `duplicate_predicate_registry.py`'s `ConsolidatedFamily` shape) rather
  than a full-repo sweep gating every PR. A one-off discovery sweep
  (`scripts/find_clone_pairs.py`, directory-scoped pairwise AST-similarity
  scan, NOT wired into CI) found this pair plus a second real family:
  `zone_pour_clearance.py::ZonePourClearanceTable.required` /
  `zone_pour_creepage.py::ZonePourCreepageTable.required` (0.949 similarity,
  the creepage module's own docstring calls itself the clearance module's
  "Twin"). Registered both; the zone_pour pair's ~5% gap is a documented,
  permanent, safety-relevant divergence (different unmatched-pair
  fallback: 0.2mm floor vs 0.0 = no requirement) — the `#1332`-shaped
  "legitimate and permanent" case the task brief asked the registry to be
  able to hold apart from the `#1329`-shaped accidental one.
- Non-vacuity tests: `scripts/tests/test_check_clone_drift.py`, 27 tests,
  all passing under `uv run pytest` (the repo's real toolchain — the
  system `python3`/pytest is broken in this environment, unrelated to
  this change: a conda-installed `typeguard` plugin fails to import
  under Python 3.9). Direct two-sided proof
  (`TestSyntheticRegistryFailsThenPasses`): a synthetic clone pair where
  twin B is missing two of twin A's three obstacle-check branches (the
  exact `_power_islands.py` pre-#1332 shape) is a VIOLATION
  (`live_similarity < floor`); the SAME registry/floor with B reconciled
  to A is CLEAN — same tmp_path tree, only the file contents change.
  Also proved: renames/literal changes are invisible to the score (that
  is `check_fact_registry_drift.py`'s job, not this gate's — pinned
  explicitly so the two gates' scope never blurs); a missing branch and
  a different `raise` target (`GateError` vs `ValueError`) both move it;
  qualname ambiguity (two sibling nested defs sharing one dotted path)
  fails closed as a TOOL ERROR rather than silently picking one — the
  `scope_anchor`-matches-3×-caught-in-#1320's-own-draft lesson, applied
  to qualname resolution instead of a regex anchor.
- CI wiring: two steps added to `hygiene-gates` ("Repo Hygiene & Import
  Gates") in `.github/workflows/python-tests.yml`, immediately after the
  duplicate-predicate consolidation gate. `hygiene-gates` is listed in
  `.github/required-checks.json`'s `required_contexts` and carries no
  `continue-on-error` anywhere except one pre-existing, separately
  tracked `ruff` lint step — every other step in the job, including
  these two, is a real, unmasked gate (a step failure fails the job).
  Proved the gate actually RUNS on a PR shaped like this changeset, not
  merely that the job exists: `.github/required-checks.json`'s
  `catch_all_paths` includes `scripts/**` and `.github/workflows/**` —
  both hit by this changeset — and `job_should_run`/
  `classify_changed_paths.py`'s own rule is "a path matching
  `catch_all_paths` runs EVERY path-conditional job", so `hygiene-gates`
  runs regardless of its own narrower `paths: ["packages/**"]` entry in
  `job_triggers`. Confirmed mechanically: `check_required_checks.
  validate_trigger_manifest` + `validate_job_conditions` both pass
  cleanly against the edited workflow (no drift between the manifest and
  the workflow's own `if:` conditions).
- `scripts/manifest.yaml`: added entries for `check_clone_drift.py`,
  `clone_drift_registry.py`, `find_clone_pairs.py` (`check_manifest_gate.
  py` requires one per top-level `scripts/*.py` file — verified clean
  against the new files; its one remaining failure,
  `check_placement_pair_creepage.py`, predates this change, commit
  `d5882072d`, a sibling's file, not touched here).
- Board `pcb/temper.kicad_pcb` sha256 unchanged throughout:
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`.
  `power_pcb_dataset/drc_ceiling.json` and `scripts/oracle_hashes.json`
  untouched (`git diff` scoped to this task's commits touches only the
  workflow file, the evidence doc, and the 4 new/modified `scripts/`
  files).

## The clone pairs found, and what was and was not registered

**Registered (9 pairs, all CLEAN as of 2026-08-18):**

| Pair | Live similarity | Floor | Shape |
|---|---|---|---|
| `_ground_plane.py`/`_power_islands.py` `_blocked()` | 0.880 | 0.80 | REGRESSION GUARD — the flagship incident (#1329/#1332), fixed |
| `_ground_plane.py`/`_power_islands.py` `_emit_segment()` | 0.879 | 0.80 | REGRESSION GUARD — same incident |
| `zone_pour_clearance.py`/`zone_pour_creepage.py` `.required()` | 0.951 | 0.85 | LEGITIMATE, PERMANENT — creepage module's own docstring calls itself clearance's "Twin"; the ~5% gap is a documented, safety-relevant fallback difference (0.2mm floor vs 0.0 = no requirement) that must NOT be closed |
| `_sexp` × 2 (copper_net_consistency↔domain_partition, ↔footprint_drift) | 1.000 | 1.00 | 5-file s-expr mini-parser family found by the discovery sweep; GateError sub-family |
| `check_netlist_freshness` × 2 (same trio) | 1.000 | 1.00 | Same sweep finding |
| `_sexp` (gen_pcb_skeleton.py ↔ gen_schematics.py) | 1.000 | 1.00 | ValueError sub-family |
| `RouterV6Result`/`PathfindingResult` `.completion_rate` | 0.836 | 0.75 | REGRESSION GUARD — both `success/total` zero-guarded identically, no known reason to diverge |

**Found, reported, deliberately NOT registered as a ClonePair:**

- The **cross-family** gap between the GateError trio
  (`check_copper_net_consistency.py`/`check_domain_partition.py`/
  `check_footprint_drift.py`) and the ValueError pair
  (`gen_pcb_skeleton.py`/`gen_schematics.py`) — both raise a different
  exception type at the identical structural position (a real,
  discovery-sweep-confirmed divergence: 1.000 → 0.992 once the
  call-target-preserving AST refinement was added). NOT registered
  because each exception type is correct for its own script's contract
  (gate scripts signal failure via `GateError`; plain generator scripts
  do not have that concept) — there is no floor that would both accept
  this AND still catch a real accidental divergence inside either
  sub-family.
- `STITCH_TRACE_WIDTH_MM` (incident #1 in the task brief) — a scalar
  fact, not a clone-drift shape; `check_fact_registry_drift.py`'s job
  (see `default_via_diameter_mm` for the same via-geometry-constant
  shape already covered there).
- The false "identical" code comment (incident #2) — prose, no AST
  exists for a natural-language claim. See "What this does NOT catch" in
  `clone_drift_registry.py`'s own docstring: the only mechanical defence
  is deleting the false claim and replacing it with something checkable
  (a `Fact` or a `ClonePair`), which `_power_islands.py`'s current header
  comment already does (cites this registry instead of asserting
  equality in prose).
- `heuristics/*.py` `apply`/`name`/`description`/`priority` methods
  (`organizational.py`, `structural.py`, `style.py`, `topological_init.py`,
  `base.py`) — the discovery sweep's highest-`jaccard` candidates by
  shared-name count, but investigated and rejected: these are sibling
  subclasses of `Heuristic` implementing a common interface (expected
  polymorphism — each `apply()` genuinely does something different), not
  copy-paste clones. Registering these as a "must stay similar" floor
  would be actively wrong (it would punish two heuristics for correctly
  doing DIFFERENT things). Reported here as a class of false positive
  the mechanism must not chase, not registered.
- `validation/drc.py`/`validation/spice.py` `KiCadDRCValidator.validate`/
  `NgspiceValidator.validate` (0.84 similarity) — same shape: sibling
  implementations of a common `Validator` interface, both wrapping a
  subprocess call. Investigated briefly, judged likely-polymorphism
  rather than clone-drift, and NOT registered (time-boxed — flagged as a
  candidate a future sweep review should re-examine, not asserted safe).

## Mechanism chosen, and why

Evaluated three options before settling:

1. **Exact textual/byte comparison.** Rejected immediately — the task
   brief's own prediction held: every real pair here differs in
   docstrings/comments even when logic is identical (e.g. the
   `check_netlist_freshness` trio, which cites different CI run IDs in
   otherwise-identical prose). A byte-diff gate would be red on every
   trivial edit.
2. **Purely semantic equivalence** (e.g. symbolic execution, property
   testing against both twins). Rejected as not tractable — these
   functions call into Shapely geometry, in-memory `pcb` parse state, and
   net-topology data structures; there is no practical way to prove two
   arbitrary such functions compute the same thing for all inputs, and
   building one would dwarf the rest of this task.
3. **Normalized-AST structural similarity + an explicit, hand-reviewed
   registry of accepted floors** (the task brief's own suggested shape,
   evaluated and adopted, then sharpened once during evaluation — see
   below). Chosen. Mirrors `check_geometry_primitive_duplication.py`'s
   existing "structural, not textual" choice for one fixed function
   shape, generalized to arbitrary registered pairs, and mirrors
   `check_duplicate_predicates.py`'s existing "explicit registry, not a
   whole-repo sweep gating every PR" convention for a `ConsolidatedFamily`
   -- both already-established patterns in this codebase, not new
   invented ones.

**One refinement made during evaluation, not assumed at the start**: the
first version of `normalize_function_ast` collapsed every `Name` node
(including a `Call`'s own target) to a placeholder, matching
`check_geometry_primitive_duplication.py`'s "variable renames don't
count" philosophy — but that made it structurally blind to `raise
GateError(...)` vs `raise ValueError(...)` at the same position (both are
just `Call(func=Name(...))` to the collapsed eye). The discovery sweep
surfaced a REAL instance of exactly this (the s-expr parser family, see
above), so the normalizer was changed to preserve `Call` TARGETS (bare
name and attribute) while still collapsing every other `Name`
occurrence — verified this sharpens the score (1.000 → 0.992 for the
real divergence) without reintroducing false positives on ordinary
variable renames (`TestNormalizationIgnoresRenamesAndLiterals`, still
passing 1.000 for pure renames).

## What could not be made reliable, stated plainly

- **A brand-new, never-registered clone pair.** This gate only checks
  `PAIRED_FUNCTIONS`. `scripts/find_clone_pairs.py` finds candidates but
  is a human-run discovery tool, not wired into CI (a full O(n²)
  all-pairs sweep is too slow/noisy to run on every PR, and even the
  directory-scoped version would need a human to distinguish real clones
  from expected-polymorphism false positives — see the `heuristics/*.py`
  rejection above). This is the same limitation
  `check_duplicate_predicates.py`'s own docstring states for finding a
  new duplicate-predicate family: "a measurement/audit exercise... not a
  mechanical gate."
- **A false natural-language claim** (incident #2 in the brief). No AST
  exists for prose; not mechanically checkable by any means evaluated.
- **A bug present identically in both twins.** A similarity comparison
  by construction cannot see a shared defect — the exact failure mode
  the 2026-08-13 point-to-segment-distance audit found for
  oracle-pinned Rust kernels. This gate proves the twins have not
  drifted apart; it says nothing about whether either is correct.
- **Convergence, not just divergence.** A similarity FLOOR only catches
  a score falling below it; if a future edit makes the two
  `zone_pour_clearance`/`zone_pour_creepage` `.required()` bodies MORE
  similar (e.g. both silently start returning `0.0` for an unmatched
  pair, quietly erasing the 0.2mm clearance floor), the score would rise
  above the floor and this gate would report clean — a real,
  safety-relevant regression a similarity-floor mechanism cannot see by
  construction. Stated explicitly in that pair's own registry `notes`.
