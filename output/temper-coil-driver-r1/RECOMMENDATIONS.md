# Recommendations

These are addressed to the power-stage session unless noted otherwise, and
ranked by impact. Confidence is shown as H (high), M (medium) or L (low). They
are change requests: no design source was edited.

1. **Fix the pan-resistance placement in the EMI model (H; s19b, model only).**
   - **Change:** model the coil as R/2 + L + R/2 between its terminals, with
     the coil capacitance at the terminals.
   - **Why:** today's placement at SW_A adds an artificial I·R common-mode
     term, about 160 V peak at 60 kHz.
   - **Effect:** the earthed-pan worst margin goes from 2.6 to 8.4 dB. The
     binding line becomes the 70 kHz differential-mode 2fs line.
   - **Verify:** rerun `emi_split_cap.py`. On the bench, measure common-mode
     current from the coil terminals to PE with the pan floating and with it
     earthed.
2. **Measure bus current with an AMC1301 on R5 (H/M).**
   - **Change:** power it from the HOT5 domain like the AMC1311 and add an RC
     filter. Extend J4 to 2×9, or put this on the controller side.
   - **Why:** native-21 has no input-current measurement, and the 10 %
     estimate costs about 13 % of nominal power. Impulse measures it (ACS773).
   - **Effect:** the 15 A-plug hold goes from 11.09 A to 11.9–12.05 A (+7–9 %
     power). It also gives measured pan power for η/C identification
     (`output/temper-sensor-r2`) and pan classification.
   - **Verify:** compare against true-RMS line current at 108, 120 and 132 V
     over the pan grid.
   - **Power-stage reply (2026-10-15):** logged as an open item in
     `zapote/power-stage-120v/OPEN-ITEMS.md`. It rides with the
     candidate-23 SELV-side lane.
     - The board of record is now s35 (DECISIONS 44).
     - A thermal-ratings audit puts still-air board copper near R5 at about
       4 K above the laminate's 130 °C MOT at 22 A.
     - So the +7–9 % power gain may be capped thermally rather than by
       current-measurement error. Re-check this item against that audit
       before claiming the gain.
3. **Dither the frequency in firmware (M).**
   - **Change:** triangular, ±1 kHz, one period per line half-cycle.
   - **Effect:** −8.5 to −10.5 dB band-A QP in the model. It may relax the
     100 µH differential-mode inlet inductor, which still has no part number.
   - **Verify:** ZVS margin at fs − 1 kHz against the 150 ns audit, power
     ripple, and an LISN pre-scan.
4. **Keep a comb electrostatic shield as the fallback (M).**
   - **When:** only if bench common-mode results are poor. It would be a
     radial comb under the glass, returned to bus_n.
   - **Effect:** 10.7–11.1 dB in all coupling cases.
   - **Costs:** insulation coordination (the shield is live), an eddy-loss
     check, and an FTO read of parent application 19/292,752.
5. **Run a weighted touch-current test (enclosure and certification).**
   - **Test:** touch current through an earthed pan with the UL 101 /
     IEC 60990 network. Unweighted it is 2.25–2.86 mA.
   - **If it fails:** split the resonant bank symmetrically; total CV² stays
     about the same.
   - **Otherwise:** don't split it for EMI. It gives 0 dB, or −3 dB with
     asymmetric coupling.
6. **Re-validate pan detection on native-21 (H; controller and firmware
   sessions).**
   - **Change:** redo `pan_detect.c` for the full bridge with a low-energy
     burst, CT and VBUS sensing, a reflected-impedance classifier, and a guard
     for aluminium that reads as a short.
   - **Test set:** aluminium, copper, a ferrous pan under 12 cm, a warped pan,
     an induction disc and no pan.
7. **Coil specification: hot-crimp the litz (M).** Don't solder-tin it under
   the lugs, because solder cold-flows under contact pressure. Check the
   clause in IEC 60335-1 / UL 858.
8. **Add a bus-live indicator LED (L/M).** A low-current LED on the bleed path,
   for service safety.
9. **R27 device mounting (M).** Per-device spring clips are proven in mass
   production; weigh them against the clamp bar.
10. **Architecture rule (H; controller session).** Keep every safety function
    out of OTA-updatable firmware. Temper's hardware-only safety already
    complies.

## No change needed

- **Ferrite:** eight wide radial bars, which temper already specifies.
- **Winding:** two sections, already in temper's design.
- **Power terminals:** press-fit, already used (REDCUBE THR).
- **Controller header:** 2×8, already matches.

## For the sensor work

Impulse's sensor uses a coil-local, isolated multichannel front end (E2, E3).
That is relevant to `output/temper-sensor-r3`.
