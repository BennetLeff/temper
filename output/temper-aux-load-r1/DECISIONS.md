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
   power-stage owner's decision, gated on the B3 R5 / C40 cases at the higher
   hold and on a bench true-RMS check. This folder makes no firmware or board
   change.
