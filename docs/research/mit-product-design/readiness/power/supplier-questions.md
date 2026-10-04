# Unsent supplier requests

These are drafts for engineering review. No message or order has been sent. Supply the waveform/temperature records as they become available; the illustrative model points below are **not measured requirements or worst-case bounds**.

## CDE / exact resonant capacitor application support

We are evaluating **two 942C12P22K-F (0.22 µF) and one 942C12P1K-F (0.10 µF) in parallel**, 0.54 µF nominal, as the series resonant bank of a full-bridge induction cooker. The intended mains target is 120/127 V, 60 Hz, with a 15 A input limit. The resonant current has a 60 Hz rectified-line envelope; the candidate control range under investigation is 20–60 kHz and includes startup, shutdown, burst/phase changes and pan detuning. Actual operating waveform and temperatures are not yet measured.

Please provide written application limits for **each exact part number**, identifying guaranteed versus typical data and the required installation conditions:

1. Continuous allowable AC RMS voltage and RMS current versus frequency and ambient/case/hotspot temperature, including how to assess nonsinusoidal harmonics and burst envelopes. Which thermal point and averaging interval should we use? Does the catalogue's 70 °C/100 kHz current row transfer to this lower-frequency, line-modulated application, and by what method?
2. Peak voltage, reversal, dV/dt, pulse current, repetitive/transient energy and lifetime limits for the actual waveform; simultaneous use of limits, required derating and measurement uncertainty. Is a hot high-frequency lifetime calculation supported?
3. ESR/ESL and tolerance versus frequency/temperature, including the bounds needed to assess unequal branch sharing. We will measure every branch; capacitance ratio alone is not a qualified sharing rule.
4. Permitted lead-forming distance/radius, supported pitch, minimum PCB/body clearance, vibration restraint, compatible adhesives and mounting temperatures. Current provisional footprints use 42.5 mm formed pitch and horizontal axial bodies; please approve or correct that construction from a drawing.
5. If unsuitable, propose exact orderable alternatives with these limits, package drawing, approved lead form, availability and traceable change control. Please distinguish production availability from distributor snapshot stock.

For context only, the inherited nominal tank-loss model predicts 18.7 A bank RMS. Ideal capacitance sharing gives 7.62 A per 0.22 µF and 3.46 A for 0.10 µF; independent ±10% capacitance extremes give individual maxima of 8.54 A and 4.07 A at that same **fixed assumed** bank current. These maxima are not simultaneous and omit ESR/ESL and transient effects. The old 650 V peak screen is unqualified and is not an application specification. We will provide actual per-branch RMS/peak spectra, envelope/duty, temperatures and lead construction before requesting final suitability.

Source: [CDE 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf), pp. 1, 3–4. Live fetch returned HTTP 403 on 2026-10-04; this review inspected the already recorded local manufacturer PDF and its exact-part table. Request a current revision from CDE rather than treating the access failure as confirmation that the saved catalogue is current. The saved table's 430 Vac basis is 60 Hz; its current rows are at 70 °C/100 kHz. Neither alone qualifies this application.

## Coil / ferrite assembly supplier

Please quote an **engineering characterization specimen**, not a production release, for the existing approximately 200 mm coil envelope. The current 70 µH no-pan value is provisional. Provide exact winding/litz/ferrite construction, dimensional and electrical tolerances, loss versus frequency/current/temperature, insulation system and temperature class, mounting/retention drawing, terminal ratings and strain relief, and lot traceability. Identify whether the nominal inductance is measured with or without a pan, at what frequency and signal level, and on what fixture. We need samples with the actual lead dressing, support and ferrite used in the final design.

Provide feasible alternative winding/bank combinations within the unchanged physical allocation, with data rather than nominal inductance alone. We will compare measured cookware impedance and thermal behavior before selecting an alternative. Do not infer approval for a 140 µH replacement from the exploratory model ranking.

## Protection/device application questions for the power engineer

- **TI / TLV3201:** characterize or bound delay and output behavior for the actual low-overdrive ramp/RC waveform, supply and temperature corners. The specified 55 ns at the datasheet test condition is not a guaranteed threshold-to-trip bound for arbitrary waveforms. Include effects of changing U8 from the existing two-input logic to the HOT5 three-input NAND.
- **Infineon / IPW65R018CFD7:** confirm applicable hot on-resistance envelope, pulse/SOA/avalanche restrictions and body-diode recovery behavior for the chosen commutations. Ask whether any short-circuit withstand guarantee exists for the proposed conditions; absent such a guarantee, require bounded circuit analysis and controlled tests. Submit real switching waveforms when available, not the positive-terminal-power proxy as measured dissipative heat.
- **Vishay / WSK2512R0010FEA:** confirm selected assembly's continuous and pulse loading, terminal temperature/PCB heat-sinking assumptions and resistance drift. The current 1 W at 70 °C local-ambient derating curve does not establish element temperature or fault-energy survival in Temper.

Keep each reply with date, named technical contact, document revision, exact MPN and stated conditions. Transfer accepted limits into one component-limit table with provenance; unresolved cells remain blank and block the affected release decision.
