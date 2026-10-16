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

## Addendum 3, 2026-10-16: stage 48 puts BIAS_GOOD on J4.1 (power-stage DECISIONS 67, OPEN-ITEMS B13 H2)

11. **J4 pin 1 is now an output of the power board:** BIAS_GOOD (U40, SN74LVC1G17 on V3V3) through R146 220 k at the
    connector. It reads high only while the LS / HS-A / HS-B bias monitors are good and the heartbeat runs. Items 1–2
    (J13 merge, no 15 V on J4.1) are therefore still required, and are now also the precondition for item 12. On every
    controller branch checked on 2026-10-16 (`controller-layout`, `controller-l4`, `controller-release`,
    `fab/controller`, `controller-c1-crs` at C47), J4.1 is still `v15_selv`, the input of the 3.3 V buck. A stage-38+
    board does not power that controller at all (benign). With an s48 board and a bench 15 V on J4.1, R146 limits the
    current into U40's output to ≤ 68 µA.
12. **Asked: route J4.1 to GPIO35 as a high-Z input.** All 36 WROOM-1-N8 GPIOs are allocated, so free GPIO35 by
    moving RAIL_OK_RB (U9 Y1_4, push-pull) to the spare TCA9555 **P02**. C27 did the same for SUP_RUN_OK (P14) to free
    GPIO14 for RUN_EN.
    - **Why GPIO35:**
      - input-capable, and not a strap (0, 3, 45, 46);
      - no ADC function, so no ADC2 / Wi-Fi conflict;
      - not used by flash or PSRAM on the N8 module (only octal-PSRAM R8 parts take 35–37);
      - beside PERMIT_RB (GPIO36), the other J4 read-back.
    - **Cost of the move:** RAIL_OK is latched in hardware (RAIL_FAULT). The binding already reads SUP_RUN_OK from
      the expander snapshot with a freshness check, so moving RAIL_OK there costs no protection.
    - **Why not an expander bit for BIAS_GOOD:** the TCA9555's 100 k pull-up against R146 220 k holds a BIAS_GOOD low
      near 2.2 V, so a low would read high.
    - **Parts at the controller:**
      - net `bias_good_rb`: J4.1 → 10 k series → GPIO35;
      - 1 MΩ 1 % to selv_gnd and 1 nF C0G to selv_gnd at the pin;
      - the same ESD treatment as the other J4 inputs.
    - **Figures (1 % parts):**
      - high reads ≥ 0.81 × V3V3, against the ESP32-S3's VIH of 0.75 × VDD;
      - an open U40 output reads ≤ 50 mV (50 nA × 1 MΩ);
      - τ ≈ 190 µs, which filters harness transients and still reaches VIH within 0.5 ms;
      - the 10 k lets U37 hold PERMIT if a GPIO misconfigured as an output meets a J4.1–J4.9 harness short, so a
        GPIO still cannot drive PERMIT;
      - no internal pull: 45 k would hold the input at ≤ 0.6 V.
    - **Firmware side** (branch `claude/fw-bias-good-check`): done. The check runs as soon as `controller_pins.h` defines
      `CTRL_GPIO_BIAS_GOOD_RB`, which the pin-map cross-check allows only once the ato carries the net. Until then it
      reads "not fitted" and claims nothing.
    - **Bring-up:** firmware `components/power/COMMISSIONING.md` step 2 item 6.
    - **Reverses if:** the controller cannot spare a pin. R146 then stays as a harmless load, and B13 H2 is lost
      (DECISIONS 67).
