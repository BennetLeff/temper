# Layout-quality Rust review

## Scope and intent

Review the new `zapote-drc::layout_quality` kernels, JSON runner, tests,
benchmark and documentation against the requested nine tuning checks. Base:
`f11ca939f73e869e6745d33badcf6cc1acc818b2`. Scope is advisory model evaluation,
not automatic native extraction, routing, new insulation thresholds, or board
qualification. Source content hashes and execution evidence are under
`zapote/layout-quality/evidence/`.

## Actionable Findings

No unresolved implementation defects found within the documented model domains.
The implementation pass addressed these concrete review findings:

1. A maximum budget on the assembly metric could misuse a search-radius lower
   bound as an exact clearance. The interface now rejects that direction and
   has a regression test.
2. Overflow in omega*C could erase capacitive reactance and return a plausible
   R-only impedance. Added a failing reproducer and a checked intermediate;
   the regression now passes.
3. Underflow of a positive rectangle overlap could report absent coupling.
   Geometric non-overlap is now distinguished from unrepresentable positive
   area, with a failing-then-passing regression.
4. Successful validation eagerly allocated error messages. Error formatting is
   now confined to error branches; the benchmark records the observed change.
5. Assembly sweep testing originally exercised primarily x-axis translations.
   Added an asymmetric 3D property comparing pair identities and distances
   against exhaustive enumeration.

## Coverage

Applied the ce-simplify-code and ce-code-review correctness, testing,
maintainability, performance, adversarial and project-standards lenses
sequentially in the main session, as the user's AGENTS tool mapping requires.
This is an inline review by the implementing agent, **not an independent
reviewer or cross-model audit**. No subagents or external model were dispatched.

Reviewed signed pickup units and cancellation, complete/correct error propagation,
RLC resonance and antiresonance, copper connectivity/grounding and conservation,
geometry broad-phase completeness, thermal model domains, budget directions,
missing-family semantics, unknown JSON fields, exact board-byte binding, and
CLI exit codes. Tests include closed-form electrical references, randomized
invariants, exhaustive geometry references, and the real native-17 matrix/board
example. No KiCad transforms or Python engineering rules were introduced.

Validated against root AGENTS.md and zapote/AGENTS.md. New logic stays in the
Zapote Rust workspace; public interfaces are documented and model limitations
are explicit. PCB edits, generated legacy DRC ceilings and pyo3 rebuilds do not
apply to this diff.

Validation: 374 workspace tests passed; the final focused run passed 46 kernel
tests, including 15 properties with 2,048 generated cases each. Four CLI tests
passed in the workspace run. New files pass formatting and scoped Clippy.
Full workspace lint/format diagnostics are pre-existing; the Python import gate
could not run because lint-imports is missing. Regeneration and its check pass.

Native-adapter completeness remains outside this kernel implementation: a hash
verifies file identity, not that supplied coefficients were extracted from that
file. The README and runner label this distinction, retain explicit missing
families and avoid a board-pass status. Thermal/field accuracy and operating-case
completeness require separate evidence.

## Verdict

The documented advisory kernels and batch interface are ready for use and review.
The nine-family software API is implemented; this change does not establish a
complete native-board assessment. No unresolved findings require changes to the
kernel scope before delivery.
