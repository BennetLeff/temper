# BENCH-RMS: true-RMS inlet check of the proposed aux allowance and e_est

This bench step confirms `blower_aux.patch` before it ships. The patch
replaces the IRM linear-sum allowance with modelled inlet-RMS increments. Every
expected value below is in `aux-load.json`, produced by `python3 aux_load.py`,
under the key `firmware_model_proposed` unless another key is named. If the
model changes, re-run the script and re-read the values; never edit them here.

The step fits inside the existing e_est qualification (COMMISSIONING.md step 7)
and step 8c, and uses the same analyser.

## What is checked

The firmware bound is

    inlet_bound = i_ps,est * (1 + e_est) + I_aux,allowance(blower state)

It must be at least the true-RMS line current, and the allowance must cover what
the auxiliaries actually add. What they add is their **increment**,
RMS(i_bridge + i_aux) − RMS(i_bridge), measured at the hold. It is not their
stand-alone RMS.

## Setup

- **Supply:** a variac at 108, 120 and 132 V (±0.5 V at the inlet, under load).
- **Analyser:** a power analyser with true RMS, ≤ 0.1 % of reading +
  0.1 % of range, and bandwidth ≥ 100 kHz.
  - **CH1:** the inlet, I_line.
  - **CH2:** the bridge's own AC feed, downstream of the PS2 and PS3 mains
    taps (F2 / J11). This is I_bridge. Tap point, confirmed by the power-stage
    session from `power_stage_120v.ato` (2026-10-15):
    - **No wire carries only the bridge current.** BR1.AC1 / AC2 sit on
      L_FILT / N_FILT, after L1. The same nodes feed:
      - the X2 cap (1 µF);
      - the Y caps;
      - the line zero-cross sense;
      - the J3 TCO loop (L_FILT → TCO → TCO_L), which feeds only PS2;
      - F2 → R130 → J11 (BLW_LR / N_FILT), which feeds only PS3.

      BR1 itself is board-mounted on the heatsink.
    - **CH2 is therefore a clamp on the J1 line conductor, with one J3 lead
      and the J11 line lead (pin 1) passed through it backwards.** Both are
      off-board wires to the chassis TCO and to PS3. CH2 then reads
      i_bridge + i_X2 + i_Y + i_zc.
    - **The extra terms don't matter.** The X2 current is about 45 mA at
      120 V, 90° out of phase, so it adds ≈ 0.08 mA to the RMS at 13 A. The
      Y and zero-cross currents are smaller still.
    - **Clamp only:** every conductor here is at mains potential, so use no
      shunt.
  - Log the harmonic content of CH2 to h7 as well.
- **Channel cross-calibration:** before each line voltage, pass the bridge
  conductor through both CH1 and CH2 at the hold, so both see the same current.
  With the CH2 arrangement above, use the J1 line conductor alone through
  both clamps, without the reversed J3 / J11 leads.
  - Record g = CH1 / CH2 and divide every later CH1 reading by g.
  - The repeatability of g, as 2σ over 10 readings, is U_cal.
  - This keeps channel gain mismatch, about 2 × 0.1 % × 13 A ≈ 26 mA, out of
    the increment.
- **Firmware:** a commissioned image with the patch applied.
  - Log the following telemetry at ≥ 10 Hz: `last_half.est.i_ps_a`,
    `last_half.est.inlet_bound_a`, `aux_a`, `freq_reason`, and the blower
    duty and rpm.
  - Force the blower through a bench hook, with the fan law bypassed and the
    state known.
- **Pan:** the high-R test pan, on which the inlet limit binds first.
  - Confirm `freq_reason` is UP_INLET or HOLD_LIMIT at every point. A point
    held by the tank ceiling is not at the hold and does not count.

## Grid

Measure 9 points: 3 blower states × 3 line voltages. Hold each point for at
least 30 s, then average over 10 s.

| Blower state | Forced command | Allowance (`allowance_A.*.proposed`) |
|---|---|---|
| off | FAN_OFF, tach < 300 rpm | 0.310 A |
| mid | GPIO46 duty 0.50 | 0.597 A |
| full | duty 0 | 0.887 A |

At each point, record:
- I_line (CH1 / g)
- I_bridge (CH2)
- dI = I_line − I_bridge
- i_ps,est
- inlet_bound
- the CH2 h3 / h1 ratio
- real power on both channels

## Pass criteria

1. **Bound covers reality (safety).** At every point,
   inlet_bound ≥ I_line − U_line, where U_line is the analyser's
   uncertainty. If this fails, it is a FAIL whatever else holds.
2. **The allowance covers the increment.** At every point,
   dI + U_cal ≤ the allowance for that state from the table above.
   - If this fails: do not ship the patch. Keep the stage-16 constants and
     report the point.
3. **The model is conservative.** At every point, dI + U_cal ≤ the
   worst-corner model value for that line and state
   (`worst_increment_by_line_and_duty_A`).

   | Line | off | duty 0.50 | full (duty 0) |
   |---|---|---|---|
   | 108 V | 0.2538 | 0.5001 | 0.8815 |
   | 120 V | 0.2321 | 0.4545 | 0.7997 |
   | 132 V | 0.2135 | 0.4160 | 0.7310 |

   A point between this model value and the allowance is not a ship-stop,
   because criterion 2 still holds. It does mean a model input is wrong.
   Check these in order:
   - the CH2 h3 against the assumed 20 %;
   - PS2's bias frequency against the 80 kHz allocation;
   - the logic load against 4.83 W.

   Then re-run `aux_load.py` with the measured value.
4. **Plausibility (informational).** At 120 V, dI should sit near the
   typical rows (`results.typical/*.rms_increment_at_hold_A`): about 0.10,
   0.19 and 0.33 A for off, mid and full.
   - A value **below** these is fine.
   - A value more than 2× **above** them means the bench differs from the
     model. Explain it before using the result.
5. **e_est (estimator only).** e = I_bridge / i_ps,est − 1 at every point
   must be ≤ the e_est in force (0.10 provisional).
   - This is the power-stage estimator error with the auxiliaries removed by
     measurement, not by allowance.
   - Fold it into step 7 as that step specifies, using the allowance as
     I_aux, never the auxiliaries' stand-alone RMS.

## Record

Commit the analyser CSV for each point and the telemetry log. Commit a table
of I_line, I_bridge, dI, U_cal, i_ps,est, inlet_bound, the allowance, the model
value and the h3 ratio, with pass or fail on criteria 1–3 and 5. Save it next
to this file as `bench-rms-<date>.csv`.

When the data passes, replace `base_a`, `ps3_eta × ps3_pf` and `idle_a` from
the measured increments, as described in COMMISSIONING.md step 8c.4. Pin the
new values in `test_blower_aux.c`.
