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
| **F2** (new) | **FWP-50A14F**, Eaton/Bussmann, 14x51 mm | series in the DC bus between the U10 cathode and the cap bank — **inside the internal discharge loop** | DS 720025: 800 Vdc, 50 A, 50 kA breaking, min melting I²t 200 A²s, clearing I²t 1800 A²s |
| U7 (existing) | V150LA10AP | L–N surge clamp | LA Series rev 2024-09-16 |
| F1 (existing) | Schurter 0034.3129 | line-fed loop | secondary |

F2 sits in the loop for **every** `U9` state, which is what makes a fuse the right
class for the failed-short case rather than a gate command that cannot act.

## The honest headline

**If demonstrated clearing is required, no available part interrupts case (b)**
— `U10` shorted with `U9` failed short. F2 is the only element that can act, it
is topologically in the loop, and its clearing is **not demonstrated**: the
800 Vdc clearing I²t of 1800 A²s is an AC/inductive figure, not a capacitor
discharge, and the loop's high-current impedance is unknown.

Case (a) (`U9` healthy) is **not interrupted as demonstrated** either — a healthy
switch could in principle open the loop, but there is no loop-current sensor
(U12 is not in the loop; no controller OCP), so no detection/latency budget can
be credited. Cases (c) line-fed and (d) surge are likewise not demonstrated or
clamped-not-interrupted respectively. Case (e) lists what the arrangement cannot
interrupt; a crowbar diverts rather than interrupts.

## Sizing is conditional, and stated as such

Pulse assumed as a unidirectional exponential discharge from the 2240.47 µF bank,
energy 179.238 J. Prospective peak and action I²t are **null** because the loop
resistance is unestablished. What is retained is the conditional structure: F2
melts only if `R_loop <= 0.896 ohm` and stays within breaking capacity only if
`R_loop >= 0.008 ohm`. The ~4.5 A average is used for continuous duty only — the
sizing error the previous attempt made.

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

## What this changes

The protection gap is now bounded to one measurement and two source captures,
with a named part of the right class already placed in the correct loop. It is
**not** closed, and no hardware is qualified.
