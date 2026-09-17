# Loss-budget checkpoint — 2026-09-16

The loss estimator is integrated into the common Rust runner. This checkpoint
completes the first planning calculation, not the whole power-entry cooling or
electrical closeout. No CAD or retained FEM model was changed.

At 120 Vrms, 15 A true RMS, nominal 180 µH and 129.107 kHz, the ideal CCM model
reports 1,796.416 W input. That is not delivered DC power or measured efficiency.

| Term | Planning loss W | Limitation |
| --- | ---: | --- |
| GBJ bridge | 28.304 | Constant 1.05 V per conducting diode; extrapolated test point |
| Boost inductor DC winding | 4.500 / 5.915 | Copper at 20 / 100°C; excludes core and AC loss |
| Shunt | 2.273 | Reference resistance +1%; excludes hot TCR |
| Bleeders | 0.506 | Nominal resistance and bus |
| Bus divider | 0.150 | Nominal resistance and bus |
| Energized relay coil + dropper | 0.499 | 15 V, nominal resistance; excludes contact and driver |
| **Partial sum** | **36.231 / 37.646** | **Incomplete, not a bound** |

The independent MOSFET *design sensitivity*, not an exact-part prediction:

| Assumed each switching edge | 50 mΩ conduction + overlap W | 100 mΩ conduction + overlap W |
| --- | ---: | ---: |
| 20 ns | 20.651 | 27.742 |
| 50 ns | 40.990 | 48.081 |
| 100 ns | 74.888 | 81.980 |

These switch figures omit Eoss, SiC capacitive commutation and gate-drive loss.
The slower-edge assumptions plus the partial sum already exceed the previous
105 W electronics allowance. This is evidence that switching behavior matters
to the design decision; it is not evidence that the actual board dissipates
that amount. Total-loss and cooling-margin fields are deliberately null.

## What to do next

1. Resolve `STW65N65DM2` to an exact manufacturer order code, updating authored
   source and native identities together. ST records for `STW65N65DM2AG` and
   `STW63N65DM2` are candidates, not approved substitutions. Use the selected
   part's gate-charge/Coss data with the actual UCC28180 and 10 Ω gate network.
2. Model switch transitions and SiC commutation across current and temperature;
   add inductor core/AC loss and frequency-dependent capacitor loss. Bench
   waveforms remain a separate validation obligation.
3. Assign losses to actual heatsink/PCB/air paths and establish installed
   airflow. Revisit the prior imposed 60°C board boundary using that assembly,
   then close parasitics, precharge/shutdown timing and the auxiliary supply.

## Evidence and validation

- Common run: `../../validation/runs/loss-budget-20260916/`. All seven units
  have native checks PASS; all overall verdicts remain INDETERMINATE. Source
  files stayed unchanged during the run. Power-entry contains all 18 planning
  cases, three required loss rules and the exact executable/source hashes.
- Workspace tests: **498 passed, 0 failed, 1 ignored** before the final
  document-pin repair. After that repair: **8 focused tests passed** including
  drift rejection for every embedded document. No false claim of a second
  complete workspace run is made.
- Regular workspace Clippy completes. Strict `-D warnings` fails in unchanged
  `gate_drive.rs`, `power_stage_models.rs`, `domain_clearance.rs` and
  `stackup.rs`; no new-module warnings. Raw diagnostics are retained.
- Import boundary gate PASS: 5 contracts kept, 0 broken, 0 new violations
  after supplying the checkout's Python package path. Initial environment
  failures are retained, not relabeled as passes.
- `make regen` and `make regen-check` PASS; no generated artifacts changed.
- Focused review found unauthenticated document hashes; all three are now
  explicitly pinned and mutation-tested. The review receipt and final
  disposition are under `../../../docs/reviews/loss-budget-20260916/`.
- Code review: harness-native fallback — CE review orchestration terminated
  degraded; a separate native Luna adversarial review completed, adjudicated
  its wiring/current concerns against the actual source, and retained no
  findings. The initial degraded receipt remains available.

The simplification pass reused the existing digest helper, hoisted invariant
bus/frequency calculations and clarified document coverage. Broader parser
refactoring, test caching and centralizing independent part applicability
checks were deliberately omitted: small overhead does not justify coupling
the new loss model to the validator it independently checks.

No runtime service is deployed. Future evidence regeneration must execute
the common runner and retain INDETERMINATE until the listed model inputs are
resolved; a green native DRC is not thermal acceptance.
