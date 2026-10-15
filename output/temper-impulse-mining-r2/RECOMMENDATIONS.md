# Recommendations: Impulse mining, round 2 (ranked by impact)

Evidence is in `FINDINGS.md`. The owner of each item is in brackets.

1. **Bad-pan test set** [power-stage session and firmware; said, yt]
   - **Test:** a multi-ply aluminium pan with a thin stainless base, at full
     power from cold to 250 °C.
   - **Show:** the control loop (`pll_control.c`) stays stable, and the
     hardware overvoltage and overcurrent trips (about 280 V,
     `power_stage_120v.ato:601`) fire before any switch is overstressed.
   - **Why:** Impulse lost transistors in the field to exactly this pan
     (C1).
2. **Factory sensor check and firmware regression rig** [product/QA and
   sensor line; yt]
   - **At the factory:** place a reference pan on every unit, and require the
     sensor reading to fall in a set range.
   - **Before each firmware release:** log thermocouple-welded pans over USB
     and compare them with the stove's estimate. The sensor-r3 bench kit's
     logger is a starting point.
3. **No tactile reset or boot buttons where a ribbon or harness can reach
   them** [controller board, ESP32-S3; yt]
   - Use test pads instead.
   - Add a transit-vibration test before the first build.
4. **Define what the set temperature means, and which pans to recommend**
   [sensor line and product; said, yt]
   - Decide whether it is the pan's top surface or the sensor reading.
     Sensor-r2 uses the contact point.
   - Recommend tri-ply, and state that cast iron and carbon steel read less
     accurately. Impulse has the same limit.
5. **Cleanable sensor recess** [sensor-r3 and CAD; said]
   - The recess must be wipeable with the edge of a sponge.
   - Add this as a requirement for the C1 wiper/collar geometry.
6. **Throttle and pause behaviour** [firmware; doc]
   - Turn the burner off 30 s after the pan is removed. Pause when the pan is
     lifted and resume when it returns.
   - Show residual heat.
   - Show a throttle indicator for unusual heating or pans that don't
     respond.
   - Cap dry-pan preheat at about 2.5 kW.
7. **Heat-up speed setting** [firmware/UX; yt] Expose sensor-r2's ramp limit
   as a user-selectable 1–3 setting, as on the Control Freak.
8. **Power-entry reference** [power-entry board session; seen, doc]
   - Copy the pattern: a two-stage common-mode filter, RTV-staked
     Y-capacitors, an earth screw next to them, MOVs, and fuse warning text
     in the silkscreen.
   - Rate the 120 V nameplate at ≤ 12.5 A, as Impulse does.
9. **Knob** [R44 controls; seen, said]
   - This confirms R44's direction: magnetic knob, lift = off, no-knob
     inhibit.
   - Add magnetic viewing film as a polarity check in assembly QA.
10. **Assembly practice** [manufacturing; seen]
    - RTV-stake tall parts.
    - Put QR labels on every board and harness branch.
    - Leave spare room in the enclosure ("you can't buy more space
      afterwards").
11. **Low priority** [inferred]
    - Cellular and i.MX-class connectivity.
    - Conformal coat on the coil-centre board.
    - A fan-noise note for under-cabinet airflow.
