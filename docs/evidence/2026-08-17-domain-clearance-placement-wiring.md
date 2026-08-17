<!-- provenance: commit=caec25d61 (main, HEAD at start of this task), worktree agent-a0baf6568e3fdb60f.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged before starting (read-only reference only, never opened for writing).
Spec: docs/evidence/2026-08-17-placer-creepage-constraint-spike.md (commit 659f62759,
branch spike/placer-creepage-constraints -- not yet merged to main at task start; read via
`git show 659f62759:docs/evidence/2026-08-17-placer-creepage-constraint-spike.md`, same
shared .git object store). -->

# Stub: wiring `domain_clearance.py` into the main placement solve

STATUS: in progress. This is a placeholder commit so the work survives a worktree
reclaim; being filled in as the task proceeds.

## Task

Per the spike's §7 recommended design: wire
`domain_clearance.generate_domain_clearance_constraints` into
`solve_placement()`'s default path (both `--loop` and `--no-loop`), encoding the
full classified cross-domain pair set (never a subset scoped to
currently-violating pairs, per spike §6). Measure solve time at the real 12.6mm
PD3 margin on today's board. Determine the J1/K1 verdict: placed legally or
board infeasible. If placement changes, route it and measure connectivity + DRC
before/after.

## Hard constraints in effect

- No edits to `pcb/temper.kicad_pcb`. No edits to `netclass_constraints.py` or
  `gates.py` (`IECCreepageGate`) -- a sibling agent owns those.
- No clearance/creepage/DRU threshold changes. 12.6mm PD3 is settled.
- No new placement committed to the board -- producing and reporting one is in
  scope, committing it is not.

## Plan (filled in as executed)

1. Read `domain_clearance.py`, `_encoder_solve.py`, `cli/__init__.py`,
   `_loop_core.py`, `io/real_board.py` to confirm the spike's call-site claims
   and find the minimal wiring point. DONE -- confirmed exactly as the spike
   describes: `generate_domain_clearance_constraints` had exactly one caller
   in `src/` (`cli/repair_commands.py`'s `repair-unplaced`), never
   `solve_placement`'s main `optimize` path.
2. Wire the constraint generator into `solve_placement`'s default path, gated
   so it always encodes the full classified pair set. DONE. See "What was
   wired" below.
3. Run a full solve at 12.6mm PD3 on the current board; record wall time,
   constraint count, and CP-SAT status (optimal/infeasible/UNSAT core).
   IN PROGRESS (background run started; this doc will be updated with the
   result).
4. If a placement results, route it (scratch `.kicad_pcb` + `.kicad_pro` +
   `.kicad_dru` sidecars) and measure pad connectivity + DRC
   (`--severity-all --all-track-errors`, with and without `--refill-zones`)
   against the stated baseline (63/139 connected, 36/139 genuine multi-pad,
   DRC total 1086).
5. Report findings here; do not commit the new board placement itself.

## What was wired (commit-in-progress)

- `packages/temper-placer/src/temper_placer/cli/_optimize_audit.py`: added
  `_build_domain_clearance_constraints(validator_input, all_refs)`. Reuses
  the SAME `placement`/`voltage_domains` dict `_build_validator_input`
  already loads via `temper_placer.io.real_board.load_real_board_placement`
  (elec/domain_manifest.yaml-backed) for the post-solve audit -- no new data
  load. Calls `domain_clearance.generate_domain_clearance_constraints` with
  `all_refs` = every ref in the netlist being solved (never a
  violation-scoped subset, per the spike's §6 finding that scoping
  regresses 76->217-265 elsewhere). Returns `[]` (byte-identical,
  unconstrained) when `validator_input` is `None` (the existing documented
  skip condition), matching every other optional `solve_placement` input's
  convention in this module.
- `packages/temper-placer/src/temper_placer/cli/__init__.py`: both the
  `--loop` and `--no-loop` branches of `optimize` now call
  `_build_domain_clearance_constraints(validator_input, all_refs)`
  immediately after building `validator_input`, and append the result onto
  `pcl_constraints` before it becomes `extra_constraints`
  (`--no-loop`) / `all_constraints` inside `_loop_core.py::run()`
  (`--loop`, via `pcl_constraints=`).
- No changes to `netclass_constraints.py`, `gates.py` (`IECCreepageGate`),
  or any clearance/creepage/DRU threshold. `domain_clearance.py` itself is
  unmodified -- only its call graph changed.

Confirmed live (from the 12.6mm re-solve run against today's board,
`elec/domain_manifest.yaml`): 158/168 components classified, matching the
spike's own figure; the J1<->K1 pair IS present in the generated constraint
set at 12.6mm (see run output for the exact `because`/`id`). A separate,
expected finding: 8 components (`C6, K1, K2, K3, PS1, T1, T2, U6`) straddle
a DC_BUS<->LV_CONTROL domain boundary WITHIN their own footprint (relays,
transformers, isolators) -- `generate_domain_clearance_constraints` logs
this and cannot, by construction, protect these refs against themselves;
this is documented, not a defect (see `domain_clearance.py` module
docstring). It does not prevent the J1<->K1 (two distinct refs) constraint
from being generated.

(Solve-time/status/J1-K1 verdict and routing/DRC results to follow.)
