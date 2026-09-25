# F2 default-off interface and simulation closeout

Created: 2026-09-19

## Goal and scope

Complete the three explicitly requested next steps: (1) implement a dependable
default-off interface and supply supervision; (2) replace the three ineffective
fault stimuli with isolated running-fault tests; (3) remove the unphysical
power-switch current artifacts and reassess timing and voltage margin using
an applicable device model or a transparent, independently checked surrogate.

This is local circuit and simulation work, with maximum useful Luna delegation.
The host integrates and verifies. No PCB, firmware, publication or general
validator framework change is part of this pass. The existing54-part board and
all prior hashed F2 experiments remain unchanged. New artifacts live under
`zapote/power-entry/passive-reva/protection/f2-shutdown-04/` and the new source is
`elec/src/power_entry_f2_shutdown_revb.ato`.

## Decisions and evidence

- Retain the tapped-divider, independent comparator, retained-latch architecture
  from `power_entry_f2_shutdown.ato`; fault recovery requires a fresh ARM edge.
- Replace the direct Q→UCC27624 EN connection. A valid design must be OFF when
  logic5 is absent while aux15 is present, and while either supply is invalid.
  Select a standard documented interface with explicit power-off behavior;
  do not infer a guaranteed EN pullup from its200k typical value.
- Supply validity must be implemented by named parts and thresholds, including
  startup reset hold. An ideal `rails_ok` waveform alone does not close step1.
- Preserve the10Ω1206 gate resistor and gate pulldown interface. Avoid adding
  general monitoring functions unrelated to the shutdown requirement.
- Use independently driven VD/VB fault-injection fixtures for channel tests,
  so a closed F2 cannot erase the requested stimulus. Prove healthy operation
  before injecting each fault, correct channel assertion, retained shutdown,
  and valid fresh-edge recovery. Separate these logic tests from energy tests.
- The exact baseline power devices are STW65N65DM2AG and C3D20065D. The old
  diode surrogate included TT=20ns despite the selected SiC Schottky topology;
  investigate its contribution rather than treating its current spikes as real.
- Seek the exact manufacturer models with bounded attempts. If unavailable,
  use a declared physical surrogate with finite switch transition, output and
  junction capacitance, and applicable diode charge behavior. Do not hide
  ringing/spikes by clipping current or merely widening the timestep.
- Keep physical fault-current maximum, L(I,T) limits and assembly qualification
  unknown unless evidence actually establishes them. Completing the design
  and credible simulation does not require claiming hardware qualification.

## Work ownership and order

1. **Circuit worker (Luna):** owns new Atopile source, new scoped compiled-pin
   test `zapote/packages/zapote-erc/tests/f2_shutdown_revb.rs`, new component
   documentation and `f2-shutdown-04/circuit/`. Select the interface and
   supervisors, calculate thresholds/leakage/drive margins, and hand over a
   node/part contract early. Host compiles the exact entry and bridges its graph.
2. **Fault-test worker (Luna):** owns `f2-shutdown-04/fault-tests/`. Build independent
   running-fault stimuli and strict Rust extraction. Start with the existing
   detector/latch function; update the fixture to the circuit worker's published
   interface before acceptance. Own supply ramp/dropout and held-ARM cases too.
3. **Power-model worker (Luna):** owns `f2-shutdown-04/plant/`. Diagnose the old
   current artifact, retain applicable model sources, validate device behavior,
   then run the improved F2 energy model, timestep checks and sensitivities.
   Publish a detector/disable interface so host can bind it to the new circuit.
4. **Independent source/design audit (Luna):** read-only manufacturer and circuit
   assessment, focusing on power-off defaults, back-power and model applicability.
5. **Host integration + fresh Luna review:** inspect frozen changes, compile and
   verify the actual graph, run integrated cases, resolve findings and record
   current hashes, results, assumptions and remaining physical dependencies.

Workers use separate worktrees at the recorded base revision, read prior
immutable canonical artifacts, and do not commit, publish, edit another unit's
files or change generated shared caches. Native Luna subagents are the selected
execution engine. User approval to execute is already explicit.

## Required verification

- Compiled graph: exact pins/parts/values, comparator polarity, no tied
  push-pull outputs, default-off interface, supervisor threshold connections,
  asynchronous clear and fresh raw ARM clock; source/export hashes current.
- Supply behavior: both rail orders, logic absent/aux present, aux absent/logic
  present, slow ramps, each dropout and restoration, ARM held high, PWM high;
  no enabled output until supplies are valid and a new valid ARM edge occurs.
- Fault channels: diode-side OV, bank-side OV and reverse mismatch independently
  persist after normal operation and assert the intended detector. Also check
  forward mismatch/F2 path. Do not label startup inhibition as zero latency.
- Extraction: reject absent/malformed/nonfinite traces and missing events;
  require pre-event activity and sustained off behavior; require a successful
  positive rearm and reject an uncommanded restart.
- Device model: explain original impulse cause; compare steady conduction,
  switching charge/energy or applicable vendor fixture against external data;
  retain raw gate, VD/VB, inductor and switch/diode-current traces. Check energy
  conservation over a defined interval with source work included.
- Full path: loaded-gate fault timing, representative current/inductance/PWM
  phases, doubled gate load and slower response; deliberately slow negative
  control must fail the provisional2µs target. Reassess500V voltage screen.
- Timestep refinement must not turn a divergent numerical spike into evidence.
  Negative margins are engineering results to address or report explicitly.
- Independently review frozen outputs. Preserve all prior receipt hashes and
  run the existing claims checker on the new evidence ledger.

## Completion

Each step closes only with implemented artifacts and executed evidence. A real
model/device limitation must be named precisely; do not classify unfinished
tests or a missing circuit as a hardware-only dependency. Report whether the
provisional margin passes under the declared assumptions and what remains
unbounded. Preserve failed attempts and resolve material review findings before
calling this pass complete.

## Executed result

All three requested simulation-work steps are complete. The accepted report is
`zapote/power-entry/passive-reva/protection/f2-shutdown-04/README.md`.

1. **Implemented:**79-part revisionB, source-07 export and physical-pin graph.
   Real supervisor dividers/CT, buffered external inputs, fast auxiliary-loss
   clear, RUN/clear qualification and a1kΩ default-disable driver interface.
   Fifteen compiled/regression checks pass.
2. **Executed:**13 positive independent fault/supply cases pass. Both bypass and
   slow-detector negative controls fail. All four fault channels run after
   verified gate activity, retain shutdown through recovery and require a fresh
   ARM edge. Loaded-gate delays are0.749µs OV and1.536µs mismatch.
3. **Corrected and evaluated:**finite MOS/SiC surrogate with actual DC anchor
   checks, no doubled body diode/Cgd, actual opening currents41.66–51.10A,
   current/phase/load sensitivities and timestep refinement. Twelve plant cases
   pass; deliberately slow-driver case fails. Accepted peak voltages stay below
   478V and doubled-load controlled turnoff is0.870µs.

Host integration corrected source-pin, fixture, model and extraction defects;
independent Luna reviews found no remaining must-fix in the final bounded
plant accounting. The193 earlier artifact/input hashes remain unchanged.
The receipt records exact final hashes and the claims checker result.

Remaining physical/model qualification limits are explicit in the report and
are not treated as missing implementation work: partial-power behavior below
specified logic supplies, hot device dynamics, real fault-current/L(I,T)
bounds, fuse arc and layout parasitics. No hardware exists in this campaign.
