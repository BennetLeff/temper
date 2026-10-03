# D-22 evidence review

**The evidence report is reviewable; the filter is not qualified for release.** D-22's full-envelope timestep requirement remains open. The report must keep the conditional enclosure recommendation separate from any ≥6 dB acceptance claim.

The review was performed sequentially in the main session, following the repository's instruction to keep subagent work inline. It is **not an independent or cross-model review**. The selected lenses were correctness, evidence fidelity, failure handling, testing, maintainability, performance and project scope. Code reuse/simplicity was checked before this pass; the exploratory topology variants remain because their recorded outputs must be reproducible.

## Corrections made during review

- A newly completed transient can precede its receiver analysis. The summary now marks it as awaiting analysis rather than inheriting a prior result or omitting it.
- Numerical acceptance requires both cycle and step comparisons, with every expected scenario/terminal present exactly once. Missing, duplicate or failed coverage cannot pass; the negative tests exercise this directly.
- The bleed-resistor tolerance, temperature and stated aging multipliers are stacked multiplicatively. The result remains below the proposed one-second discharge target under the stated assumptions.
- A raw/AC replay with no evidence cannot report PASS.
- Resampling now uses a D-22-owned transfer cache. A rerun proved that this scope correction preserved every previously recorded resampling number exactly.
- Fresh campaign output can be directed to a separate directory, preserving historical captures and their provenance.

## Requirements coverage

| Brief item | Evidence | Status |
| --- | --- | --- |
| Reproduce D-19's two settled cases first | `reproduction.json`, baseline raw captures | Pass, bit-identical spectra |
| Complete the 16-case source envelope | `envelope-0.5-results.json` | Pass for initial endpoint/cycle-RMS screen; not spectral qualification |
| Establish timestep convergence / resolve 6.72 dB movement | `resampling.json`, `convergence-summary.json`, refinement and diagnostic campaigns | Open: step sensitivity and finer-step aborts remain |
| PE-referenced QP/AV and separate modes | Every-line CSVs and complete-envelope tables | Provisional calculations; failed numerical cases do not receive qualified margins |
| ≥6 dB added-stage margin | `envelope-summary.json` combines coverage and margin gates | Not established over the envelope |
| Orderable parts, ratings, losses, damping, bleed, cost and size | `PARTS.md`, budget, harmonic losses, passive damping and packing evidence | Conditional proposal; hot biased choke, capacitor ripple and complete-appliance leakage/loop checks remain |
| Outside both FEM regions | `placement.json`, source mesher boxes and plot | Pass for the stated reservation and unchanged original geometry |
| Output-only scope and licensed-model exclusion | Git diff, input hashes and provenance manifest | Input hashes match the required base; staged scope is checked before each publication |

The model's physical qualifications remain material: both nonlinear legs use D-19's leg-A matrix, temperature is 27 °C, receiver transfer is one-way, the rectifier state is fixed, and RF parasitics include typical fits and sensitivity assumptions. Finite sweeps are not component bounds, and the CW detector estimate does not cover bursts or mains modulation.
