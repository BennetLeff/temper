# What temper should do: round 3, ranked

Owner, evidence tags (see FINDINGS.md), confidence and effort are given for each item.

1. **Decide the power and nameplate target explicitly, because it is temper's biggest competitive gap.**
   - Owner: product + power-stage. Tags: model, yt, reg, web. Confidence H. Effort M.
   - At 1.33 kW input, temper boils 1.35–1.63× slower than the Control Freak in the same test, and is slower than $50 commodity units.
   - Options:
     - (a) Recover current: measure input current, size the auxiliary allowance to the real load, and resolve the thermal limit near R5.
     - (b) Go to a 15 A nameplate as the Control Freak does. NRTL listings at 100 % are common, but NEC 210.23(A)(1) says 80 %, so check with the certifier.
     - (c) Accept the slower boil and position on precision only, with copy to match.
   - The current 13.5 A inlet target fits neither the code-conservative 12 A nor the market's 15 A.
2. **Make "safe with the controller dead or stuck" the certification strategy, and test it.**
   - Owner: power-stage + controller + cert. Tags: reg, said. Confidence H. Effort M.
   - The UL 858 25.3.1 exception (safe with the solid-state control totally or partially inoperable), together with SA3, is how hardware-first safety keeps firmware out of protective Class B evaluation.
   - Impulse needed 18+ months with firmware in the certification.
   - This makes sensor-r3 CR-3 (runaway divider on S−) and CR-5 (hardware rim-NTC trip) **certification-critical**, not just accuracy fixes.
   - The firmware supervisor's 35 s stuck-on-with-dead-current-sensor case must be covered by hardware.
3. **Add the UL 858 59.6 bar to pan detection.**
   - Owner: firmware + power-stage. Tag: reg. Confidence H. Effort L.
   - The test: an iron bar 2 mm × 100 × 20 mm in the worst position, highest setting, rated voltage, rise ≤ 35 °C.
   - Add it, plus a fork, spoon and knife, to the pan_detect re-validation set (round 1, item 6).
4. **Expand the "bad pan" set with temperature-dependent pans.**
   - Owner: power-stage + firmware. Tags: doc, said. Confidence M. Effort L.
   - Add Demeyere ControlInduc (self-limits at about 250 °C) and Proline (misbehaved on the Control Freak) next to round 2's thin-stainless multi-ply aluminium pan.
5. **Keep temper portable by DOE's definition.**
   - Owner: product + enclosure. Tag: reg. Confidence H. Effort none.
   - "Designed to be moved from place to place" keeps it outside the 2028 IAEC limit of 207 kWh/yr.
   - A built-in or drop-in variant would need DOE testing and certification.
6. **Write the FCC frequency guard into the requirements.**
   - Owner: power-stage + firmware. Tag: reg. Confidence H. Effort L.
   - Keep the operating frequency below 90 kHz in every mode, including dither, pan detection and fault recovery. That keeps temper in 18.305's 1,500 µV/m class rather than 300 µV/m.
   - Plan for SDoC under Part 18 for the induction function. The ESP32 radio is Part 15 under its modular grant, with "Contains FCC ID" labelling.
7. **Turn the Control Freak's weaknesses into temper requirements and marketing.**
   - Owner: sensor line + product. Tags: doc, web. Confidence M. Effort L.
   - Its weaknesses:
     - its own error list includes "sensor rubber broken / stuck down";
     - its sensor needs keeping "free from oil build-up";
     - it pulses at low power;
     - its UI scrolling is slow;
     - it costs $1.3–1.5k.
   - C1's captive wiper and sponge-wipeable recess (round 2, item 5) answer the first two. Measure the Control Freak's own ±1.8 °F claim on the bench before claiming better.
8. **Don't claim "continuous control" below the floor, but don't re-engineer the burst mode either.**
   - Owner: product + firmware. Tags: model, said. Confidence M. Effort none.
   - At the 160 W floor with 20 s bursts, ripple is ≤ 0.9 K at the contact and ≤ 2.9 K at the hottest ring.
   - Low-temperature modes (sous-vide-style 60 °C pan holds) work inside that ripple.
9. **Impedance cross-check: a plausibility channel only, and after an FTO.**
   - Owner: firmware + sensor line. Tags: model, patent, paper. Confidence M. Effort M.
   - R_eq = P/I² can flag contact loss and dry-pan runaway in carbon steel to about 4–11 K, but only 11–30 K in cast iron and clad.
   - Avoid the claim elements of E.G.O. US10085303B2 (resonant frequency at a held bus voltage, to 2035) and Whirlpool US8530805B2 (model tuning on R0(1 + αΔT), to 2032).
10. **Engage an NRTL early, choosing UL 858 or UL 1026.**
    - Owner: cert. Tags: reg, web, said. Confidence M. Effort M.
    - Portable induction units are certified under UL 1026 in practice (Kenyon/TÜV). UL 858 has the induction-specific clauses (47.7/47.8/59.6) and the smart-enabled supplement.
    - Ask the NRTL which one applies, whether Wi-Fi remote functions bring in SA, and for the touch-current limits. Book a preliminary review now, given Impulse's 18-month path.

**Lower priority:**
- Route coil-eye and heatsink wiring with insulation rated above the modelled local temperature. SMEG's field failure was melted wire insulation; sensor-r3 CAD already does this for the cartridge.
- Watch Impulse Core licensing (Zephyr, THOR, BS Service). A licensed 120 V module would be a direct competitor, or a possible supplier.

## Contradictions with current temper decisions

- **Power target.** The 13.5 A inlet with a 10 % estimate margin (1.33 kW held) contradicts the product's competitive class (1800 W, 15 A). This is item 1.
- **Firmware safety scope.** The C1 firmware supervisor carries safety logic (35 s stuck-on detection). Under the 25.3.1 strategy, firmware must not be the barrier anywhere, so every firmware-detected hazard needs a hardware backstop shown in test. This is item 2.
- **No contradiction on burst mode, the NO_PAN timeout, or the operating frequency.** All three comply and are adequate. The NO_PAN grace could be lengthened up to UL 858's 30 s for user experience (tossing food); that is a product choice.
