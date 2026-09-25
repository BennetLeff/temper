---
title: F2 emergency shutdown circuit and simulation
date: 2026-09-19
type: engineering-implementation
---

# Objective and completion boundary

Implement the user's four steps in an isolated circuit: faster voltage sensing,
retained fault latch, direct gate-driver disable and a transient simulation of
F2 opening. The accepted direction is the small tapped-divider circuit, not the
rejected 133-component supervisor. This work completes a circuit experiment
and its simulation; it cannot qualify absent device bounds or physical hardware.

User explicitly authorized execution and maximal useful Luna delegation.
The host owns canonical integration and verification. Native Luna workers own
separate worktrees and disjoint outputs. No publication is part of this work.
The retained 54-part board and earlier hashed experiments stay unchanged.

# Inputs and design decisions

- Prior source: `elec/src/power_entry_f2_sense.ato`.
- Evidence: `zapote/power-entry/passive-reva/protection/f2-open-01/` and
  `zapote/power-entry/passive-reva/protection/f2-timing-02/`.
- Circuit candidate: two TLV3202 dual comparators, SN74HCS21 combining gates,
  SN74HCS74 retained fault latch, UCC27624 gate buffer; exact pins verified
  against official retained PDFs before wiring.
- Keep paired 987k/200R/5.62k tapped dividers and 100pF filters as the starting
  point, with LM4040 2.5V reference. Preserve both absolute OV channels and
  both mismatch polarities. Recalculate threshold assumptions for new parts.
- All ports HOT-referenced. Externally regulated logic5, aux15 and qualified
  rails_ok are explicit supplied interfaces; this does not build the full
  auxiliary supply, isolation or precharge sequencer.
- `permit` must be valid and high before a fresh `arm` edge. Any fault,
  rails_ok loss or permit loss asynchronously clears retained run permission.
  Healthy inputs returning cannot restart switching. Do not gate ARM with
  health: its reappearance could otherwise invent a clock edge.
- RUN drives the buffer's EN with an external default-low resistor. Unused
  logic/driver inputs are tied to defined states. Retain 10R gate resistance
  and 10k gate-source pulldown as the baseline drive interface.
- Default-off, fault retention, held-arm behavior and supply-return assumptions
  are part of this isolated experiment, with explicit limitations for analog
  back-power and external rails_ok sequencing.

# Work units and ownership

## U1 — circuit source and connectivity checks (Luna circuit worker)

Files: `elec/src/power_entry_f2_shutdown.ato`,
`zapote/packages/zapote-erc/tests/f2_shutdown.rs`, and circuit notes under
`zapote/power-entry/passive-reva/protection/f2-shutdown-03/circuit/`.

Build the separate sensing/latch/driver entry using existing Atopile component
patterns. Host compiles it through the existing source-build adapter and binds
the resulting pin graph. Tests must inspect the compiled physical pin graph,
not just search authored text. Check comparator polarity, separate push-pull
outputs, gates, asynchronous clear, ARM edge, driver EN, unused pins, gate R
and pulldown. A characterized missing source/export is valid initial red
evidence; no generic harness extension is needed.

## U2 — transient model and timing extraction (Luna simulation worker)

Files only under
`zapote/power-entry/passive-reva/protection/f2-shutdown-03/simulation/`.

Model the actual divider RC, comparator response, retained latch, driver and
loaded gate, plus healthy boost diode, inductor, local reservoir and open F2.
Use applicable manufacturer models when available. Explicit authored behavioral
surrogates are allowed for absent models, but label every delay and device
parameter as assumed/typical/maximum with its source condition. Never implement
the desired 2us result as an imposed switch-off delay.

Extract delay from the defined unfiltered voltage threshold to cessation of
switch current; also retain comparator, latch, EN and VGS transitions and peak
VD. Declare the current-cessation metric and distinguish it from inductor
commutation to zero. Keep transistor current and inductor current separate.
Rust owns numerical verdict/extraction; shell and thin serialization may run it.

Cases: normal arm/run; F2 opening with adverse switching phase and 40/45/50A
initial conditions; reverse mismatch; both absolute OV channels; fault clears
while ARM held; fresh rearm; permit loss; rails invalid/return; delayed-gate
negative control. Include timestep refinement and increased gate-charge/delay
sensitivities. Report failures/indeterminate cases rather than tuning tests green.

## U3 — source and failure-path audit (Luna read-only researcher)

Check exact pinouts, timing fixture applicability, logic levels, startup and
back-power hazards, and official model availability. Return a bounded report;
do not modify the circuit or simulation workers' files. Host resolves findings.

## U4 — integration, adversarial review and report (host + fresh Luna reviewer)

Host owns compiled exports, graph transport, evidence ledger/receipt, final
README, source/model binding and canonical checks in `f2-shutdown-03/`.
Review actual worker diffs before copying. Freeze worker outputs before final
verification. A fresh Luna review challenges wiring and simulation conclusions;
the host fixes material findings and reruns affected checks.

# Verification and definition of done

1. Atopile compilation succeeds; compiled count and exact connectivity retained.
2. Rust compiled-net tests cover the complete detector/latch/driver path.
3. Transient scenarios run with raw traces and extracted metrics; actual
   simulated pass/fail against provisional2us and500V is reported per case.
4. Static threshold and source/model audit show assumptions and unbounded
   terms explicitly. Typical model success is not physical qualification.
5. Simulation parameters and topology are checked against the compiled source;
   timestep refinement and a deliberately slower shutdown expose false passes.
6. Existing claims checker passes with hashes; old evidence and baseline hashes
   remain unchanged. No production PCB, placer, firmware or general harness edits.

If a candidate misses the target, revise the bounded circuit/model with evidence
and retain the failed attempt. A valid completed experiment may report that the
target remains unmet; it must not relabel absent implementation as hardware-only
work or claim steps complete without source and executed simulation evidence.
