# Electrical model and applicability

The Rust model is algebraic KCL for the exact resistor networks. It is not a manufacturer transistor-level SPICE model. Its input is the compiled source manifest, including values/tolerances, rather than a detached set of nominal constants. The independent Luna review recomputed the same circuit from KCL; pinned numerical expectations are exercised by the voltage tests.

| Quantity | Conditional result |
|---|---|
| ADC at 170 V / 200 V | 1.8681 V / 2.1978 V nominal |
| ADC at 250 V | 2.7473 V nominal; 2.6617–2.8356 V modeled corners |
| Ideal rising OVP | 196.126–203.824 V |
| Ideal external hysteresis | 8.151–9.349 V, including ±5% host supply |
| Filter | 100 nF nominal, approximately 0.989 ms small-signal time constant |

For OVP, with top-series resistance Rt, bottom Rb and positive-feedback Rh:
`Vbus = Vref × (1 + Rt/Rb + Rt/Rh) − Vout × Rt/Rh`.
The rising ideal threshold assumes Vout=0. Same-device external hysteresis is
`(VOH−VOL) × Rt/Rh`; the ideal calculation uses VOH=VCC, VOL=0.
Do not subtract thresholds from different component corners to derive hysteresis.

Modeled conditions: absolute temperature displacement from 25 °C ≤60 °C; 1%/100 ppm/K RC-family resistors, 0.1%/25 ppm/K RT-family bottom/feedback resistors; REF2025 initial ±0.05% and 8 ppm/K; VCC 3.3 V ±5%. Tolerance and temperature extrema are conservatively combined. Top resistors are checked at 250 V for normal operation and each single top-resistor short, below 200 V and 50% of 0.25 W. These checks do not cover bottom-resistor opens, contamination, arcing or transient pulse energy.

A separate sensitivity scenario explores ±5 mV effective comparator offset and VOL=0–0.4 V. It is explicitly INDETERMINATE: it does not bound TLV3201's internal hysteresis or establish applicability of every tabulated limit at this circuit's supply/common mode. At 250 V, the OVP input approaches the upper common-mode boundary, so startup, supply sag and transient envelope matter. The assumed 250 V maximum must be justified by the integrated power circuit.

The old 3×169 kΩ ADC divider would produce about 4.84 V at 250 V and is retained as a rejecting test. The intermediate suggestion of 3×270 kΩ would reach 3.049 V nominal, leaving inadequate corner margin to the chosen 3.1 V receiver ceiling; 3×300 kΩ was selected instead.

Official evidence consulted:

- [TI TLV3201 datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf): OUT1/GND2/IN+3/IN−4/VCC5, supply/common-mode ranges, offset/output conditions and typical-only internal hysteresis.
- [TI REF2025 datasheet](https://www.ti.com/lit/gpn/ref2025): VBIAS1/GND2/EN3/VIN4/VREF5, reference accuracy/drift and output-capacitance stability. VBIAS is intentionally unused; EN is tied to VIN.
- [Espressif ESP32-S3 ADC guidance](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/adc/index.html): receiver range depends on attenuation and calibration. This unit uses 3.1 V as a design ceiling, not an accuracy guarantee.

Physical accuracy, ADC acquisition/loading, effective capacitance, hot leakage, comparator internal hysteresis, output loading, brownout/power-off, surge behavior, assembled insulation and complete shutdown timing remain unqualified. No physical measurement was performed.
