# PFC model assurance and electrical-loss options

Read the [integrated results and next experiment](RESULTS.md).

This investigation follows the corrected switching model at `80ae56830`.
The user authorized Luna workers to implement harness protections and investigate
all three electrical options. The target is a supported comparison and executable
model-assurance gates; no candidate is approved merely because its estimate is
lower, and no PCB or cooling redesign follows automatically.

## Parallel ownership

| Work | Owned deliverables |
| --- | --- |
| Harness safeguards | Rust assurance/report/rule wiring and focused regressions; `harness/` evidence |
| Existing MOSFET and characterized drive | `existing-drive/` |
| Replacement MOSFET with existing controller drive | `replacement-fet/` |
| Replacement MOSFET and changed driver | `replacement-pair/` |
| Coordinator | This comparison contract, result synthesis, integration and authoritative verification |

Workers use separate sparse worktrees based on the same commit. The harness
worker alone builds during the parallel investigation; all builds use the shared
Zapote release target, not the legacy PyO3 target. Research workers must preserve
source conditions and unknowns in their handoffs. The coordinator inspects actual
changes, tests integrated behavior and records the final evidence.

## Common comparison contract

- Anchor the nominal case to 120 Vrms, 15 A true RMS input ceiling, 180 µH,
  the authored approximately 389.615 V bus and 129.107 kHz switching frequency.
  Use exact source-derived values when calculating; rounded prose is not input.
- Include 108 and 132 Vrms cases. A fixed-current sweep has different powers and
  is a sensitivity, not a like-for-like efficiency comparison. Equal-output
  comparisons must state the output target and solve the required input; if
  incomplete losses prevent that calculation, leave the result unresolved.
  The historical 1,796.416 W figure is ideal-model input power, never DC output
  or pan power. Report derating when the input-current ceiling binds.
- Derive on/off event currents and branch RMS from the maintained current model;
  do not substitute one for another or use an event mean as a peak bound.
- Identify the exact MOSFET, controller/driver, gate network and bias. Pin sources
  to revision/page/curve/test conditions. The 15 V circuit supply does not itself
  establish the actual high gate output or plateau current.
- Distinguish measured, manufacturer typical/guaranteed, derived and assumed
  inputs. Evaluate supported temperature cases; temperature labels alone do not
  create an electrothermal solution. Do not extrapolate a gate-charge or energy
  curve silently to a different current, bus voltage, resistance or temperature.
- Keep conduction, overlap, output-capacitance and gate-network terms disjoint;
  source Eon may already contain capacitance/recovery energy. Unknown terms stay
  null. A partial estimate is not a total or a physical upper bound.
- Compare operating suitability, voltage/current limits, startup/shutdown,
  driver interfaces, overshoot/EMI risks, footprint/layout consequences and
  orderable identity. Dated stock/price claims need direct distributor evidence;
  inaccessible data remain unknown.

## Acceptance of this investigation

The harness must distinguish numerical correctness, physical applicability and
qualification in machine-readable findings reached through the common runner.
Independent-reference disagreement, invalid bindings and deliberately corrupted
production inputs must be rejected; unsupported assumptions must prevent an
acceptance claim even if quadrature tests pass. Retained evidence must identify
model/source inputs and the tests actually run.

Each electrical option supplies a report and structured candidate evidence.
A rejected option is a valid result when a demonstrated incompatibility explains
why. A promising but uncertain option supplies the decisive missing input and a
reproducible sensitivity rather than a fabricated precise answer. Final selection
requires supported evidence at the intended operating conditions.
