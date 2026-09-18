---
title: "Electrical model acceptance rules: bound direction, source conditions, fault states and completion evidence"
date: "2026-09-18"
category: best-practices
module: zapote
problem_type: best_practice
component: measurement_evidence
severity: high
applies_when:
  - "accepting a loss, current, stress, protection or fault claim in a campaign handback, model certificate or evidence ledger"
  - "restating a datasheet value at an operating condition different from the one it was published at"
  - "making a protection claim about a fault in which a device may have failed"
  - "turning an arithmetical result such as R x C into a deadline, budget or bound"
  - "promoting a design from identified to selected to coordinated to verified"
tags:
  - evidence-class
  - bound-direction
  - source-condition
  - fault-state
  - completion-evidence
  - protection-claim
  - model-acceptance
  - zapote
---

# Electrical model acceptance rules

Five claims were made, reviewed and corrected during the 2026-09-17/18 PFC
investigation. Each correction was mechanical once seen, and each is now a
rejected derivation in the Rust harness. This records the incidents, the rule each
produced, and where it is enforced.

Enforcement lives in `zapote/packages/zapote-erc/src/evidence_claims.rs` (CLI
`zapote-claims`) and `zapote/packages/zapote-erc/src/fault_loop.rs` (CLI
`zapote-fault-loop`), with the campaign's committed ledgers as regressions in
`zapote/packages/zapote-harness/tests/campaign_ledgers.rs`.

## 1. A bound was restated backwards

**Claimed:** the MOV's clamp "is a lower bound" at the surge current, and therefore
the voltage margins "are optimistic".

**Wrong:** the datasheet gives `VC = 395 V maximum at IPK = 50 A` — an **upper**
bound, at that current only. Monotonicity does not recover the direction: a device
could clamp at 350 V at 50 A and 380 V at a higher current while satisfying both
statements. The clamp at the surge current is **unknown**, and the stated margin
was the most favourable reading rather than a conservative one.

A companion error in the same sequence: the MOV current was assumed to be the
generator's prospective ~500 A. It is not automatically — the current through a
line-to-neutral MOV depends on the coupling and source impedance.

**Rule.** A value carries whether it is typical, minimum, maximum, assumed or
measured, together with its current, temperature, waveform and exact part. A bound
may weakly become unknown; it may not reverse or strengthen. **"Maximum at 50 A"
is not a minimum above 50 A** — that specific inference is rejected by name, as is
dropping a source condition or a part binding when a value is reused.

## 2. Energy was assigned to an element outside the loop

**Claimed:** a capacitor-discharge model put ~34 J into the current-sense shunt,
with a 7.7 kA peak and a 116 µs time constant.

**Wrong:** the retained netlist puts the shunt on `{PFC_BUS_MINUS, minus}` — one
terminal on the loop — while the switch source and the capacitor negatives share
`PFC_BUS_MINUS`. The loop is capacitors → shorted boost diode → switch →
capacitors and **bypasses the shunt**. The values were a wiring error, not a
tolerance. The stored energy (179.24 J) survived; the *distribution* did not.

**Rule.** An element can carry current in a declared loop only when at least two
of its terminals lie on that loop's nets. This is a **necessary connectivity
check** — it does not prove a conductive path, a device state, a direction or a
distribution.

## 3. Two device states were collapsed into one

**Claimed:** gate shutdown cannot open "a conducting U9", so the internal loop is
uninterruptible.

**Wrong:** that collapsed two different devices. A **healthy** switch may
potentially be commanded off after the diode shorts, subject to a
detection-and-latency budget; an **already-failed-short** switch cannot be turned
off, and nothing else in the loop interrupts it. The shunt's blindness is a real
problem in both cases, but the conclusion differs.

**Rule.** Distinguish healthy/on, healthy/off, failed-short and failed-open. A
protection claim must name the device that opens the path **and** establish that it
remains functional in that scenario; crediting interruption to a failed device is
rejected.

## 4. A calculation was presented as a qualified prediction

**Claimed:** the internal discharge timescale is 94.1 µs.

**Wrong:** that is `42 mΩ × 2240.47 µF` — an illustrative RC number that assumes the
normal-operation device resistance describes a destructive fault. It does not
establish a timescale, and it certainly does not establish a **clearing deadline**.

**Rule.** `R × C` may produce an illustrative number; it may not support a qualified
prediction without evidence that the resistance model applies to the fault being
analysed. The physical timescale joined peak current and energy distribution as
**unresolved**.

## 5. A proposal was promoted to a resolved design

**Claimed:** "add a semiconductor-grade interrupting element" as the protection
recommendation, sized to "carry ~4.5 A and clear a ~100 µs multi-kA pulse".

**Wrong:** no device was selected and no coordinated clearing analysis demonstrated
interruption, so the gap was **identified, not resolved**. The ~4.5 A figure is the
average bus current and is not a basis for sizing an element that carries pulsed
charging current.

**Rule.** Keep `protection identified → part selected → coordination demonstrated →
hardware verified` as distinct statuses. No rung is skipped and each needs retained
evidence. Missing evidence prevents promotion.

## A predecessor of the same shape

An earlier claim in the same investigation — "586.7 V across the bridge device on a
boost-switch-short fault" — was `400 + 186.676`, an explicit **sum of two node
potentials**. It survived because the arithmetic is trivial and the number looks
computed. It corresponded to no real node; tracing the schematic showed the boost
diode blocks the bus in that fault.

**Rule.** Do not derive a device stress by adding two voltages. Trace the actual
current path, name the nets and components, and state each element's state.

## Why these are checks and not reminders

Every one of the five was caught by a human reading the artifact, not by the
harness, and each was corrected **after** it had been committed. A reminder would
have been available each time and would not have fired. The derivations are
mechanical, so they are enforced mechanically; the *unmechanisable* part — is the
circuit reasoning right? — is what the review procedure in
`zapote/skills/electrical-model-review/SKILL.md` is for.

Two honesty constraints are built into the checks and must survive future edits:

- They reject unsound **derivations**, not false **claims**. A ledger can be
  internally sound and still wrong. Their CLI output says so.
- The connectivity check is necessary, not sufficient. Passing it is consistent
  with conduction; it is not evidence of it.

Any regression added here needs a **valid counterexample** beside it — a weakened
bound, a justified fault-state split, a declared non-interruption — so the checks
cannot be satisfied by rejecting everything.
