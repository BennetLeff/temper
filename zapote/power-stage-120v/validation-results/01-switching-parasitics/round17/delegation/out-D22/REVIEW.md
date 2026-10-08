# D-22 evidence review

**All 16 source cases pass numerical qualification, and the proposed stage exceeds the 6 dB modeled-margin target after reserve.** The evidence report is ready for review. Hardware release remains conditional on the component, leakage, PE-layout and coupled-system qualifications below.

The review was performed sequentially in the main session, following the repository's instruction to keep subagent work inline. It is **not an independent or cross-model review**. The selected lenses were correctness, evidence fidelity, failure handling, testing, maintainability, performance and project scope. Code reuse/simplicity was checked before this pass; the exploratory topology variants remain because their recorded outputs must be reproducible.

## Corrections made during review

- A newly completed transient can precede its receiver analysis. The summary now marks it as awaiting analysis rather than inheriting a prior result or omitting it.
- Numerical acceptance requires both cycle and step comparisons, with every expected scenario/terminal present exactly once. Missing, duplicate or failed coverage cannot pass; the negative tests exercise this directly.
- The bleed-resistor tolerance, temperature and stated aging multipliers are stacked multiplicatively. The result remains below the proposed one-second discharge target under the stated assumptions.
- A raw/AC replay with no evidence cannot report PASS.
- Resampling now uses a D-22-owned transfer cache. A rerun proved that this scope correction preserved every previously recorded resampling number exactly.
- Fresh campaign output can be directed to a separate directory, preserving historical captures and their provenance.
- Failure labels distinguish significant-line, weak-line and missing-comparison checks. Cycle evidence is retained even when an adjacent timestep aborts; a missing step comparison still prevents qualification.

- Receiver CSV packaging verifies every member byte and the archive hash before deleting loose copies. Repacking refuses to drop previously archived members; replay checks both archive coverage and content.

- Receiver-margin coverage also requires every scenario and each of L/N/terminal/DM/CM exactly once before taking minima. A missing worst-case record cannot silently improve a reported margin.

## Requirements coverage

| Brief item | Evidence | Status |
| --- | --- | --- |
| Reproduce D-19's two settled cases first | `reproduction.json`, baseline raw captures | Pass, bit-identical spectra |
| Complete the 16-case source envelope | `envelope-0.5-results.json`, `envelope-summary.json` | Pass; final spectral qualification covers all 16 points |
| Establish timestep convergence / resolve 6.72 dB movement | `resampling.json`, `convergence-summary.json`, refinement and diagnostic campaigns | Pass under the declared finite-refinement criterion; failed trials remain indeterminate |
| PE-referenced QP/AV and separate modes | Every-line CSVs and complete-envelope tables | All 16 selected sources qualified; CW-equivalent detector and physical-model limitations remain |
| ≥6 dB added-stage margin | `envelope-summary.json` combines coverage and margin gates | Pass over all 16 cases and declared sensitivities: minimum AV margin 8.28 dB after reserve |
| Orderable parts, ratings, losses, damping, bleed, cost and size | `PARTS.md`, budget, harmonic losses, passive damping and packing evidence | Conditional proposal; hot biased choke, capacitor ripple and complete-appliance leakage/loop checks remain |
| Outside both FEM regions | `placement.json`, source mesher boxes and plot | Pass for the stated reservation and unchanged original geometry |
| Output-only scope and licensed-model exclusion | Git diff, input hashes and provenance manifest | Input hashes match the required base; staged scope is checked before each publication |

The model's physical qualifications remain material: both nonlinear legs use D-19's leg-A matrix, temperature is 27 °C, receiver transfer is one-way, the rectifier state is fixed, and RF parasitics include typical fits and sensitivity assumptions. Finite sweeps are not component bounds, and the CW detector estimate does not cover bursts or mains modulation.
