---
name: electrical-model-review
description: Review an electrical model, protection claim or fault assessment before it is accepted. Use when a change, ranking or protection claim rests on a circuit model, a datasheet value, a derived number or a fault scenario; when reviewing a campaign attempt, a model certificate or an evidence ledger; or when a review correction has to become an enforceable rule. Covers tracing actual current paths, challenging assumptions, choosing independent checks, and the four failure classes the Rust checks enforce.
---

# Electrical model review

A model result is not evidence until its **bounds, conditions, device states and
completion evidence** survive review. This procedure says how to test that, and
what the Rust checks already enforce.

Read this before accepting any of: a loss or stress number; a protection claim; a
fault assessment; a ranking between alternatives; a "verified" or "qualified"
status.

## The four failure classes

These recurred and are now machine-checked. Review for them first.

### 1. Bounds and conditions

A value is never just a number. Record **whether it is typical, minimum, maximum,
assumed or measured**, alongside the **current, temperature, waveform and exact
part** it was established at.

The specific invalid inference: **"maximum at 50 A" does not become "minimum
above 50 A".** A bound cannot flip direction, and monotonicity does not rescue it
— a device clamping at 350 V at 50 A and 380 V at a higher current satisfies both
statements only in the correct direction. If the value at the operating condition
is not published, the honest result is **unknown**, not a bound in either
direction.

Also reject: dropping a source condition when a value is reused; dropping the
part binding; promoting an assumed or typical value to measured without evidence.

### 2. Fault states

Distinguish **healthy/on, healthy/off, failed-short, failed-open**. They are
different devices for a protection argument:

- A **healthy** switch may be commanded off, subject to a detection-and-latency
  budget that must be stated.
- A **failed-short** switch cannot be turned off, and no gate command opens that
  path.

A protection claim must name **the device that opens the path** and establish
that the device **remains functional in that scenario**. Crediting interruption
to an unnamed device, to a device that is failed in that case, or with no
retained evidence, is rejected.

### 3. Calculations vs qualified predictions

`R × C` produces an **illustrative** number. It may not establish a **clearing
deadline** unless there is evidence that the resistance model applies to the
fault being analysed — a normal-operation resistance does not describe a
destructive short. Say which you have.

### 4. Completion evidence

Keep these distinct, and do not skip a rung:

`none → protection identified → part selected → coordination demonstrated → hardware verified`

Each step needs retained evidence. "Protection identified" is not "part
selected"; "part selected" is not "coordination demonstrated"; nothing is
"hardware verified" without a hardware record.

## Procedure

1. **Trace the actual current path.** From the schematic and the board, name the
   nets and components in the loop. Do not derive a device stress by adding two
   node potentials — that produced a phantom 586.7 V claim. Write down, for each
   element in the path, whether it can conduct given its state.
2. **Separate the fault classes.** Line-fed and internally powered faults have
   different limiting impedances, timescales, energies and interrupting elements.
   Do not let one class's numbers stand in for the other's.
3. **State the condition for every number.** If the condition is unknown, the
   number is unknown. An average current is not a basis for sizing a pulsed
   element.
4. **Challenge the assumption the number rests on.** Ask what model the
   calculation assumes and whether it applies at the operating condition. An
   illustrative number is allowed; presenting it as a qualified prediction is not.
5. **Seek an independent check.** Prefer an external oracle — a manufacturer
   model, a measurement, an independent implementation — over agreement between
   two of our own implementations. Say explicitly when none exists.
6. **Keep unresolved quantities null.** A null with a named missing input is a
   result. A filled-in number without evidence is a defect.
7. **Run the checks and retain their output.** See below. Passing a check means
   the derivations are sound, not that the claims are true. The CLI reports
   "no violations detected by implemented checks" and says so in its own output.

## Tooling

| Check | Command | Catches |
| --- | --- | --- |
| Evidence ledger | `zapote-claims LEDGER.json` | bound reversal, the maximum→minimum inference, a changed condition or part without a declared transformation, silent fault-state change, illustrative→qualified promotion, unnamed or failed interrupting device, broken completion history, any evidence reference that is malformed or does not resolve to retained bytes — across claims, protection claims and promotions alike — and any claim with no declared origin, any derivation that names no inputs, duplicated ids, inputs naming no claim, and dependency cycles |
| Fault loop | `zapote-fault-loop NETLIST.json --loop-nets A,B,C --assignments A.json` | current assigned to an element that cannot conduct in the declared loop |

Both are Rust under `zapote-erc`; the Python entry points are thin wrappers. The
campaign's acceptance regressions
(`zapote/packages/zapote-harness/tests/campaign_ledgers.rs`) run the committed
ledgers through them, so a ledger that regresses fails the normal test suite.

## What these checks cannot do

- They detect **specific violations**, not false **claims**. A ledger can pass
  every implemented check and still be wrong. Their CLI output says so.
- The origin rule closes a **declared** derivation that omits its parents. It
  cannot tell that a claim *labelled* `source` (or `assumption`) is really a
  calculation — deciding that needs the meaning of the prose, not its shape. A
  known instance is asserted by `the_documented_residual_gap_is_still_open` in
  `campaign_ledgers.rs`, so closing it fails a test rather than passing silently.
- Neither can it see a document *outside* the ledger that restates an
  `illustrative` entry as a bound. That is how the AR-BOUNDS defect reached the
  manufacturer packet; closing it needs report-to-ledger consistency, with
  generated tables inheriting evidence strength and conditions from the ledger.
- The fault-loop check is a **necessary connectivity** test. Two terminals on a
  loop's nets is consistent with conduction; it does not prove a conductive path,
  a device state, a direction, or a distribution.
- No check substitutes for tracing the circuit. An agent's checklist assertion is
  never evidence; retained artifacts are.

## Reporting

State which failure classes each finding falls in, which artifacts support it,
and which quantities remain null with what would resolve them. When a review
correction turns out to be mechanically checkable, add the regression case —
including a valid counterexample so the check does not simply reject everything.
