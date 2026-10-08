# Burst-mode flicker screen (low-power control, DECISIONS.md 2026-10-05)

**Answer:** bursts are flicker-compliant on this screen **only if the burst
period scales with the burst power**. That means ≥ 2.5 s at 160 W, ≥ 10.3 s at
250 W and ≥ 18.5 s at 300 W. The **1 s window first written in the decision fails**:
two steps per second also falls outside the analytical method's ≥ 1 s spacing.
The firmware rule is therefore:

    T_burst >= max(2 s, 4.6 * d^3.2 / 0.65^3.2),   d[%] = 100 * (P/(V*PF)) * (R cos phi + X sin phi) / V

using the measured burst power. A fixed **20 s** default covers floors up to
300 W. With 8.33 ms half-cycle granularity, the average-power resolution is
P × 8.33 ms / 20 s (0.13 W at 300 W). The water bath's time constant is minutes,
so a 20 s window is invisible to the temperature loop.

[`burst_flicker.py`](burst_flicker.py) → [flicker.md](flicker.md) / [flicker.json](flicker.json).
Method: IEC 61000-3-3 Annex B, analytical, rectangular steps (F = 1),
Pst = (Σ t_f / 600)^(1/3.2), limits Pst ≤ 1 and Plt ≤ 0.65 (steady repetition, so Plt = Pst).

**Limits:** this is a screen, not compliance. IEC 61000-3-3 is a 230 V standard;
its 0.4 + j0.25 Ω reference impedance stands in for 120 V service (typical North
American service impedance is lower). The analytical formula uses the 230 V lamp
curve, whereas IEEE 1453 uses IEC 61000-4-15 with the more sensitive 120 V lamp.
PF = 0.95 is assumed. The closing evidence is an IEC 61000-4-15 (120 V lamp)
flickermeter run on the measured burst current.
