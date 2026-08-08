<!-- provenance: commit=02abba561939a0cbb6af7d963ba4e6bc9d6b414d dirty=false (re-pointed from the pre-merge branch SHA, orphaned by squash-merge, to PR #702's merge commit -- "feat(placer): production real-board loader + CLI validator_input wiring (#617) (#702)") -->

# CLI optimize path REQ-SAFE-01 validator_input wiring — issue #617 second half

**Date:** 2026-08-05
**Branch:** `feat/cli-validator-input` (worktree `/tmp/temper-cli`).
**Issue:** #617 second half — the CLI optimize path
(`packages/temper-placer/src/temper_placer/cli/__init__.py`, the
`solve_placement` call) could not pass `validator_input` because the
validator-shape placement + voltage-domain map were not constructible there:
the only loader (`tests/requirements/safety/_real_board_fixture.py::
load_real_board_placement`) lived in the test tree. The review note in PR
#595 recorded the blocker precisely: "placement/domains not constructible
there — `load_real_board_placement` only exists in tests; half-wiring would
raise `ValueError`".
**Board measured:** `pcb/temper.kicad_pcb` + `elec/domain_manifest.yaml` +
`elec/build/default.net` on `origin/main`. **`pcb/**` and `elec/**` untouched.**

## 1. Options evaluated

**(a) Extract the loader into production and wire `validator_input` in the
CLI optimize path.** The fixture's loader is importable logic; the task
brief prefers this when the extraction is clean, with the fixture importing
from the production module so there is one loader.

Feasibility findings (all measured, not assumed):

1. **A production `.net` parser already exists.** The fixture parsed the
   compiled netlist with `scripts/check_domain_partition.py::parse_netlist`
   (a gate script production cannot import). Production already owns a
   self-contained netlist parser,
   `temper_placer.validation.netlist_reconciliation.parse_design_netlist`
   (the "deliberate copy" convention that module documents). On the real
   netlist it is **byte-equivalent** to the gate's parser: 0 net->refs
   mismatches, 0 ref->pins mismatches across all 162 compiled nets (verified
   2026-08-05).
2. **Production manifest reading is established.** `isolation_barrier.py::
   load_domain_manifest_nets` already reads `elec/domain_manifest.yaml`
   directly; the loader follows the same discipline.
3. **The loader core is self-contained.** Pads/rotations/board geometry come
   from `parse_kicad_pcb` (production); the HV/MAINS/DC_BUS mapping, the
   copper-aware proximity check and the stats shape are pure logic.
4. **The extraction is byte-identical when done as a move.** The new
   production loader's output (placement, voltage_domains, stats) was
   compared field-by-field against the pre-refactor fixture on the real
   board: **0 diffs** (158 components, 54 nets, identical proximity
   findings, identical chain-exempt pairs).

**(b) Document a binding decision that the CLI path intentionally stays
unaudited.** Held as fallback; the extraction above made (a) clean, so (b)
was not taken.

**(c) Wire it only if constructible without new abstractions.** The
loader hoist is exactly one production module + a thin fixture wrapper; the
CLI wiring is two call sites. This is (a) with no extra abstraction.

## 2. Choice: (a) — production loader + CLI wiring

**The loader** — `temper_placer/io/real_board.py`:
`load_real_board_placement(pcb_path, manifest_path, netlist_path)` returning
the same `(placement, voltage_domains, stats)` triple the fixture returned,
plus `RealBoardUnavailable` (the availability exception). The fixture
`tests/requirements/safety/_real_board_fixture.py` is now a thin binding of
the production loader to the repo's default paths, preserving the no-arg
3-tuple API every test and evidence script in the repo calls — **one loader,
one derivation**. The `ValueError`-on-missing-keys contract is respected by
construction: the CLI only builds a dict carrying BOTH keys, or None.

**The CLI wiring** — `cli/__init__.py::_build_validator_input(input_pcb)`:

- locates `elec/domain_manifest.yaml` / `elec/build/default.net` by walking
  up from cwd (the CLI's existing repo-root-relative convention);
- calls the production loader;
- returns `{"placement": ..., "voltage_domains": ...}` when constructible,
  prints the "audit armed" line;
- returns `None` and logs `REQ-SAFE-01 validator post-solve audit SKIPPED:
  <reason>` when inputs are unavailable (missing pcb / netlist / manifest)
  or the board has zero domain-classified components — the documented skip.
  The solve then runs **byte-identical** to pre-wiring (the encoder treats
  absent `validator_input` as the documented skip).

Wired into BOTH the `--no-loop` `solve_placement` call (the TODO's literal
location) and the default `PlaceRouteLoop` path (`run(validator_input=...)`
-> `_call_solver` -> every feasible round's `solve_placement`), so the
default command is audited too. After the solve, the CLI prints the audit
buckets (`_print_validator_audit`: hard / intra-footprint / coverage-gap /
geometry_trusted) when the result carries an audit.

## 3. What the audit means on the CLI path — and what it does not

Measured on the real board through the CLI's own path (production config,
unresolved-ref downgrade, 30s solve): **status=optimal,
validator_audit populated, hard=0, intra=0, gaps=405, covered_pairs=0,
geometry_trusted=True**.

The one number that needs a reader's eye: **covered_pairs=0**. The CLI
optimize path generates NO `domain_clearance_` constraints (verified: 0 in
the production config; the loop generates none; only the repair caller
`clearance_repair.py` calls `generate_domain_clearance_constraints`). The
audit therefore classifies every inter-component validator violation as a
**coverage gap** ("pair NOT in the solve's constraint set" — the
solver-validator pair-set alignment finding), and the hard-failure
fail-closed raise can never fire on this path (there is no domain encoding
to be unsound). This is the audit working as designed, not a bug: on the
CLI path it is **additive reporting** — the exact REQ-SAFE-01 validator's
verdict on the optimized placement, including which pairs the optimizer
never constrained. It does not and must not gate the command (failing on
gaps would break every optimize run, since the CLI never constrained those
pairs). The REQ-SAFE-01 *gated* flow remains the repair caller
(`run_clearance_repair_solve`), which generates the domain constraints and
is already validator-wired per round (#523 gap 2, #596/#653); there the
same audit has a non-empty covered-pair set and hard failures are
fail-closed.

The 405 gaps on this solve are themselves a real finding for the board
owner: a bare `temper optimize` run's output is NOT REQ-SAFE-01-compliant by
construction unless the domain-clearance constraint set is added — the CLI
now *says so in its own output* instead of silently shipping an unaudited
placement.

## 4. Verification

- Loader equivalence: production loader vs pre-refactor fixture on the real
  board — placement / voltage_domains / stats **all 0-diff** (158
  components, 54 nets, 11 proximity findings, 6 chain-exempt pairs).
- `_real_board_fixture` consumers unchanged: `test_clearance.py`,
  `test_clearance_copper.py`, `test_runb_audit_lie.py`,
  `test_domain_clearance.py` — all pre-existing failures on main reproduced
  identically; everything else green (81 passed in the safety/domain suite).
- New CLI wiring tests (`tests/cli/test_optimize_validator_input.py`, 5):
  real-board constructible case passes `validator_input` with both keys +
  non-empty placement in both the no-loop and loop paths; loader-unavailable
  and zero-classified-component cases log the skip and pass `None`; audit
  buckets printed when present.
- Real solve through the CLI's own path (function-level, no click/write):
  audit armed (158 comps / 54 nets) -> solve `optimal` -> audit populated
  with hard=0 intra=0 gaps=405 covered_pairs=0 geometry_trusted=True.
- Loop plumbing (`_loop_core` `run`/`_call_solver`): `test_loop.py` +
  `test_compound_loop.py` 34 passed; backward compatible (optional kwarg).

## 5. Gates

- ruff: clean on all touched files.
- import linter: PASSED, 0 new violations.
- typecheck gate: 214 baseline errors / **0 new** (monotonic baseline OK).
- coverage gate: the new loader is exercised by the safety + CLI suites, but
  the gate only measures `tests/core/`, so it is allowlisted with issue
  #617's ticket ref; monotonic-shrink check passed.
- `pytest tests/cli/ + tests/placer/cp_sat/test_validator_audit.py`: 56
  passed, 4 skipped, 1 failed — `test_free_k3_solve_is_inter_clean_and_k3_
  intra_surfaces`, verified to fail identically on clean `origin/main`
  (board-state-dependent; the board is mid-routing, K3-intra blocker
  documented in the fixture's own docstrings).
- Pre-existing failures on main (verified on a clean `origin/main`
  worktree, same board): `test_temper_board_clearance_compliance`,
  `test_runb_validator_fires_headline_pair`,
  `test_runb_validator_total_exceeds_documented`,
  `test_production_board_constraint_count_11571` — all board-state-driven,
  none touched by this change.
- Evidence provenance: this doc carries the commit stamp (PASSED).
- Extensions: `make extensions` fresh (0 STALE), `uv sync --all-packages
  --inexact`.

## 6. Reproduction

```bash
# loader equivalence + real-board audit through the CLI's own path:
python3 - <<'EOF'
from temper_placer.io.real_board import load_real_board_placement
p, vd, stats = load_real_board_placement(
    "pcb/temper.kicad_pcb", "elec/domain_manifest.yaml", "elec/build/default.net")
print(len(p["components"]), len(vd), stats["coverage_ratio"])  # 158 54 0.935
EOF
# CLI wiring tests:
cd packages/temper-placer && uv run --no-sync pytest tests/cli/test_optimize_validator_input.py -q
# real solve with audit (30s, production config; unresolved-ref downgrade is
# only needed because the board is mid-routing vs the config's refs):
TEMPER_UNRESOLVED_REF_POLICY=warn uv run --no-sync python docs/evidence/cli_validator_input_probe.py
# expected: audit armed 158/54; status=optimal; hard=0 intra=0 gaps=405
# covered_pairs=0 geometry_trusted=True
```
