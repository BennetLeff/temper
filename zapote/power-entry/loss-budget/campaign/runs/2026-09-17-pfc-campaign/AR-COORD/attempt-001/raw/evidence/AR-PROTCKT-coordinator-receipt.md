# Coordinator receipt — AR-PROTCKT attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-PROTCKT/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** A concrete circuit with named parts; the
protection gap is **narrowed, not closed**, and the attempt says so.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`, per `ADMISSION.md`). Evidence ledger present, passing, and
re-verified independently.

## The circuit

One arrangement over three loops:

| Ref | Part | Placement | Rating source |
| --- | --- | --- | --- |
| **F2** (new) | **FWP-50A14F**, Eaton/Bussmann, 14x51 mm | series in the DC bus between the U10 cathode and the cap bank — **inside the internal discharge loop** | DS 720025, **retained revision only** (PDF CreationDate 2011-03-01, ModDate 2014-03-26): 800 Vdc, 50 A, 50 kA @800 Vdc, min melting I²t 200 A²s, clearing I²t 1800 A²s. **The applicable revision is unresolved** — see below. |
| U7 (existing) | V150LA10AP | L–N surge clamp | LA Series rev 2024-09-16 |
| F1 (existing) | Schurter 0034.3129 | line-fed loop | secondary |

F2 sits in the loop for **every** `U9` state, which is what makes a fuse the right
class for the failed-short case rather than a gate command that cannot act.

## The honest headline

**No evaluated arrangement has demonstrated interruption of case (b)** — `U10`
shorted with `U9` failed short. That is the supported statement; the earlier
"no available part interrupts case (b)" claimed more than the investigation
established. F2 is topologically right and is the only evaluated element that can
act, and its clearing is **not demonstrated**: the 1800 A²s clearing figure is an
AC/inductive number, not a capacitor discharge, and the loop's high-current
impedance is unknown.

Case (a) (`U9` healthy) is **not interrupted as demonstrated** either — a healthy
switch could in principle open the loop, but there is no loop-current sensor
(U12 is not in the loop; no controller OCP), so no detection/latency budget can
be credited. Cases (c) line-fed and (d) surge are likewise not demonstrated or
clamped-not-interrupted respectively. Case (e) lists what the arrangement cannot
interrupt; a crowbar diverts rather than interrupts.

## Sizing: an illustrative screen, and the right continuous-duty basis

**The resistance window is an illustrative screen, not an interruption
criterion.** `E/R >= 200 A²s` compares an ideal discharge's available action to a
pre-arcing figure; it does **not** prove melting or clearing for that waveform,
and `400/R <= 50 kA` does not establish applicability of the breaking rating.
Inductance, evolving fault resistance and arcing all remain relevant. What is
retained is the arithmetic: F2 would melt only if `R_loop <= 0.896 ohm` and would
sit inside breaking capacity only if `R_loop >= 0.008 ohm` — a screen to bound the
next measurement, not a verdict.

**Continuous duty is an RMS question, not an average one.** F2 carries the
pulsed boost-diode current, and heating depends on the RMS of that waveform with
its repetitive pulses, startup and temperature. The retained waveform model gives
**diode RMS = 9.0007 A at 120 V** (8.5390 A at 108 V, 8.5868 A at 132 V) — about
**twice** the 4.5 A average the earlier draft proposed to size on, so an
average-based size would undersize heating by roughly half. Eaton's own loss
correction is expressed against RMS load current, which is the basis to use.

## The MOV bound, correctly handled this time

The required clamp is `V_clamp(I_MOV)` from the manufacturer V-I, and is **null**
because the operating MOV current is unestablished. The datasheet's 395 V is
recorded as an **upper bound at 50 A only** — the reversal that had to be
withdrawn in AR-MOV is not repeated, and the surge contract stays **provisional**.

## Completion discipline

The ladder advanced one rung at a time: `none -> protection_identified ->
part_selected`. It is **not** promoted to `coordination_demonstrated`, because
coordination is not demonstrated. That is the rule working exactly as intended —
the previous attempt's defect was promoting a proposal past this point.

## Checks

- `zapote-claims claims.json` — no violations (15 claims, 5 protection claims, 2 promotions); re-run independently by the coordinator.
- `check_fault_loop.py` — consistent on the illustrative and null assignments.
- Negative controls both fail as designed: the withdrawn `U12 = 34 A` model
  reports `FAULT LOOP INCONSISTENT`, and a reversed MOV bound reports
  `reverses the bound direction`.

## Single gating input

**The internal discharge loop's high-current impedance at the fault** — the
combinations of `U10`/`U9` short residual, bank ESR, fuse resistance and layout.
It decides whether F2 both melts and clears, and without it case (b) cannot be
shown to be interrupted. Two secondary inputs: a **400 Vdc capacitor-discharge
clearing characteristic** for the fuse class, and a sourced **bank/copper
withstand I²t**.

## Fuse rating: the applicable revision is unresolved

The retained datasheet is a **2011-2014** revision of DS 720025 (PDF
CreationDate 2011-03-01, ModDate 2014-03-26) and states **800 Vdc** and
**50 kA @800 Vdc**. The current revision reportedly specifies **700 Vdc**, with
the breaking rating stated at 700 Vdc instead. The current PDF could not be
captured from this host (HTTP/2 `INTERNAL_ERROR`, then an HTTP/1.1 timeout with
zero bytes — both failures retained under `raw/capture/`), so **the applicable
revision has not been established** and the 800 Vdc figure is recorded as the
retained revision's value, not the part's.

Either revision exceeds the nominal 400 V bus, so the candidate's *class* is not
in question. But the number a coordination argument relies on must come from the
revision that applies to the part being ordered.

## Milestone

**Candidate part and location identified; coordination unestablished.** F2 is a
proposal and has **not** been added to CAD or the BOM.

## What this changes

Less than the previous draft claimed. The candidate part and its location are
identified and defensible; the protection gap is **not** bounded to a single
measurement. Coordination needs the fault-impedance envelope, a 400 Vdc
capacitor-discharge clearing characteristic (or manufacturer guidance), and a
sourced bank/copper withstand — and the applicable fuse revision. It remains open,
and no hardware is qualified.
