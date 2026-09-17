# G0 checker and coordinator acceptance specification
Created: 2026-09-17

This is a required future Rust implementation, not a claim that current campaign
JSON is executable or machine-enforced. G0 freezes the implemented schema and
CLI before fan-out. It must reject malformed data before physics comparisons.

## Admission and identity

- Required dispatch fields present; unique task/attempt; authorized output paths;
  UTC budget; source/model/checker/binary hashes all resolve to actual bytes.
- Strict schema version and known enum/unit values. Reject unknown or duplicate
  JSON keys, NaN/Infinity, missing required fields, negative physical magnitudes
  where disallowed, and null values disguised as zero.
- Expected case IDs form an exact set. Missing, duplicated, relabeled, extra or
  skipped-without-reason cases cannot be counted as a completed grid.
- Inputs actually used match requested inputs and case labels, including topology,
  frequency, L, driver paths, bias, source curves, temperature and solved currents.
- A source-backed value requires matching source conditions and exact part suffix;
  an explicitly assumed mismatch remains conditional and cannot become applicable.
- Every raw log/deck/source/summary is content-bound. Recompute numerical summaries
  from raw evidence through the maintained truth function, not a cheap proxy.
- Cross-task dependencies bind accepted immutable receipts; a filename such as
  'winner.json' without a hash is not a dependency identity.

## Physics and accounting checks

- Recompute current moments independently of the summary; use waveform-domain
  checks across continuous phase, not only favorable sampled points. Confirm
  true input RMS includes ripple once. Bound the matched-power solve and residual.
- Check input-power contract, low-line derating, power balance and correct
  comparison-group membership. Comparisons at unequal processed power are blocked.
- Check CCM validity. A different conduction mode requires a separately supported
  model. Interleaved phase currents and input ripple need their own model.
- Check per-term units and source conditions, disjoint accounting, finite totals,
  total=sum(complete terms), Pout=Pin-loss and 0<=efficiency<=1 when computable.
  If a term is unknown, totals and efficiency are absent, not fabricated.
- Validate source interpolation domain, monotonic axes where required and extraction
  uncertainty. No extrapolation across missing gate bias/current/temperature data
  without a declared separate sensitivity classification.
- Refinement checks use identical physics and justified absolute+relative tolerances.
  G0 records tolerance derivation from numerical precision/convergence and separate
  physical uncertainty; never widen tolerances because a candidate failed.
- Require independent known-answer checks for solver changes; replay of the same
  implementation and hash closure alone do not establish physical correctness.
- FEM, if later used: independently verify geometry/material/boundary transfer,
  mesh convergence and energy balance, preserving all boundary assumptions.
  A heatsink reservoir temperature is not a measured surface or junction result.

## Required deliberately bad cases (all must fail their intended check)

| Mutation | Expected rejection |
| --- | --- |
| Rename 129 kHz output to 90 kHz without changing applied config | CASE_INPUT_MISMATCH |
| Multiply an applied L by 1000 while keeping a retained summary | RAW_SEMANTIC_MISMATCH |
| Edit a log/deck/solver version after manifest generation | EVIDENCE_IDENTITY_MISMATCH |
| Recompute hashes after changing a log, retaining the old summary | RAW_SUMMARY_MISMATCH |
| Replace a PDF with HTML; cite the wrong part suffix/revision | SOURCE_INVALID or SOURCE_INAPPLICABLE |
| Mark 63 µJ at -5/+18 V as measured at 0/+15 V | SOURCE_CONDITION_MISMATCH |
| Assign P/V to true RMS without the waveform solve | CURRENT_CONTRACT_MISMATCH |
| Add triangular ripple a second time to existing true RMS | CURRENT_MOMENT_MISMATCH |
| Use switch RMS as instantaneous double-pulse current | EVENT_CURRENT_MISMATCH |
| Duplicate one favorable case to conceal a missing hot case | CASE_CENSUS_MISMATCH |
| Feed NaN through a tolerance comparison | NONFINITE_INPUT |
| Interpret an unsupported low-load CCM case as zero loss | MODEL_DOMAIN_MISMATCH |
| Use 132 V/15 A as same-power counterpart to 120 V/15 A | COMPARISON_CONTRACT_MISMATCH |
| Drop a required bridge/core/aux term, then publish total | INCOMPLETE_ASSEMBLY_TOTAL |
| Add Eoss to Eon that already includes that energy | OVERLAPPING_LOSS_TERMS |
| Sum loaded-driver ICC and full gate-charge loss twice | OVERLAPPING_LOSS_TERMS |
| Count driver/cooling consumption outside the declared input boundary | POWER_BOUNDARY_MISMATCH |
| Label Rds×2 as measured 125 °C without a source | UNSUPPORTED_TEMPERATURE_CLAIM |
| Use natural-convection thermal current as saturation current | RATING_TYPE_MISMATCH |
| Reuse single-boost moments for a totem-pole circuit | TOPOLOGY_MODEL_MISMATCH |
| Change a thermal boundary while calling it mesh refinement | PHYSICS_CHANGED_DURING_REFINEMENT |
| Use a stale finalist receipt after updating model source | DEPENDENCY_STALE |
| Change INDETERMINATE to PASS in handback only | VERDICT_MISMATCH |

Error labels are proposed stable diagnostic categories, not existing API names.
Add positive controls to prove valid conditional results remain consumable. Unknown
physics must yield a valid INDETERMINATE result rather than rejecting all research.
Prove the bad cases fail the real acceptance path, not only an unused helper.

## Reviewer decisions

The coordinator independently reads exact source conditions and at least the
control, worst stress and highest claimed improvement cases. Source-only tasks
need equation/condition review even without solver output. Read every hard-failure
case before pruning its architecture; distinguish model/tool gaps from real limits.

Accepted handback outcomes:

- ACCEPTED_CONDITIONAL: consistent evidence, bounded claims; eligible for conditional
  comparison in its group, not hardware acceptance.
- ACCEPTED_INFEASIBLE: source-supported violated constraint with valid applicable
  analysis; may prune only the affected design/condition.
- ACCEPTED_GAP: useful documented missing evidence/model support; no numeric rank.
- REJECTED_EVIDENCE: malformed/stale/incorrect/misleading result; retain, repair
  within a new attempt budget or mark unresolved.

The coordinator writes its receipt separately. Never overwrite the worker report
or promote agent consensus into an external oracle. G0 must demonstrate a valid
baseline, a valid conditional candidate, an honest unknown and at least the
mutations above before numerical workers begin.
