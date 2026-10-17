# Interfaces

| Connector | Pin | Signal |
|---|---|---|
| J1 heatsink | 1 | HS_SENSE, external NTC terminal |
| J1 heatsink | 2 | gnd, other NTC terminal |
| J2 coil | 1 | COIL_SENSE, external NTC terminal |
| J2 coil | 2 | gnd, other NTC terminal |
| J3 host | 1 | +3V3 supply, modeled 3.135–3.465 V |
| J3 host | 2 | gnd, common return |
| J3 host | 3 | HS_FAULT, active-high hot indication |
| J3 host | 4 | COIL_FAULT, active-high hot indication |
| J3 host | 5 | HS_SENSE, raw analog monitor |
| J3 host | 6 | COIL_SENSE, raw analog monitor |

J1/J2 are JST B2B-XH-A(LF)(SN), J3 is B6B-XH-A(LF)(SN). Connector pin numbers, not camera orientation, define the interface. The two sensors are off-board Vishay NTCALUG01A104GA assemblies, 100 kΩ at 25 °C. NTC polarity does not matter; connector power/host polarity does.

The published sensor rating is −55 to 150 °C **without a connector**. JST XH is rated −25 to 85 °C including temperature rise. The PCB and XH connections must remain in the cooler electronics area, with a separately qualified extension harness to the 38.1 mm sensor leads. No assembled harness, crimp selection, installation temperature or cable strain relief has been qualified. [Vishay](https://www.vishay.com/doc/?29092), [JST XH](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf).

The analog outputs are unbuffered and approach VCC at cold/open sensor conditions. Their full range is 0..VCC, up to 3.465 V in the modeled supply envelope. They are not certified for a receiver with a lower usable ADC range. Receiver loading, acquisition, clamps and power-off behavior require integration work. The two digital outputs are push-pull comparator outputs; do not wire them together.

Hot resistance falls, sense voltage falls, and the corresponding hot flag rises. A short to ground reads hot; an open or short to supply reads cold. The comparator has resistive hysteresis but there is no latched shutdown, diagnostics or firmware dependency in this unit. Diagnostic coverage and the downstream shutdown path remain system obligations. The board is not an isolation barrier; the sensor's dielectric test is not a cooker insulation qualification.
