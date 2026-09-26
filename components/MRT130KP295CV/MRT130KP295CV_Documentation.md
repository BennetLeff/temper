# MRT130KP295CV — DC-link TVS

**Selected part:** Microchip MRT130KP295CV, bidirectional axial transient-voltage suppressor. D3 connects directly between BUS_P and HV_RET in the 120 V power stage. It is intended to limit returned tank energy and rectified surge stress; it is not a proved 520 V bus bound.

## Ratings and land pattern

- Stand-off voltage: 295 V. Minimum breakdown: 300 V at 5 mA.
- Manufacturer pulse condition at 25 °C: maximum 410 V at 282 A for a 6.4/69 µs pulse. The rating does not include formed-lead or PCB loop inductance, hot operation, or repeated pulses.
- Source pins 1 and 2 are interchangeable for this bidirectional device. The unit footprint is `temper:MRT130KP_Axial_P20.00mm_ReviewOnly`: pad 1 `(0,0)` and pad 2 `(20,0)` mm, each Ø3.2 mm copper / Ø1.6 mm drill. Body maximum is 12.954 mm long × Ø7.874 mm; lead maximum is Ø1.3462 mm. The 20 mm formed pitch is a prototype assembly choice, not a manufacturer board recommendation.

The OVP restart threshold has an estimated upper corner near 286 V, only about 9 V below stand-off. The requested ≥2 J absorption and ≤520 V at the MOSFET terminals remain design targets. Qualify the actual current-time waveform, temperature, surge coordination, formed-lead geometry and voltage at the capacitor **and** MOSFET terminals. No powered clamp test has run.

Sources: [Microchip datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/HRDS/ProductDocuments/DataSheets/130-kW-Transient-Voltage-Suppressor-TVS-Device-00005551.pdf), [unit footprint and drawing notes](../../zapote/power-stage-120v/FOOTPRINTS.md), [clamp assessment](../../zapote/power-stage-120v/DC-LINK-CLAMP.md).
