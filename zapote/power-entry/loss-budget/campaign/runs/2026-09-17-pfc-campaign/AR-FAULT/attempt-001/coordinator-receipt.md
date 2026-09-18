# Coordinator receipt — AR-FAULT attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-FAULT/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** The claim under test is **refuted with circuit
reasoning**, and the real problem is a different one.

## 1. Admission

- Dispatch: **ADMITTED** (deadline computed at issue time).
- Handback: **NOT COUNTED AS A VALIDATED RUN** — no checker issued, per
  `ADMISSION.md`. Retained as evidence.

## 2. The 586.7 V claim is refuted

The figure was `400 + 186.676 = 586.68`, an explicit sum of two node potentials
(`AR-VERIFY/raw/compute_ar_verify.py:415`). Traced against the schematic, it
corresponds to **no real node**:

- **Boost-switch short.** The short is across the inductor's output node and
  `PFC_BUS_MINUS`. The boost diode U10 (anode at the switching node, cathode at
  `PFC_BUS_PLUS_390V`) is then **reverse-biased by the full bus**, so the bus is
  isolated from the fault. The loop runs mains → fuse → CMC → NTC/relay → bridge
  → inductor → shorted switch → shunt → bridge → back. **The bridge device sees
  the line peak, 186.676 V.** Nothing sits at 586.7 V.
- **Boost-diode short.** This *does* put the bus on the bridge output, but the
  bridge's own devices clamp their AC nodes between the rails, so a bridge
  device blocks at most ~V_bus (400 V). Reaching 586.7 V would need one AC node
  at +400 V while the other sits at −186.7 V simultaneously — impossible in a
  bridge rectifier; it would require a bridgeless or totem-pole stage.

**Consequence: the real switch-short stress is current and energy, not
voltage.** The 586.7 V figure does not force an 800 V or 1000 V device.

## 3. Exposure

| Quantity | Value |
| --- | --- |
| Bus capacitance (board) | 4 × 560 µF / 450 V + 470 nF / 630 V = **2240.47 µF** |
| Stored energy @400 V | **179.24 J** (226.85 J at the 450 V rating) — independently reproduced |
| Bare switch short | **does not discharge the bank**; U10 blocks it. Natural discharge is the 300 kΩ bleed, τ ≈ 672 s |
| Diode short with the switch conducting | bank discharges internally: 179.2 J total, ~145 J into U9, ~34 J into the shunt, peak ≈7.7 kA, τ ≈ 116 µs |
| Switch-short peak current | **null — parametric.** The AC source/line impedance is not established. Board-only bound ≈6.2 kA; the inductor saturates (43 A) in ≈42 µs |

**Interruption.** F1 (Schurter 0034.3129, FST 16 A / 250 V time-lag) sits in the
line-fed loop, so a line-frequency fault is interrupted *in principle* — but its
pre-arcing I²t is captured nowhere, so clearing is unestablished. **The
bus-capacitor discharge loop is internal and does not pass through F1: nothing
on the board interrupts it.** Line-fed current (ms to tens of ms, source-bounded)
and capacitor discharge (τ ≈ 116 µs) are distinct events with different energies.

**The MOV is out of both loops.** U7 (V150LA10AP) is line-to-neutral; neither bus
rail reaches it. No clamp figure was used — the caveat was honoured.

## 4. Recommendations

- **Voltage class: 600 V remains adequate** for the single-fault blocking case
  (~400 V, 1.5×). The refuted figure does not change the device class.
- **The switch short is a current/energy problem.** The surviving bridge must be
  cleared inside its **IFSM 350 A / I²t 510 A²s**.
- **Add bus-side protection** for the internal discharge loop — a DC fuse,
  crowbar, or a fast controller over-current shutdown. Today there is none.
- Capture and coordinate **F1's pre-arcing I²t**, and resolve the **line
  impedance**.

## 5. What this changes, and what it does not

- **Does not** change the device class: 600 V stands, and the earlier 1.02× fault
  margin is withdrawn as an artefact of adding two voltages.
- **Does** add a protection requirement the design did not have: the 179 J bus
  bank can discharge through a failed switch with nothing to interrupt it.
- It also means selecting the MOV is now **unblocked on its own terms** — the
  fault does not move the voltage class, so the surge contract can be pursued
  independently, exactly as the coordinator intended when sequencing this first.

## 6. Single gating input

**The AC source/line impedance at the fault**, which with F1's uncaptured
pre-arcing I²t decides whether a line-fed switch short is cleared before the
bridge's 350 A / 510 A²s is destroyed.

## 7. Residual uncertainties

Line impedance; F1 pre-arcing I²t and clearing time; the bus-cap discharge
interruption method; U9's failure mode (whether it fails short or open, and
whether U10 also fails); and the diode-short case's likelihood.
