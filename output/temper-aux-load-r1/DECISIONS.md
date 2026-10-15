# temper-aux-load-r1 decisions (2026-10-15)

1. **Design state: s38 or later.** PS1 is deleted. PS2 = MPM-20-24 (HOT side,
   TCO-switched). PS3 = MPM-65-15ST, carrying the controller logic after the
   J13 merge plus the blower buck. The power-stage reply quoted s35, but
   DECISIONS 50 and 53 have since moved the board of record to s38 and then
   s41. None of the later stages changes the supplies.
2. **Loads come from the owners' committed budgets**, not re-derived:
   - PS2: the ALT-BIAS.md:163 allocation (A1 modules, adopted at stage 14),
     plus a 20 mA HOT5 bound at 24 V. HOT5 is under 1 % of the total, so it
     was not itemised from datasheets.
   - PS3 logic: the controller verify `ps1.p_total_W` of 4.83 W, all parts at
     datasheet maximum.
   - Blower: Delta BFB1012VH-F00 at 32.4 W maximum / 17.04 W typical, on the
     C28 12.40 V upper envelope, with a 0.9 buck efficiency (as in
     blower_aux.c).
3. **"Typical" logic is an estimate, and labelled as one.**
   - ESP32-S3: 155 mA average, from DS v2.2 Table 5-7 RX at 91 mA plus
     Table 5-9 dual-core 160 MHz at 64.1 mA.
   - OLED: 30 % of its 310 mA typical at 100 % on.
   - Every other part stays at its datasheet maximum.
4. **Module model.** The bulk capacitor comes from the hold-up time; series R
   is swept. Each module's harmonic content is then inflated until its
   full-load RMS matches the datasheet AC current. This was chosen because no
   physical (C, R) variant reproduces the datasheet figure; the datasheet
   figure is the higher one, so matching it is the conservative side.
5. **The metric is the increase in total RMS** at the hold point,
   RMS(i_ps + i_aux) − RMS(i_ps), worst over the calibration variants. This
   is the quantity the 15 A plug limit actually sees. The linear sum of
   module RMS figures is reported alongside, as a bound.
6. **Worst corner:**
   - 108 V;
   - PS2 bias at the 80 kHz allocation;
   - everything else at datasheet maximum;
   - efficiency at typical − 5 points;
   - h3 = 20 % with the worst sign.

   The datasheets publish no efficiency or current versus temperature, so no
   separate temperature corner exists for the modules. Their derating limits
   output power, which is checked elsewhere (the controller verify,
   ALT-BIAS).
7. **The gain is not claimed beyond what the model shows.** Adoption is the
   power-stage owner's decision. The board side is cleared: power-stage
   3998e1044 `line-hold-2026-10-15` shows that R5, C40, the leg copper and the
   bank follow tank current, not inlet current, and the gated rows move
   ≤ 0.1 K at the 13.5 A bound. The firmware change is gated on
   `BENCH-RMS.md`. This folder edits no firmware or board file in place; the
   change ships as `blower_aux.patch`.
8. **Patch base.** The patch was built against branch
   `codex/power-stage-integration` at commit
   **3998e104417484b0178b1c6c93cd935ba49e34ae**, which was
   `git rev-parse codex/power-stage-integration` when the tree was archived.
   - The extracted tree was diffed against that commit and found identical.
   - `git apply --check` passed against that tree.
   - Re-check after candidate 39 merges.
9. **Firmware form: same structure, new constants.** The allowance stays
   base + (1 + margin) × PS3 blower model + idle, capped at the worst case.
   - The IRM figures (a linear sum of datasheet AC currents) are replaced by
     each module's inlet-RMS increment at the worst corner.
   - `ps3_pf` is redefined as the effective power factor of that increment.
     Its lowest value over duty and line is the one used, so one constant
     covers every duty without the margin.
   - This was chosen over a lookup table for two reasons: it keeps the
     fan-law structure that COMMISSIONING 8c.4 refits, and it changes no
     code path.
10. **Base rounds up and the PF rounds down, both at 0.01.**
    - `idle_a` and `margin` stay at 0.05 A and 15 %, even though the new base
      already includes PS3's no-load loss. That margin now covers model error
      rather than a known light-load effect. The bench can reduce it.
    - The worst case keeps no margin. Full speed is only 5 mA over the
      modelled 0.8815 A, and is backed by the worst-corner stacking listed in
      decision 6.
11. **The constants are set at 108 V and are the maximum over 108 / 120 /
    132 V.** The increment falls with line voltage: 0.88 / 0.80 / 0.73 A at
    full. So the 108 V basis also covers the higher lines.
12. **The e_est qualification must subtract the scheduled allowance, not the
    auxiliaries' measured stand-alone RMS.** The stand-alone RMS is larger than
    the increment, so subtracting it would understate e. The patch fixes the
    COMMISSIONING step 7.5 wording. BENCH-RMS measures the increment directly
    with a second channel on the bridge feed.
13. **`drive_0.5` is renamed `duty_0.5` in the json.** It was always GPIO46
    duty 0.5. All other keys and values from r1 are unchanged; this was
    verified by comparing the regenerated json with the r1 json.
