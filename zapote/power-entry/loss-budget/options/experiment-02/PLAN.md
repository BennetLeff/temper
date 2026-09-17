# Experiment 02: C7 and a specified gate-driver interface

Approved scope: investigate C7 with a better-defined supply and driver, retaining
STW65N65DM2AG as a control. This is a source-bound numerical experiment, not CAD
implementation, part selection, measured switching energy or qualification.
Use native Luna authoring with coordinator-owned verification and commits.

## Interface and evidence contract

- Candidate buffer: UCC27624DR, one channel, from retained TI SLUSE44E Rev E.
  Its nominal 12 V supply is a proposed interface, not the AUX_15V label.
  Require 11.4–12.6 V **at the driver pins including loading/transients**.
  A 0.2 V local transient budget is inside that range, not added to it.
  Keep controller VCC separate: proposed 15 V ±5% at its pins. Controller
  startup must clear the datasheet's 12.1 V maximum rising UVLO threshold.
  Neither supply producer nor EN supervisor is implemented by this experiment.
- UCC27624 DC ROH is 5 Ω typical/8.5 Ω max at -50 mA, PMOS only. ROL is
  0.6 Ω typical/1.1 Ω max at +50 mA. The transient parallel NMOS is about
  1.04 Ω, but its assist duration is unspecified. Compare three explicitly
  hypothetical dynamic profiles: full-assist (1.04||5 Ω,0.6 Ω), no-assist
  (5 Ω,0.6 Ω), and DC-max substitution (8.5 Ω,1.1 Ω). These are not
  guaranteed dynamic bounds. Source/sink peak caps are 5 A typical at the
  datasheet's 12 V/10 µF supply/0.1 µF load/1 kHz test, not guaranteed current.
- Use C7 and ST device inputs/source pins from experiment 01. Qg and Rds remain
  their 10 V source points: applying them at 11.4–12.6 V is explicitly an
  approximation. Preserve charge/current/temperature applicability gaps.
- Required eventual circuit: controller GATE -> existing 10 Ω input damping ->
  buffer IN; buffer OUT -> selected gate resistor -> MOSFET gate, short source
  return. This experiment uses one equal external resistor for on/off; the
  driver itself is asymmetric. Preserve TO-247-3 common-source inductance gap.
  No parallel driver outputs. Unused channel must be explicitly disabled.
- Require EN held low during invalid controller/buffer supply, faults and power
  transitions; internal EN pullup is not fail-off. Release only after both
  supplies are valid and a low PWM state has been observed; loss of validity
  must disable without relying on firmware. This is an unimplemented requirement.
- Datasheet local bypass recommendation: 100 nF plus >=1 µF ceramic. Compute
  Qg*f supply-load and Qg/C local droop as conditional screens (10 V source Qg
  does not bound 12 V charge). No driver dissipation/temperature acceptance.

## Numerical experiment

Reuse the maintained Rust switching integrator. Add a minimal asymmetric gate
resistance entry point, retaining the legacy simulate(Config) API, numeric
results and serialized output exactly. New results must serialize both applied
path resistances; an unknown/malformed path cannot fall back to symmetry.
Do not duplicate waveform integration in the harness adapter.

Cartesian grid: 2 parts × 3 lines (108/120/132 V at 15 A input RMS) × 3 driver
voltages (11.4/12/12.6 V) × 3 external gate resistors (2.2/4.7/10 Ω) × 3 driver
profiles above × 3 Qgd multipliers (0.5/1/1.5) × 3 current-transfer charges
(5/10/20 nC) × 2 Rds multipliers (1/2) = **2,916 cases**. Bus 400 V, L180 µH,
source-derived switching frequency, plateau ST6.2V assumed/C7 5.4Vtyp,
loop10nH, timestep0.25ns. Rds×2 is not a temperature prediction.

Retain two experiment-01 nominal controls (ST and C7: gate10V, external10Ω,
source1.5A/sink2A, no additional driver resistance). Compare candidate cases
at120V,12V,4.7Ω,Qgd×1,transfer10nC,Rds×1 for all profiles and show gate-resistor
sensitivity. Keep overlap, Eoss, conduction and gate-network losses disjoint.
Report actual input power and separate mean event currents from switch RMS.
Do not present event-average Ldi/dt as maximum VDS or qualify faster settings.

## Verification and deliverables

- Luna owns pfc_switching.rs asymmetric API/tests, new harness experiment module
  and CLI plus registration. Coordinator owns contract, independent audit,
  source review, results, integrated testing and commit/push. No PR.
- Before changing the switching API, capture legacy numeric/serialized behavior.
  Test equality for symmetric paths, independent asymmetric triangle anchors,
  invalid on/off resistance, swapped paths and transition-pair budget.
- Bind exact source PDF/header/hash, source manifest, part/profile/grid labels
  and actual applied inputs. Check all scalars, recomputed relationships and
  disjoint terms, missing/duplicate/out-of-grid cases and corrupted values.
  Numerical verification may PASS; physical applicability, supply realization,
  sequencing, commutation/overshoot and qualification remain INDETERMINATE.
- Root independently audits every case using closed-form current moments and
  distinct turn-on/off gate currents; no imports of production model functions.
  Retain raw result, audit inputs/output, runtime/source hashes and review.
- Regression-check experiment01 against its retained report bytes. Run relevant
  Rust tests and common check-units because the shared switching solver changes.
  Retain actual outcomes and do not rewrite historical evidence.
- Finish with a concise result/decision report and a concrete source/measurement
  contract for any still-unknown dynamic driver behavior. No bench test implied.
