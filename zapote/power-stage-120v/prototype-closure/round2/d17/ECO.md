# D17 decisions for the prototype integration owner

Native19 board SHA-256: `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.
These recommendations do not release a current limit or fabrication.

1. **Remove the unsupported receiver timing assertion from electrical source.**
   `elec/src/power_stage_120v.ato` currently calls PERMIT→DIS approximately
   0.35 µs worst case. Replace that comment with the actual 100 Ω/100 kΩ/1 kΩ
   construction and an explicit loaded-waveform qualification requirement.
   The new 96-case circuit sensitivity gives 55.46–716.99 ns just from the
   commanded latch-output edge to DIS reaching 2.3 V. These are assumed
   capacitances/channel models, so even 716.99 ns is not a guaranteed bound.
   Do not silently replace 0.35 µs with another purported worst case.

2. **Keep both detector paths and selected dead-time resistors unchanged.**
   The shunt is a 1 mΩ, four-terminal WSK25121L000FEA. Its nominal 10 kΩ/10 kΩ,
   100 pF input network has 500 ns time constant and 0.5 mV/A gain. Developing
   the comparator datasheet's 20 mV test overdrive corresponds to another
   40 A at that input. A 55 ns comparator table entry alone cannot bound a
   slow fault ramp. Preserve the 396.6–488 ns selected dead-time band; no
   experiment here certifies 45 A operation or supports changing trip values.

3. **Create a dedicated reference-error requirement and accessible differential
   measurement.** Record R5 S1→local comparator/reference return impedance and
   the analog/HOT5 return-current waveform. A proposed ±1 A allocation would
   require |reference displacement|≤1 mV. That is a proposed error budget,
   not an existing requirement. At 30 mA DC it permits only 33.3 mΩ if dynamic
   error is zero; a 0.1 A/µs pulse consumes the entire budget through 10 nH.
   Preserve the existing four-terminal split. Do not add an S1–I1 or S2–I2
   PCB bridge. A separate quiet V15 feed/decoupling branch is a candidate,
   but choosing its impedance requires HOT5 load, dropout and startup checks.

4. **Accept 74AHC30PW,118 as a conditional interlock ECO candidate only.**
   It is an eight-input NAND in TSSOP14 with compatible pin mapping and an
   explicit 3.0–3.6 V hot timing row. It is not yet adopted in the foreign
   interlock source/PCB. The actual 3.135–3.465 V input-level guarantee,
   loading/slew and common-rail collapse still require qualification. AHC
   output Ioff must not be assumed. No additional power-stage pad changes
   are warranted by this substitution alone.

5. **Correct the U13 timing reference:** SN74LVC1G332 at 3.3 V ±0.3 V,
   −40…125 °C, 50 pF is 1.4–6.2 ns. The old 4.5 ns row is for 15 pF and
   −40…85 °C. This does not include the BUS_FAULT harness load. The ISO7710
   5→3.3 V timing is still not qualified by the equal-supply tables.

6. **Do not declare shutdown an energy interrupter.** The finite-energy
   full-bridge screen reaches 428.34 V bus and 1320.77 V resonant capacitor
   in separate cases, despite all gates turning off. Peak current reaches
   136.15 A in another case. These unmeasured diagnostic initial states
   are not predictions of the assembled product; they identify stored-energy
   and phase requirements the next model must include. D22 independently
   finds passive rectifier startup overshoot: integrate precharge and bus
   energy absorption/return requirements, rather than rely on OVP gate-off.
   A shorted power device needs a separate interruption path.

7. **Re-extract after every changed native board.** The fresh native19 copper
   and both-leg mesh records are available, including corrected R5 power
   closure coordinates. Field matrices are NOT_SOLVED. Existing native18
   matrices cannot be attached to this board identity. Full both-leg,
   bulk-current and Kelvin-reference modes, mesh/arch/crop convergence,
   package lead geometry and installed coil/sink coupling remain required.

Primary-source checks, 2026-10-04:
- [TI SN74LVC1G332 Rev E, pp. 3–5](https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf).
- [Nexperia 74AHC/AHCT30 Rev 8, pp. 3–8](https://assets.nexperia.com/documents/data-sheet/74AHC_AHCT30.pdf).
- [TI ISO7710 Rev E, pp. 13–14](https://www.ti.com/lit/ds/symlink/iso7710.pdf).
- [AOS AO3400A Rev 3.1, p. 2](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf): 630 pF input capacitance is typical at VDS=15 V, not a bound at the receiver's operating voltage; 0.65–1.45 V threshold is not a guaranteed turn-off threshold at the actual drain current.
- [TI UCC21550 Rev C, p. 9](https://www.ti.com/lit/ds/symlink/ucc21550.pdf): DIS high threshold maximum 2.3 V. Driver propagation and power-device discharge follow the receiver result.
