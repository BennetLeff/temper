# REF25 bias after adding bus over-voltage protection

The second comparator added a third DC load to the LM4040A25IDBZR 2.5 V
reference. The original 6.8 kΩ bias resistor supplied enough current at
nominal 5 V, but did not guarantee regulation at the allowed supply and
component corners. The source now selects Yageo RC0603FR-075K6L, 5.6 kΩ
±1%, in the same 0603 footprint.

At the limiting DC corner, HOT5 is 4.75 V, REF25 is 2.520 V, the bias
resistor is 1% high, and the three 0.1% load resistor strings are 0.1% low.
REF25 includes TI's 2.519 V full-temperature maximum at 100 µA plus a
conservative 1 mV allowance for cathode-current variation.
The OCP Kelvin node is taken at −0.15 V relative to LEG_RET. This corresponds
to 150 A through the 1 mΩ shunt and covers the nominal trip spread for the
*reference load calculation*. It does not qualify the shunt, fault current,
comparator delay or complete shutdown path at 150 A.

| Branch from REF25 | Worst-case current |
| --- | ---: |
| 10 kΩ + 10 kΩ to OCP_KELVIN_N | (2.520 + 0.15) / (20 kΩ × 0.999) = 133.6 µA |
| 10.5 kΩ + 10 kΩ OCP threshold | 2.520 / (20.5 kΩ × 0.999) = 123.0 µA |
| 10 kΩ + 140 kΩ OVP threshold | 2.520 / (150 kΩ × 0.999) = 16.8 µA |
| **Total load** | **273.5 µA** |

With 5.6 kΩ, the minimum bias feed is
`(4.75 − 2.520) / (5.6 kΩ × 1.01) = 394.3 µA`. The LM4040 receives
**120.8 µA**, above its **80 µA full-temperature minimum**. With the old
6.8 kΩ selection it receives **51.2 µA** and fails that limit. The Rust
audit pins each resistor MPN and REF25 endpoint, rejects extra direct loads,
checks this corner, and has a mutation test for the old selection.

This calculation uses the [onsemi MC78L05AC regulator's 4.75 V minimum](https://www.onsemi.com/pdf/datasheet/mc78l00a-d.pdf),
the [TI LM4040A25I voltage and cathode-current limits](https://www.ti.com/lit/ds/symlink/lm4040.pdf),
and the [Yageo 5.6 kΩ ±1% part specification](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-075K6L).
The LM4040A25I is specified from −40 to 85 °C; the selected MC78L05AC is
specified from 0 to 125 °C. The common guaranteed range is therefore
**0 to 85 °C at these components**. Board temperature and dynamic fault
response still require hardware qualification.
