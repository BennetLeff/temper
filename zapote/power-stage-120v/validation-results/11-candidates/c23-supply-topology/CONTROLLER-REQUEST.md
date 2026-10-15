# Candidate 23: request to the controller owner (J13 rail merge), 2026-10-14

Status: request, power-stage side. Nothing on the controller branch is edited from here; the controller owner records
the change in `zapote/controller/DECISIONS.md` the way C33 recorded stage 16 (it cited PLAN-16.md).

## Why now
Candidate 23 (`../QUEUE.md` row 23; proposal `../g06-g08-g10-supplies-sense-io/PROPOSALS.md` P1) deletes PS1
(IRM-20-15) and runs the controller logic from PS3 (IRM-60-15ST) over J13. It is the board's only route to the F5
touch-current limit: 0.974 mA today; 0.419 mA with PS1 deleted and the off-board D-22 rev B filter, against the 0.5 mA
Test A limit (`../c29-inlet-filter/c29_leakage.py`: 132 V, 60 Hz, +20 % on every Y, supplies at datasheet maximum).
With PS1 fitted the same filter gives 0.562 mA (fail). The controller change is the blocker, so it is asked for first.
The power board's own re-layout will be done with the six-layer study's phase B (`../c33-six-layer/PLAN.md`).

## Asked of the controller (from PROPOSALS.md P1, unchanged)
1. Join J13 pin 1 (V15_BLW) to the logic 15 V rail through a Schottky or ferrite bead plus bulk capacitance, so a
   blower start (5.46 A bound) or stall cannot pull the logic rail below its brown-out threshold.
2. Remove the J4.1 15 V input path. J4.1 is freed on the power board; the J4 re-pin with interleaved grounds
   (PROPOSALS.md P5) can move in the same step, or stay separate.
3. "PS3 absent" handling (BLW_PG, "NO BLOWER PWR") becomes moot: PS3 absent means no controller, and PERMIT / PWM fail
   low with it (power board: R7 / R15 pull permit_gate down; U1 / U2 VDDI is v3v3, so input UVLO holds both outputs low).
4. Re-check J13: PS3 output 2.72 -> 2.97 A (44.5 W / 15 V), JST VH / 18 AWG pair.
5. Bench item to keep: blower start and PS3 overload hiccup with the logic rail scoped (the P1 reversal condition).

## Also: one stale line
`zapote/controller/DECISIONS.md:348` (controller-layout branch) cites "UCC21550 VCCI UVLO <= 2.65 V". The drivers are
now Infineon 2EDR8259X (power-stage stage 29, DECISIONS 31): VDDI UVLO on <= 2.95 V, off >= 2.55 V, no tSTOP maximum
(`native-21/verification/datasheet-ledger/ledger.json`, 2EDR8259X entry). The falling-rail order TPS3703 -> TPS3823 ->
driver UVLO still holds; please restate the line with the new part.

## Needed from elsewhere (not the controller)
- Enclosure (temper-f7): PS3 bay air <= 58 C after the extra 4.8 W load (PROPOSALS.md P1: 74 % load, max ambient 60.3 C).
- Certifier: the leakage limit class and whether PS2's leakage counts (`../../08-manufacturing-package/native-21/owner-items/CERTIFIER-PACKET.md`).

## Addendum, 2026-10-15 (power-stage DECISIONS 46, 47)

6. **PS3 IRM-60-15ST → MEAN WELL MPM-65-15ST.** Same case as IRM-60 (drop-in per MPM-65-SPEC 2024-10-30). Touch current
   is < 100 µA at 264 VAC (p.2), against IRM-60's higher maximum. With PS1 deleted and PS2 → MPM-20-24, the system's
   design touch current is 0.2412 mA against the 0.25 mA portable 50 % rule; with an IRM PS3 it cannot pass at any Y
   value. Study: `validation-results/07-conducted-emi/leakage/co-design-2026-10-15/WRITEUP.md`.
   - Thermal is equivalent: 60.7 °C ambient limit on MPM-65 against 60.3 °C on IRM-60.
   - Open: stock (JLC 0), and the certifier's view of its approvals (IEC / ES / CSA 60601-1).
7. **Still-air continuous ceiling ≤ 18 A until the power board's B3 ratings gate passes** (DECISIONS 46). In still air
   with 55 °C bay air, the board copper at R5 exceeds the laminate's UL MOT of 130 °C at the 22 A default ceiling.
   Fixes are in progress (enclosure airflow, board copper candidate 36, shunt). Please treat 22 / 28 A as gated on them,
   and tell us which ceiling the firmware commissions in the meantime.

## Addendum 2, 2026-10-15: stage 38 is built (power board), what the controller now sees

8. **J4 pin 1 is not connected on the power board.** PS1 and its net V15_SELV are deleted; J4.1 sits on a named
   single-pin SELV net `j4_nc1` (no copper beyond the pad). A controller that still drives or expects 15 V on J4.1 sees
   an open pin: nothing on the power board is powered from it, and nothing is back-fed. Items 1 and 2 above (J13 merge,
   remove the J4.1 15 V input path) are therefore required before a stage-38 board is powered with the controller; the
   J4 re-pin (P5) stays a separate step.
9. **PS2 is MEAN WELL MPM-20-24** (was IRM-20-24, same Case 219A and pin map). It still feeds only the HOT-side bias
   (V24_RAW / N_LS, TCO-switched); nothing changes at J4.
10. **PS3 = MPM-65-15ST (item 6) is part of the leakage pass.** The stage-38 touch current (0.2412 mA against the
    0.25 mA budget, margin 8.8 uA) counts PS3 at the MPM-65 maximum (100 uA at 264 VAC). With an IRM-60-15ST in PS3 the
    system fails the budget (0.324 mA: 0.2412 - 0.0600 + 0.1430). Please confirm the PS3 MPN when it is chosen.
