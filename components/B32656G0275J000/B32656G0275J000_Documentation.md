# TDK B32656G0275J000 — four-lead DC-link capacitor

**Selected part:** TDK 2.7 µF ±5%, 1000 VDC polypropylene radial capacitor. C5/C6 provide 5.4 µF nominal bulk capacitance in parallel across BUS_P and HV_RET; four smaller local capacitors bring the nominal bus to 5.8 µF. The TDK table gives 22.8 A RMS at **85 °C and 100 kHz**, which is not an all-frequency or assembled-bank rating.

The unit footprint is `temper:TDK_B32656G0275J000_4Pin_P37.50_P20.30_ReviewOnly`. Local pad convention: pads 1 `(0,0)` and 2 `(0,20.3)` mm join BUS_P; pads 3 `(37.5,0)` and 4 `(37.5,20.3)` mm join HV_RET. Each pad is Ø2.8 mm with Ø1.8 mm drill for Ø1.2 ±0.05 mm leads. The datasheet drawing does **not** number the four leads. The same-end electrode pairing is an engineering interpretation and **must be checked for continuity on received parts** before assembly or energizing. The capacitor is nonpolar.

Maximum body envelope is 42 × 33 × 48 mm (length × width × seated height), with 37.5 ±0.4 mm span and 20.3 mm pitch between same-end leads. The four leads do not prove vibration retention or loop inductance; check enclosure clearance, mechanical restraint, ripple current division and temperature. The 1000 V nameplate removes the former 600 V capacitor limit but does not qualify tank-energy return, TVS pulses or 650 V MOSFET stress. The local pattern is for review; no exact 3D model is asserted.

Sources: [TDK series datasheet and drawing B1](https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf), [TDK product page](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32656G0275J000), [footprint derivation](../../zapote/power-stage-120v/RADIAL-FOOTPRINTS.md), [bus screen](../../zapote/power-stage-120v/BUS-CAP-SCREEN.md).
