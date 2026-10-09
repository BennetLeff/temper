# Round 5 executable control and electrical evidence

This package advances the model from a prerecorded conductance waveform to an
accepted-step electrical simulation calling the real C controller. It is
**diagnostic evidence, not a finished device-level implementation or a power
release**. The commissioning bit is enabled only inside the study harness; the
production target's inhibition is preserved. No hardware was energized.

## What executes

`cosim.c` loads the installed ngspice45.2 shared library and links the current
production `fullbridge_adapter.c` and `energy_supervisor.c`, plus round5
`acquisition.c`, `measurement.c`, `bypass.c`, `supervisor_binding.c` and the
same `protection-closure/isolation.c` compiled into the STM32 target. Only
accepted solver points advance state.
External-source Newton callbacks read held commands; they do not advance the
firmware. Scheduled events are ADC every256µs, supervisor every1ms, and applied
PWM plans every20µs. A 61s **simulated unpowered** prehistory supplies the cold
lockout history; it does not discharge a previously energized physical unit.
RESET is a distinct event at56ms and START at60ms.

ADC channel order is VLINE, VPRE, VOUT, VBUS, VCATCH, VTANK, IPROOF, ILINE. The
harness produces signed24-bit frames with the real CRC and passes them through
the actual parser; it then decodes them using explicitly ideal full-scale gains.
The shared target helper calculates square-integral true RMS using256µs samples,
linear zero-crossing interpolation, and complete45–65Hz-compatible cycles.
The older `sampled_measurement.c` remains an independent historical oracle and
is no longer linked into the plant. `test_shared_measurement.c` checks the
actual target helper against analytic sine/harmonic values and adverse inputs.
There is no ADS131M08 sinc-filter, AMC delay,
noise, calibration, alias rejection, or sensor fault-coverage claim. The
independent continuous-solver integration is logged only as an oracle and is
never used as controller feedback.

Startup qualification uses both measured crest polarities across two complete
valid cycles, with uncertainty-contained source100–140V RMS, inlet≤15A,
VBUS≥0.95|VLINE|, |VPRE|<5V, and |VPRE|/11.875Ω<0.5A. Each model channel has
an explicitly ideal one-ADC-LSB uncertainty; these are not installed calibration
bounds. Catch correlation requires an initially discharged capacitor and a
subsequent measured rise before comparison with the bus. It is proven while charging
and retained during RUN; a falling bus at line valleys must not erase a valid
catch charge-history proof. Proof current must match0.9–1.1×VOUT_RMS/220Ω for a
complete cycle before the real supervisor's additional continuous50ms proof.
Proof/contact withdrawal invalidates their qualifier immediately, without
waiting for the next completed cycle. Both isolated branch POST records pass
through the actual target validator and are consumed by the actual controller.
Their zero uncertainty describes exact simulated resistor values only. Physical
POST measurements, independent contact mirrors, resistor-cold qualification
and auxiliary supply health remain ideal stimuli. No calibrated production
admission contract is thereby demonstrated.

The product path has no FPGA dependency. PWM feedback is explicitly typed as
simulated on-chip register readback, synthesized from the applied plan. It
does not independently measure physical Vgs, ZVS, propagation or overlap.
The model's scope-record ID is UINT32_MAX, a diagnostic sentinel; it is not
a physical commissioning record. Invalid register readback and ADC loss are
negative controls. The shipped target remains uncommissioned and inhibited.

The joined startup includes two source-off contactor self-tests, one-token
admission, first loaded bypass proof, precharge isolation, nonretriggerable
proof-timer rearm and a fresh second proof. KPA/KPB NC mirrors, excitation,
admission gates and discharge qualifiers are ideal diagnostic inputs here.
Native gate timing and target HAL parity require separate evidence. The
audit checks actual joined permission and electrical load, not only the
energy core's RUN enum, and rejects RUN while either isolation contact closes.
The shared wrapper must command a fully qualified RUN within446ms; completed
proof alone cannot extend startup. After that qualification, zero heat demand
retains the session only with live guards and released isolation. Dedicated
cases exercise both pause/resume and proof-without-RUN expiry. Normal STOP
uses an integer-microsecond deadline, checked at exactly1.270s at both step
sizes. The model does not simulate the propagation of the actual hardware
retained-RUN latch; that circuit has a separate pin-driven state review.

## Electrical models and separation of claims

- `averaged.cir`: dynamic source impedance, two independent25Ω precharge
  branches, proof load, selected D22 differential-mode filter, nonlinear
  rectification, bus and catch capacitance, and the controller's applied-phase
  load. The load uses the series-RLC fundamental conductance at50kHz; it is
  energy-consuming and driven by actual applied phase, not a prerecorded PWL
  conductance. This averaged plant **does not simulate tank switching or returned
  tank energy**. Tank zeroes in its results are omitted physics, not zero stress.
- `coupled.cir`: the exploratory switched reduced plant. It became too slow
  after RUN and is not part of the accepted replay. Interrupted/incomplete
  exploratory outputs remain clearly separate from the accepted receipts.
- `energy_ode.rs`: independent finite-energy all-off full-bridge/catch model,
  with explicit tank, bus, catch-L/C and passive losses.64 cases test initial
  tank polarity±640V,85.551A,140µH,0.02/2Ω,2/20µs shutdown delay,
  assumed1/3µH catch loop, and a finite1µs local capacitor short.50/25ns
  refinements track the energy residual. These are deliberately unmeasured
  initial-state sensitivities. The unilateral catch diode is idealized; there
  is no Qrr/Coss/SOA/avalanche or incoming source. Its capacitor short bypasses
  the upstream fuse. `energy.cir`/`energy_runner.rs` preserve the attempted
  separate SPICE shutdown model; its aborted runs are not evidence of stress.
- `device.cir`/`device_runner.rs`:16 separate local leg references use the actual
  Infineon IPW65R018CFD7_L1 model at198V/37A, each direction,
 396.6/488ns deadtime and0.4/0.2ns steps. Each uses its own valid native19
 4×4 **finite-closure** field matrix. These are independent local references,
  not a full-bridge coupled extraction. There is no zero-filled8×8 splice or
  duplicated shared R5 return. Vendor package L remains inside the vendor
  subcircuit. The21.519nH bulk path and2nH shunt remain explicit old heuristic
  assumptions, not new extraction results. The driver is an output-resistance
  approximation, not a transistor-level driver/TVS model.

The A/B matrix input hashes and complete vendor library hash are pinned by the
replay. The source board remains native19 SHA256
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.

## Protection assumptions that must not become release claims

The precharge pair is HS40025RJ, each23.75–26.25Ω at25°C. Simulated branch
energy and instantaneous power are reported separately against the peer's
conservative2000J/part graph floor and4000W single-pulse overload figure.
Those source curves do not qualify hot/repetitive installed use. Resistor winding inductance and temperature drift are not modeled. The G4A01128C
thermal cutoff has no sub500ms protection credit in this model.

The exact LC1D18BD data gives closing53.55–72.45ms and opening16–24ms.
The current replay uses72.45ms closing for main and bypass, main opening24ms
and bypass opening16ms to exercise the adverse ordering. The actual controller
now admits pickup within100ms while retaining its446ms total attempt deadline.
The prior20ms closing assumption and50ms pickup deadline could not represent
the selected component. See the [manufacturer's exact-part data, p3](https://iportal.se.com/Contents/docs/SQD-LC1D18BD.PDF).

Proof contact5ms, contact
transition100µs,400V arc threshold plus0.5Ω arc slope, source0.1Ω/20µH,
25W nominal resistive AUX proxy,20µs analog guard delay, and thresholds230V/250V/1000V/85A
remain **allocations or sensitivities**. They do not establish component-chain
maximum delays, actual PSU inrush, contact breaking ability, current limit, or
analog fault timing. The400V arc sensitivity appears on both source and bypass
contacts; omitting the bypass arc created timestep-sensitive artificial voltage
spikes. Arc/fuse coordination requires actual interruption data.

The FWP-10A14F catch fuse is represented by an **assumed** 2mΩ conductor in the circuit. This intentionally
reports **prospective demand**, never fuse let-through. Catalogue22A²s total
clearing at700VAC cannot be substituted for a DC clearing law. Source-fed
fault demand and local-capacitor discharge are separate paths. No TVS energy,
DC fuse coordination or exact supervisor timing pass is asserted here.

The protection peer's `closed-loop-topology.json` explicitly contains unresolved
holder/fuse, die/bond, capacitor distribution and native-return closures.
`geometry_gate.rs` rejects that scaffold for a complete installed field
extraction. It is a scope gate, not a general geometric verifier. No fine mesh
was launched, no surrogate path was relabeled as physical, and no1/3µH value
was called extracted. Local matrices cannot fill these missing modes.

## Replay and evidence

Run from the worktree, with an entirely new directory below the model output:

```sh
zapote/power-stage-120v/prototype-closure/round5/model/replay.sh \
  "$PWD/output/temper-prototype-closure/round5/model/my-replay"
```

Requires the already installed Homebrew ngspice45.2 shared library/CLI, clang,
rustc, and the existing read-only Infineon library. Set `TEMPER_VENDOR_MODEL`
when its location differs. Nothing is downloaded or installed. The shared
library uses SPARSE1.3; the CLI reports a KLU-capable build. The RC analytic
check independently verifies the shared runtime and all256µs sample deadlines.
Each replay records full input hashes before and after running, tool versions,
per-case netlists/logs, actual completion times, state transitions, ADC/cycle
logs, CRC/stale/proof/bypass/POST/inhibited negative controls, energy conservation,
and numerical refinement. Aborts remain `INCOMPLETE`; they cannot produce a
completed diagnostic receipt.

See the accompanying `RESULTS.md` for the accepted replay identity, results and
remaining integration work. This package deliberately reports the remaining
exact-target, physical-geometry, analog-chain and protection-model gaps rather
than converting approximate digital evidence into a manufacturing release.
The current receipt is `current-evidence.json` with `evidence-current/`;
the original `evidence.json` and `evidence/` remain historical.

The catch diode's [official Infineon datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-idw40g65c5-ds-en.pdf)
was rechecked on2026-10-05. Its simplified typical forward model is restricted
to current below80A; it cannot validate every prospective fault here. The10ms
surge/I²t ratings also depend on case temperature and pulse shape. Exact values,
page numbers and formula applicability are recorded in
`primary-source-check.json`; no arbitrary-waveform coordination credit is taken.

`extended_run.sh` separately repeats a1.5s nominal run at1.25/0.625µs, allowing
the actual controller ramp to approach its1500W conductance request. Use the
verified binary produced by the main replay. This remains an averaged-plant
study with ideal sensing, not a rated-power hardware test.
