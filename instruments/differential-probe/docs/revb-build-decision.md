# Rev B build decision — 2026-10-20

Build the existing Rev B circuit and layout. Keep **HVCB2512BDE1M00, 1 MΩ, 0.1%, twenty pieces**, the 4.99 kΩ 0.01% bottom resistors and 50 Ω trimmers. The separate 0.1%-versus-1% ladder experiment is cancelled: its cost is not justified for this one-off instrument. Use the ordinary Rev B calibration and qualification procedure. No resistor substitution or compensation change is part of this decision.

Keep battery power and both ranges. USB power is deferred. Pods and a lumped divider remain Rev C candidates, informed by Rev B's measured strays, compensation, loading and enclosure behavior. A future lumped divider must retain at least two independent series impedance sections, not one resistor body per leg.

The confirmed procurement target is five PCBs and two populated boards from JLCPCB; the user selected two after JLC's form required that assembly minimum. Shipping is to Austin, Texas; private delivery details belong in the vendor account, not this repository. No purchase has been completed. See [procurement status](../procurement/README.md).

## Fault and operating requirements

1. **Protective impedance:** each input leg must contain at least two independent series impedance sections, each able to withstand the full intended tip voltage when the other section is bypassed, for the specified waveform and duration. Verify voltage, power, pulse energy, capacitor bypass paths and physical separation together. Two bodies are a minimum architecture requirement, not proof of protective-impedance qualification. Rev B has multiple series elements; its compliance with the full fault requirement is **not yet established**.
2. **Insulation:** retain the existing 10 mm air / 20 mm PCB creepage budget from the full-voltage tip to low-voltage/earth circuitry, with the routed slots intact. Take no credit for coating, potting or solder mask. Retain the separate **20 mm shield/enclosure setback** from exposed HV conductors, including leads and solder joints. Cleanliness, component-body paths and final assembly inspection remain part of qualification.
3. **Operating setup:** use this prototype on stage 53 only with the isolation-transformer-fed DUT and no additional galvanic HOT-to-earth reference. Keep the oscilloscope's protective earth intact. Audit probe grounds, supply negatives, analyser terminals, debug cables and connected equipment before power. Batteries provide no additional supply cable; the BNC is the probe enclosure's intended external earth connection. Do not defeat equipment PE to satisfy this condition.
4. **BRING-UP exception:** stage-53 COMMISSIONING deliberately bonds `hv_ret` to PE during steps 2–4. This prototype's restricted operating setup does not apply there: use the procedure's independently rated instrumentation. Do not remove that prescribed bond early. The prototype becomes a candidate only after the documented bond removal before BR1 fitting and completion of its own qualification.
5. **Fault energy:** the isolation transformer is an operating restriction, not a fault-current rating. The other probe leg, its compensation capacitors, DUT Y capacitors, transformer capacitance and stored charge still provide earth-current paths. A single HV-to-earth event can produce a substantial transient. Do not claim safe BNC behavior from the absence of a second ground clip alone.

## Why the full-voltage claim needs correction

The selected 1 MΩ resistor is listed as **2 W**. Applying 3 kV DC to one body would dissipate **9 W**; even a 3 kV-peak sine would dissipate 4.5 W. The continuous power-limited voltage at 2 W is only `sqrt(2 W × 1 MΩ) = 1.414 kV`, before thermal derating. A catalog 3 kV limit does not override this. Thus “each resistor individually survives the full 3 kV” is not established. [Exact-part listing and manufacturer datasheet link](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/HVCB2512BDE1M00/5824166).

Under intact sharing each body sees about 300 V and 90 mW at 3 kV DC, a very different condition. A shorted resistor or top capacitor cannot directly short the whole string, but an open component can concentrate voltage and initiate secondary breakdown. The existing single-fault study remains applicable; these requirements define the intended scope without promoting untested survival to a result.

Rev B may be fabricated as an engineering prototype for the existing staged qualification. This decision is not a high-voltage operating release. No new resistor-comparison campaign is required.
