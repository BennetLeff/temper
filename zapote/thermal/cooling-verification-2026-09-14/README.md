# Cooling design verification

The [design and disposition](../bridge-cooling.md) retain all four bridge
current-capacity findings. This work selects cooling parts and tests an explicit
requirement set; installed assembly performance and powered hardware remain
unqualified.

## Recorded checks

- `live-run.log`: 20 Gmsh/Elmer cases completed. Raw geometry, meshes, SIFs,
  commands and solver measurements are in
  `../evidence/bridge-cooling-2026-09-14/` (466 retained files).
- `workspace-tests.log`: 372 Zapote workspace tests passed. The subsequent
  final thermal/harness tests, including the final review regressions, passed
  **215 tests**, recorded in `focused-tests.log`.
- `clippy.log`: both changed crates, all targets, `--no-deps -- -D warnings`,
  passed. A broader attempt encountered existing warnings in unchanged DRC/ERC
  code; those were not suppressed or included in the scoped pass claim.
- `import-boundaries.log`: 5 contracts kept, 0 broken. The checkout needed its
  `packages/temper-placer/src` on `PYTHONPATH`; an initial missing-package
  instrument error was not interpreted as a pass.
- `regen-check.log`: repository derived artifacts are consistent.

`common-units.tar.gz` retains the complete seven-unit native/common run.
`summary.json`, `power-entry.json` and `suite-identity.json` are also directly
available. KiCad CLI 10.0.6 ran with its native Framework Python and required
macOS session access. All seven native ERC/DRC/parity checks and common coverage
checks passed. Six units remain INDETERMINATE; power-entry remains FAIL with
four `DRC.PFC.BRANCH_COPPER` findings. Its five thermal checks contain three
conditional numerical/design passes and two INDETERMINATE applicability/
sensitivity findings. The command's nonzero exit records that engineering
outcome, not a successful qualification.

The final suite reported `suite_changed_during_run: false`; all recorded suite
source hashes were compared with the current files. The dirty-start flag is
retained honestly. An earlier run overlapped a test edit and correctly reported
source drift; it is not the accepted receipt.

## Regressions and review fixes

[Completed code review](review/review.json): Ready to merge, no actionable
findings. The optional native-runner regression-test gap and the reasons for
its disposition are recorded in [review-disposition.md](review-disposition.md).
This verdict concerns the harness change, not hardware qualification.

The cooling profile is bound to exact source contract bytes and the reviewed
heatsink/two-fan assembly. Rehashed part substitutions, below-ambient passive
reservoirs, overflowing budgets, edited summaries and missing process records
are rejected. Refinement must compare the same physics on a connected
three-resolution chain; temperature, power and node-count defects have negative
controls using the retained reference cases. Existing analytic/PDE reference
checks remain in the thermal crate.

The new and old studies share exact PFC-current binding. Five thermal rules
are mandatory for power-entry independently of whether its hook emits a report.
The direct real-board integration checks a valid replay and a mismatched PFC
branch current; the native common run exercises the production runner.

An existing process-timeout test failed under concurrent load because its child
could write before a delayed timeout check. Its descendant now announces that
it started, then waits for a release file written only after timeout returns.
The assertion tests surviving descendants without assuming a 20 ms scheduling
guarantee. Production timeout handling was unchanged.

The simplification pass removed duplicated contract defaults/parsing and shared
current binding. Validation guards were preserved. No original 40-case evidence,
PCB geometry, ERC rule or current-capacity ceiling was relaxed.
