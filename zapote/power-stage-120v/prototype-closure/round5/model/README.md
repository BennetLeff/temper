# Round 5 executable control and electrical evidence

This package advances the model from a prerecorded conductance waveform to an
accepted-step electrical simulation calling the real C controller. It is
**diagnostic evidence, not a finished device-level implementation or a power
release**. The commissioning bit is enabled only inside the study harness; the
production target's inhibition is preserved. No hardware was energized.

## What executes

`cosim.c` loads the installed ngspice45.2 shared library and links the unchanged
production `fullbridge_adapter.c` and `energy_supervisor.c`, plus round5
`acquisition.c` and `fast_capture.c`. Only accepted solver points advance state.
External-source Newton callbacks read held commands; they do not advance the
firmware. Scheduled events are ADC every256µs, supervisor every1ms, and applied
PWM plans every20µs. A 61s **simulated unpowered** prehistory supplies the cold
lockout history; it does not discharge a previously energized physical unit.
RESET is a distinct event at56ms and START at60ms.

ADC channel order is VLINE, VPRE, VOUT, VBUS, VCATCH, VTANK, IPROOF, ILINE. The
harness produces signed24-bit frames with the real CRC and passes them through
the actual parser; it then decodes them using explicitly ideal full-scale gains.
`sampled_measurement.c` calculates square-integral true RMS using256µs samples,
linear zero-crossing interpolation, and complete50–60Hz-compatible cycles. It
is a **diagnostic estimator owned here**, not the target's completed analog
qualification implementation. There is no ADS131M08 sinc-filter, AMC delay,
noise, calibration, alias rejection, or sensor fault-coverage claim. The
independent continuous-solver integration is logged only as an oracle and is
never used as controller feedback.

Startup qualification requires both crest polarities across two complete valid
cycles: |VLINE|≥0.98√2 times the preceding cycle RMS, VBUS≥0.95|VLINE|,
|VPRE|<5V, and |VPRE|/11.875Ω<0.5A. Catch correlation is proven while charging
and retained during RUN; a falling bus at line valleys must not erase a valid
catch charge-history proof. Proof current must match0.9–1.1×VOUT_RMS/220Ω for a
complete cycle before the real supervisor's additional continuous50ms proof.
These thresholds/error windows are **diagnostic allocations**, not a calibrated
production admission contract. Manual POST, independent contact mirrors,
resistor-cold qualification and auxiliary supply health are ideal stimuli.

Capture frames exercise the actual sequence/CRC/age parser but are synthesized
from the applied digital plan. They do not independently measure physical Vgs,
ZVS, gate propagation or driver overlap. Capture corruption and ADC loss are
negative controls, not evidence that the physical capture system exists.

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

Main contact opening24ms, bypass opening20ms, proof contact1ms, contact
transition100µs,400V arc threshold plus0.5Ω arc slope, source0.1Ω/20µH,
25W nominal resistive AUX proxy,20µs analog guard delay, and thresholds230V/250V/1000V/85A
are **allocations or sensitivities**. They do not establish component-chain
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

Since 2026-10-05 the gate parses the file instead of matching substrings (the earlier gate authorised `{"status": "COMPLETE_PHYSICAL_FIELD_GEOMETRY", "segments": []}`; round-6 investigation). It authorises a solve only for: the exact status; a non-empty segment list with unique ids; all four required kinds (fuse-holder path, catch-diode die/bond, catch-capacitor distribution, native-return closure); per-segment provenance (`physical` or `bounded_model`) whose relative source file exists and matches its SHA-256; one closed connected loop (every node degree 2); and no UNKNOWN/APPROXIMATION/UNRESOLVED/PORT_CLOSURE_ONLY markers. The contract and its 11 negative/positive tests are in `geometry_gate.rs` (`rustc --edition 2021 --test geometry_gate.rs`).

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
