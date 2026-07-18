---
title: "test_regression_drc.py's golden-board gates never wired zones=/loop_components= into solve_placement(), masking real DRC-quality regressions behind an UnresolvedConstraintRefsError"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: high
symptoms:
  - "temper_placer.placer.cp_sat.encoder.UnresolvedConstraintRefsError: Constraint(s) reference names absent from the netlist/zones/loops -- HV_ZONE, MCU_ZONE, ISOLATION_BARRIER, commutation_loop, gate_drive_high, gate_drive_low"
  - "Both test_golden_board_drc_regression and test_golden_board_routing_drc_regression failed identically, before ever reaching their real placement-fixable/routing-introduced violation-count assertions"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - temper-placer
  - cp-sat
  - drc-regression
  - config-drift
  - stale-test
  - hidden-by-ci
---

# Golden-board DRC regression gates never wired zone/loop names into `solve_placement()`

## Problem

`test_golden_board_drc_regression` and `test_golden_board_routing_drc_regression`
(the repo's "territory-level truth gate" for placement/routing DRC
quality) both failed with `UnresolvedConstraintRefsError` before ever
reaching their real assertions. The PCL config
(`configs/constraints/temper_induction_cooker.yaml`) declares zones
(`HV_ZONE`, `MCU_ZONE`, `ISOLATION_BARRIER`) and named critical loops
(`commutation_loop`, `gate_drive_high`, `gate_drive_low`) that its own
constraints reference -- but both tests called `solve_placement()` with
only `extra_constraints=`, never `zones=` or `loop_components=`, so none
of those names could resolve. `validate_constraint_refs()` correctly
fail-closed on this (by design -- a silently-dropped constraint is
exactly the "looks applied but isn't" failure mode it exists to catch).

## Investigation

Fixed the **zones** half directly: `config_loader.load_constraints()`
already returns `constraints.zones` as a list of `Zone(name, bounds,
...)` objects -- the same data the CLI's `loop_runner.run()` call site
already converts to `{z.name: z.bounds for z in zone_objs}`. Added a
`_load_zones()` helper mirroring that pattern and passed `zones=` into
both `solve_placement()` calls.

The **loop names** half has no equivalent direct wiring available in
this codebase: `solve_placement()`'s only loop-resolution fallback
(`_resolve_loop_components`) auto-detects loops from netlist topology
using auto-generated names, which never match this config's
manually-curated names (`commutation_loop`, `gate_drive_high`,
`gate_drive_low`). There is no established helper anywhere in the
codebase converting `constraints.critical_loops` (net-name lists) into
the `{loop_name: [component_refs]}` shape `solve_placement()` needs --
building one correctly would require resolving which components touch
each loop's declared nets, a nontrivial cross-reference this
investigation did not attempt to invent without a clear existing
pattern to follow. Downgraded via
`encoder._UNRESOLVED_REF_POLICY = "warn"` for this specific gap instead
-- the officially sanctioned escape hatch per
`UnresolvedConstraintRefsError`'s own message. Note this is patched
directly on the already-imported `encoder` module object via
`monkeypatch.setattr`, not via the `TEMPER_UNRESOLVED_REF_POLICY`
environment variable -- that constant is read once at `encoder.py`'s
import time, so setting the env var from inside a test has no effect
once the module is already imported elsewhere in the same pytest
session (the same class of mock-timing gotcha found in
[`router-integration-tests-assumed-array-based-cpsatplacementresult.md`](router-integration-tests-assumed-array-based-cpsatplacementresult.md)'s
`ortools` mock).

## What This Revealed (Not Fixed)

With the wiring bug fixed, both tests now run their real CP-SAT
solve + kicad-cli DRC pipeline successfully (previously impossible --
they crashed before reaching it) and fail on their **actual, substantive
assertions**:

- `test_golden_board_drc_regression`: expects ≤15 placement-fixable DRC
  violations, measured **42** (`clearance: 8, copper_edge_clearance: 2,
  lib_footprint_mismatch: 32`).
- `test_golden_board_routing_drc_regression`: expects 0
  routing-introduced DRC violations, measured **261**
  (`clearance: 61, shorting_items: 48, solder_mask_bridge: 79,
  tracks_crossing: 72, diff_pair_gap_out_of_range: 1`, offset by
  `unconnected_items: -84`).

**This is a genuinely different class of finding than every other bug in
this session's batch** -- not a stale test or a hidden wiring gap, but a
real question about whether current placement/routing quality on this
specific golden board has regressed relative to these committed
thresholds, or whether the thresholds were miscalibrated from the start.
Answering that requires the same kind of rigorous investigation as
[`production-board-courtyard-area-exceeds-usable-board-area.md`](../architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md)
(is this a solvable quality problem, or a structural
board/component-density limit?) or a `git bisect`-style history dig to
find when the numbers first exceeded threshold -- explicitly **not**
attempted in this pass, since loosening the thresholds without that
investigation would repeat exactly the mistake this whole session has
been rooting out elsewhere (making a gate pass without understanding
why it was failing).

## Resolution

**Partially fixed.** The wiring bug (zones never passed, loop-name
resolution never had an available fix) is fixed/downgraded as described
above -- both tests now run to completion instead of crashing on setup.
**Not fixed**: the real violation-count thresholds these tests exist to
enforce are currently failing (42 vs 15, 261 vs 0). CI will still show
these two tests red, now for a real, substantive reason rather than a
test-harness bug. This needs a dedicated investigation (regression
bisection or requalification of the thresholds against current reality)
as a follow-up, not folded into this fix.

## Why This Matters

This is the most consequential test-fix in this whole batch: two tests
explicitly documented as the repository's "territory-level truth gate"
for DRC quality had been unable to run their actual check *at all* since
whenever this wiring gap was introduced -- a real regression in
placement or routing DRC quality could have been silently accumulating
with zero detection, hidden first by CI never reaching this test file
(see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)),
and then by the tests crashing on setup even when CI did reach them.

## Prevention

- **A "golden board" regression gate is only as good as its ability to
  actually run.** A setup-time crash (config↔netlist drift) is
  functionally identical to the gate never existing -- neither catches a
  quality regression. Treat a gate that has never successfully completed
  its real assertion with the same urgency as one that's failing.
- **Module-level constants derived from environment variables
  (`_UNRESOLVED_REF_POLICY = os.environ.get(...)`, read once at import
  time) cannot be overridden from inside a test via
  `monkeypatch.setenv`/`os.environ[...] = ...`** once the module is
  already imported elsewhere in the process -- patch the module
  attribute directly instead.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
- [`docs/solutions/test-failures/router-integration-tests-assumed-array-based-cpsatplacementresult.md`](router-integration-tests-assumed-array-based-cpsatplacementresult.md)
  — sibling finding with the same "env var read once at import time"
  mock-timing gotcha.
