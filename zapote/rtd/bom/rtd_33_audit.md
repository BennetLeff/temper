# RTD 33-component audit

The source-02 manifest contains 33 `rtd_pan` instances: 17 resistors, 8
capacitors, 6 ICs, 1 ferrite bead, and 1 connector. The machine-readable
instance-to-MPN mapping and manufacturer evidence links are in
[`rtd_33_inventory.json`](rtd_33_inventory.json).

| Group | Instances | Catalog result |
| --- | --- | --- |
| MAX31865 | `adc` | `MAX31865AAP+`, 20-pin SSOP, -40..125 °C |
| Reference | `reference` | `REF2025AIDDCR`, SOT-23-5, 2.5 V, ±0.05% max, 8 ppm/°C max |
| Comparators | `low_window`, `high_window` | `TLV3201AIDBVR`, SOT-23-5, -40..125 °C |
| Logic/monitor | `window_and`, `rail_monitor`, `fault_nand` | TI DBV/DDC SOT packages; exact ratings are recorded per MPN |
| RREF | `r_ref` | `ERA-6AEB431V`, 430 Ω, ±0.1%, ±25 ppm/°C, 0.125 W, 0805 |
| Precision threshold resistors | `r_low_top`, `r_low_bottom`, `r_high_top`, `r_high_bottom`, `r_avdd_top`, `r_avdd_bottom` | Panasonic ERA-3A/ERA-6A thin film; ±0.1%, ±25 ppm/°C; package and voltage rating per MPN |
| Diagnostic bias | `r_rtdin_p_bias`, `r_rtdin_n_bias` | YAGEO `RC0603JR-071ML`, 1 MΩ, ±5%, ±100 ppm/°C, 0.1 W, 75 V, 0603 |
| SPI/logic resistors | `r_sclk`, `r_mosi`, `r_cs`, `r_miso`, `r_window_ok_pulldown`, `r_rail_ok_pullup`, `r_fault_pullup` | YAGEO RC0603FR family, 0603, ±1%, ±100 ppm/°C, 0.1 W, 75 V |
| Input filter | `c_rtd_input` | KEMET `C0603C102J5GACTU`, 1 nF, C0G, ±5%, 50 V, -55..125 °C |
| Bypass capacitors | `c_vdd`, `c_reference`, `c_low_window`, `c_high_window`, `c_window_and`, `c_rail_monitor`, `c_fault_nand` | KEMET `C0603C104K5RACTU`, 100 nF, X7R, ±10%, 50 V catalog rating, 0603 |
| Ferrite | `fb_power` | Murata `BLM18AG121SN1D`, 120 Ω typical @100 MHz, 0.18 Ω max DCR, 800 mA, 0603 |
| Connector | `j_rtd1` | JST `B4B-XH-A(LF)(SN)`, XH, 4 circuits, 2.50 mm pitch, through-hole vertical |

## Required source correction

The four `RC0603FR-0733RL` instances are declared as `33ohm +/- 5%` in
`modules.ato`. The exact YAGEO manufacturer specification sheet identifies
that MPN as 33 ohm **±1%**. The machine-readable inventory marks this as
`source_tolerance_mismatch`; it must not be silently treated as a pass.

## Error-budget inputs

* RREF: ±0.1% initial tolerance and ±25 ppm/°C. With a 60 °C rise, use
  ±0.25% as the simple worst-case component bound before correlation or
  calibration. At 100 Ω PT100 and 0.385 Ω/°C, that is about ±0.65 °C.
* Each 1 MΩ bias resistor: ±5% and ±100 ppm/°C. At 60 °C, the simple bound
  is ±5.6%. Include ADC input leakage, cable leakage, and the actual fault
  state when converting this into a detection margin.
* The 1 nF C0G filter is ±5%, 50 V, with a listed 30 ppm/°C coefficient.
  Its nominal 1 ms RC time constant therefore has a roughly ±10.8% simple
  component bound with a 1 MΩ bias resistor at 60 °C; this affects response
  timing, not the steady-state PT100 ratio directly.

## Evidence and limits

Manufacturer URLs are retained alongside every component in the JSON. The
source-02 manifest is current for this audit, but footprint and copper
acceptance still require the matching native board export. No placement,
routing, or board acceptance conclusion is made here.
