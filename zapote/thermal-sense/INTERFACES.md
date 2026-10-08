# Interfaces

| Connector | Pin | Signal |
|---|---|---|
| J1 heatsink | 1 | HS_SENSE, external NTC terminal |
| J1 heatsink | 2 | gnd, other NTC terminal |
| J2 coil | 1 | COIL_SENSE, external NTC terminal |
| J2 coil | 2 | gnd, other NTC terminal |
| J3 host | 1 | +3V3 supply, modeled 3.135–3.465 V |
| J3 host | 2 | gnd, common return |
| J3 host | 3 | HS_FAULT, active-high hot OR open indication |
| J3 host | 4 | COIL_FAULT, active-high hot OR open indication |
| J3 host | 5 | HS_SENSE, raw analog monitor |
| J3 host | 6 | COIL_SENSE, raw analog monitor |

J1/J2 are JST B2B-XH-A(LF)(SN), J3 is B6B-XH-A(LF)(SN). Connector pin numbers, not camera orientation, define the interface. The two sensors are off-board Vishay NTCALUG01A104GA assemblies, 100 kΩ at 25 °C. NTC polarity does not matter; connector power/host polarity does.

The published sensor rating is −55 to 150 °C **without a connector**. JST XH is rated −25 to 85 °C including temperature rise. The PCB and XH connections must remain in the cooler electronics area, with a separately qualified extension harness to the 38.1 mm sensor leads. No assembled harness, crimp selection, installation temperature or cable strain relief has been qualified. [Vishay](https://www.vishay.com/doc/?29092), [JST XH](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf).

The analog outputs are unbuffered and approach VCC at cold/open sensor conditions. Their full range is 0..VCC, up to 3.465 V in the modeled supply envelope. They are not certified for a receiver with a lower usable ADC range. Receiver loading, acquisition, clamps and power-off behavior require integration work. The two digital outputs are push-pull SN74LVC1G32 outputs; do not wire them together. Hot and open comparator outputs feed separate OR inputs.

Hot resistance falls, sense voltage falls, and the hot comparator asserts. The open comparator asserts when sense rises above the shared approximately 0.988 VCC reference. Either sensor lead open and a short to VCC produce this rail-high condition. A short to ground asserts through the hot comparator. All feed the same channel FAULT pin, so the digital output alone does not distinguish cause.

A connected sensor is modeled from 0 °C upward. Each analog node must stay within the aggregate ±1 µA leakage/loading allowance; shared reference loading must stay within ±2 µA. These include external circuitry, not just comparator bias. Input acquisition and additional cable capacitance must be qualified before integration. The 10 ms electrical detection limit applies to the board's 100 nF filter model and excludes thermal response and downstream shutdown latency.

Reconnecting a healthy sensor clears this board's indication after settling. It does not authorize heater restart: the external interlock must latch faults and require a deliberate reset. At startup the filter can temporarily look hot. The interlock must keep heating disabled until supply and sensors are valid. Loss of board power or the whole J3 cable does not guarantee a driven-high fault; the interlock must independently reject missing power/live status.

This board is not an isolation barrier; a sensor dielectric test is not a cooker insulation qualification. Harness attachment, shorts between channels and out-of-range cold operation require system qualification.
