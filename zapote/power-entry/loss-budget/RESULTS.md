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

## Candidate screen: one requirement, three lines

The candidate screen now runs inside the common runner
([`pfc_candidates.rs`](../../packages/zapote-harness/src/pfc_candidates.rs),
rules `ERC.PFC.CANDIDATE_SOURCE_BINDING`, `ERC.PFC.CANDIDATE_COVERAGE`,
`THERMAL.PFC.CANDIDATE_CLOSURE`). It fixes a common required power — the ideal
CCM input power at 120 V RMS and 15 A true RMS, **1,796.4 W** — and derives the
current each line needs to carry it, enforcing the 15 A ceiling. Full write-up:
[candidates.md](candidates.md).

| Line | Required input RMS | 15 A ceiling | Reachable input power | Shortfall | Bridge drop at 1.05 V |
| --- | ---: | --- | ---: | ---: | ---: |
| 108 V | 16.658 A | **binds** | 1,617.1 W | **179.3 W** | 28.309 W |
| 120 V | 15.000 A | met | 1,796.4 W | 0 W | 28.304 W |
| 132 V | 13.645 A | met | 1,796.4 W | 0 W | 25.730 W |

| Candidate | Screen | Anchor |
| --- | --- | ---: |
| Keep bridge, improve thermal path | open; moves heat, not loss | 28.304 W at 120 V, 26.956 W/V |
| Larger / lower-drop passive bridge | blocked on sourcing an exact part | 2.696 W per 0.1 V |
| Parallel passive bridges | inconclusive, not rejected | constant-drop identity holds; 450 vs 225 W/ohm slope |
| Active rectifier | unresolved at one threshold | break-even 62.9 mOhm per device vs 50 mOhm 25 °C max |
| Boost-stage optimization | largest unresolved term | 33.898 W overlap at 50 ns edges |

The strongest result is that switching behaviour can move the heat budget by
tens of watts, which is larger than any bridge-architecture question here. The
bridge drop falls as line voltage rises (25.730 W at 132 V against 28.304 W at
120 V) because a fixed required power needs less current at a higher line, and
the 108 V line cannot meet the requirement inside the ceiling at all.

No candidate is promoted, no architecture is ranked, and total loss and cooling
margins stay absent. Hot junction temperature, degraded airflow, startup and
fault behaviour, measured switching waveforms and delivered-output efficiency
are named as required inputs rather than modelled as cases; only the three line
voltages appear as operating points.

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

The candidate screen's own priority order, for the same sequence: pursue
candidates 1 and 5 together — keep the passive bridge as the baseline and
establish its practical heatsink path while resolving the boost MOSFET and its
switching losses. They are compatible and they attack the two things the screen
identified: the concentrated bridge heat and the largest unmeasured term. This
is baseline-model completion, not board variants. Compare alternatives at a
common required **output** power with the 15 A input limit enforced and any
reduced output reported, rather than at a common input current, and revisit a
different bridge architecture only if loss, temperature or enclosure
requirements justify it.

## Evidence and validation

- Common run: `../../validation/runs/loss-budget-candidates-20260916/`
  (`evidence/common-run-candidates.txt`). All seven units have native checks
  PASS; all overall verdicts remain INDETERMINATE; the suite did not change
  during the run. Power-entry contains the 18 planning cases, the five-candidate
  screen (three line operating points each at a common required power, five named
  required inputs, 29 unresolved terms), six required loss/candidate rules and
  the exact executable/source hashes.
- The runner must be built with `--release`. The power-entry stage replays about
  1.2 GB of retained FEM meshes, and a debug build had not finished that stage
  after 25 minutes; the same run in release completed all seven units in about
  five minutes. Two invalid instrument runs are retained locally under
  `../../validation/runs/candidates-invalid-*` (KiCad Python without `pcbnew`;
  no main-display access). Both failed closed rather than producing a
  plausible result. `validation/runs/` is Git-ignored, so those are local
  records.
- Workspace tests, release profile: **509 passed, 0 failed, 1 ignored**
  (`evidence/workspace-tests-candidates.txt`). That is the earlier 498 plus the
  10 candidate-screen tests and one further document-pin test in
  `pfc_loss_budget` (3 to 4). The 8 focused tests after the pin repair also
  passed, including drift rejection for every embedded document.
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
