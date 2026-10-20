# Strict full-chain transient corners

All 54 cases passed finite-data, complete 10µs transient, ADC headroom and true-DC operating-point checks. Every exported full OP raw file also independently passed `op_guard`. 27°C nominal vendor models; VOCM=2.048V. Each table row covers nine combinations of ±11.4/12/12.6V analog supply and 4.75/5/5.25V FDA supply. No PCB or device-process/temperature claim.

| Feedback C | Fixture C | Cases | Overshoot min–max | Last >1% error min–max after edge |
|---:|---:|---:|---:|---:|
| 0pF | 0pF | 9 | 94.201–94.248% | 321.352–322.643ns |
| 0pF | 25pF | 9 | 0.000–0.000% | 310.485–310.999ns |
| 0pF | 100pF | 9 | 0.000–0.000% | 1161.889–1162.625ns |
| 10pF | 0pF | 9 | 0.000–0.000% | 225.837–226.484ns |
| 10pF | 25pF | 9 | 0.000–0.000% | 382.214–382.388ns |
| 10pF | 100pF | 9 | 0.000–0.000% | 1217.160–1218.118ns |

The pulse is 1µA across DUT_HIGH/DUT_LOW with a 1ns edge and 5µs duration, DUT=5kΩ. A capacitive fixture smooths this current disturbance, so its lack of ringing is not evidence of phase margin by itself. The parent loop-gain matrix supplies that separate check.

## FDA common-mode step

VOCM steps 2.048→2.058V in 10ns; the normal source remains at its DC value. The step tests common-mode recovery around the operating point, not power-on sequencing. Both actual FDA input-resistor bias currents and all ADC RC loads remain connected.

| Range/load | ADC channel | CM step mV | Overshoot | Last >1% error after 10ns edge | Peak differential glitch µV |
|---|---|---:|---:|---:|---:|
| cm100r | A | 9.877890 | 45.693% | 1488.987ns | 0.291 |
| cm100r | B | 9.876420 | 45.692% | 1488.987ns | 0.142 |
| cm5k_cf10 | A | 9.876420 | 45.692% | 1489.310ns | 0.395 |
| cm5k_cf10 | B | 9.876420 | 45.692% | 1489.310ns | 0.243 |
| cm100k | A | 9.876410 | 45.693% | 1489.629ns | 0.420 |
| cm100k | B | 9.876420 | 45.692% | 1489.629ns | 0.176 |
