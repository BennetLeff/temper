# Single-resistor, lumped-compensation divider

**Research, 2026-10-20; no circuit, BOM or CAD change.** This evaluates the [Rev B divider](../design.md): DC–5 MHz small-signal response, 2000:1 per leg, 35–60 kHz application, and simultaneous tip/differential limits initially ±1.5 kV, potentially ±3 kV. The existing qualification status remains unmeasured.

## Verdict

**Worth a two-leg coupon experiment, but not yet a replacement.** A single resistor removes nine PCB resistor junctions per leg and can greatly shorten the HV section. It does not remove the resistor's internal distributed field, shield capacitance, or capacitor midpoint. Neither 60 dB broadband CMRR nor a complete 30 mm divider assembly follows from the reduced part count.

The ideal replacement is `10 MΩ || 6.6 pF` above `5002.501 Ω || 13.1934 nF`: both time constants are 66 µs and attenuation is 2000:1. Here 6.6 pF means **total effective tip-to-tap capacitance**, including resistor and mounting parasitics, not just fitted capacitors. Input-to-earth capacitance adds loading separately.

## Resistor candidates and traps

Manufacturer limits below are working/operating voltage ceilings, also restricted by `sqrt(Pallowed × R)`. They are not impulse or accessible-insulation qualifications.

| Exact candidate | Manufacturer nominal ratings | Geometry and decision |
|---|---|---|
| Ohmite **MOX-750231005FE** | 10 MΩ, 1%, 1 W at 25°C, 5 kV; catalog capacitance 0.75 pF | Axial body 22.35 × Ø4.19 mm. Compact initial-envelope candidate; only about 0.10 W nominal power margin at 3 kV DC. |
| Ohmite **MOX1125231005FE** | 10 MΩ, 1%, 1.5 W at 25°C, 7.5 kV; 0.25 pF | Axial body 32.26 × Ø4.19 mm, before formed leads/lands. Better power margin, cannot fit a 30 mm longitudinal envelope. |
| Ohmite **SM102031005FE** | 10 MΩ, 1%, 1 W at 25°C, 5 kV; 0.90 pF | 14.73 × 2.54 mm body, 8.64 mm height, 10.16 mm pin pitch. Short package creates a full-voltage PCB-spacing problem. |
| Ohmite **SM104031005JE** | 10 MΩ, 5%, 1.5 W at 25°C, 10 kV; 0.70 pF | 27.43 × 2.54 mm body, 8.64 mm height, 22.86 mm pitch. Strongest compact geometry candidate; tolerance needs selection/calibration range review. |

Sources: [Mini-Mox manufacturer data](https://www.ohmite.com/mini-mox/), [exact MOX1125 record](https://www.ohmite.com/catalog/mini-mox-series/MOX1125231005FE/), [Slim-Mox manufacturer data](https://www.ohmite.com/slim-mox/), [exact SM104 record](https://www.ohmite.com/catalog/slim-mox-series/SM104031005JE/).

Mini-Mox offers 25 ppm/°C over 0–85°C; broader-temperature coefficients differ. Slim-Mox offers 25 ppm/°C options, while distributor data for the exact SM102 FE lists 50 ppm/°C: do not assume the best family option applies to every order. At 10 MΩ both families publish VCR below 2 ppm/V. A conservative 3000 V multiplication permits nearly 0.6% resistance change—already above a 0.1% CMRR-matching budget. VCR tracking and self-heating must be measured. Mini-Mox's separate 750 V dielectric-withstand test is not its end-to-end working rating and does not certify a grounded shield near its coating. [Ohmite data](https://www.ohmite.com/mini-mox/)

Calculated dissipation is 0.899 W at 3 kV DC, 0.450 W at 3 kVpk sine; at 1.5 kV these become 0.225/0.112 W. Apply the actual temperature derating curve; a “1 W” title is insufficient. Availability observed online: [MOX750](https://www.digikey.com/en/products/detail/ohmite/MOX-750231005FE/823626), [MOX1125](https://www.digikey.com/en/products/detail/ohmite/MOX1125231005FE/823632), and [SM102](https://www.digikey.com/en/products/detail/ohmite/SM102031005FE/4300994) have active distributor listings with stock shown; quantities were cached and are not procurement commitments. SM104 exact stock was not established.

## Two series capacitors

Two equal capacitors need **13.2 pF each** to produce 6.6 pF ideally. Two 13 pF give 6.5 pF. **C1812C130JHGACTU** is a family-table/order-code candidate for 13 pF, 5%, 3 kVDC C0G; exact stocked availability was not established. The existing verified **C1812C330JHGACTU** is 33 pF, not a two-series substitute. KEMET's [family data](https://content.kemet.com/datasheets/KEM_C1009_C0G_HV_SMD.pdf) lists E24 values, ±30 ppm/°C C0G behavior, and a short dielectric-withstand test distinct from working voltage.

With SM104's nominal 0.70 pF modeled entirely in parallel, only 5.90 pF external capacitance is needed: equal capacitors approximately 11.8 pF each. This is a starting estimate, not an accurate resistor model. Two 13.2 pF plus 0.70 pF would instead give about 7.30 pF and require roughly 14.593 nF below, far outside the existing fine trim span; coarse values must change.

At 3 kVpk, ideal sharing gives 1.5 kVpk per capacitor; opposing ±5% capacitance tolerances give up to 1.575 kVpk. DC sharing depends on leakage, not capacitance. A floating midpoint and its shield capacitance alter transient sharing. Each part should tolerate the credible full voltage after its partner shorts, while that failure doubles the external high-frequency capacitance and corrupts gain. An open capacitor loses compensation; an open resistor loses DC indication. Reduced series redundancy also makes a resistor short more consequential.

A 3 kVDC label supplies no verified 60 kHz/5 MHz amplitude envelope. At 60 kHz/3 kVpk, 6.6 pF draws 5.28 mArms; at 5 MHz it would draw 0.440 Arms. The latter is not an allowed operating point. [Murata's AC guidance](https://www.murata.com/en-global/support/faqs/capacitor/ceramiccapacitor/char/0002) illustrates the separate waveform and heating checks; it is not approval of these KEMET parts. Obtain their actual AC/pulse limits. KEMET also recommends coating against surface arcing at ≥1.5 kV and careful cleaning; that is not automatic insulation credit.

## Size, CMRR and deciding experiment

SM104 makes a roughly 30–40 mm **longitudinal component zone** plausible, including lands and routing; this is an estimate. Its 22.86 mm pitch can leave 20 mm between small lands. SM102 cannot meet that inherited surface rule directly. Capacitor slots, full-voltage bypass paths, input termination, opposite leg and shield setback still set assembly size. Rev B's 20 mm creepage/10 mm clearance are prototype constraints, not a demonstrated universal 3 kV minimum. Existing 600 V section slots cannot simply be copied for 1.5–3 kV components.

One low-leg adjustment can cancel an ideal first-order mismatch. Distributed resistor-to-shield coupling creates additional poles/zeros that one adjustment cannot generally cancel. For 60 dB CMRR, the complete complex leg gains must track about 0.1%; at the capacitive plateau that corresponds to only **6.6 fF** equivalent mismatch, or about **32 ps** delay mismatch at 5 MHz. DC and HF trims do not prove tracking between them. Commercial probes also distinguish low- and high-frequency compensation ([Tektronix](https://www.tek.com/en/documents/application-note/how-minimize-probe-loading-low-capacitance-probes-0)).

Build matched SM104 and MOX1125 coupons with adjustable coarse compensation and fixed representative shield/leads. Measure both leg transfers and tied-tip residual from DC through 5 MHz, emphasizing 35–60 kHz; repeat after warm-up, voltage steps, temperature and permitted lead movement. Establish DC gain versus voltage, capacitor sharing/heating and overload recovery separately under controlled qualification. Advance only if the measured CMRR curve, residual phase and voltage envelope outperform the existing ladder without extra compensation complexity.
