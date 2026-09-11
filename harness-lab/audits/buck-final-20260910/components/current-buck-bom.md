# Current BuckConverter3V3 physical BOM ledger — 2026-09-10

This is an audit ledger for the nine physical references in
`BuckConverter3V3`. It does not change the production BOM, PCB, registry, or
stock status. Ratings below are part ratings or source-declared minima as
identified; they are not effective-capacitance or hot-corner guarantees.

| Ref | Qty | Exact MPN | Manufacturer | Value / tolerance | Rating | Package / footprint |
|---|---:|---|---|---|---|---|
| U3 | 1 | LMR51430XDDCR | Texas Instruments | LMR51430 | 4.5–36 V input, 3 A output; 500 kHz PFM model in harness | SOT-23-6 |
| L2 | 1 | SRP1265A-5R6M | Bourns | 5.6 uH ±20% | 10 mOhm max DCR; 12.5 A Irms at 40 °C rise; 23 A Isat at 20% drop, specified at 25 °C | SRP1265A, 13.5 × 12.5 mm nominal; 14.0 × 12.8 mm maximum |
| C9 | 1 | CL32B106KBJZW6E | Samsung Electro-Mechanics | 10 uF ±10%, X7R | 50 Vdc; soft termination; effective C under bias remains open | 1210 / `C_1210_3225Metric` |
| C10 | 1 | C0603C104K5RACTU | KEMET | 100 nF ±10%, X7R | 50 V | 0603 / `C_0603_1608Metric` |
| C11 | 1 | GRM32ER71E226KE15L | Murata | 22 uF ±10%, X7R | 25 V | 1210 / `C_1210_3225Metric` |
| C12 | 1 | GRM32ER71E226KE15L | Murata | 22 uF ±10%, X7R | 25 V | 1210 / `C_1210_3225Metric` |
| C13 | 1 | C0603C104K5RACTU | KEMET | 100 nF ±10%, X7R | 50 V | 0603 / `C_0603_1608Metric` |
| R16 | 1 | RC0603FR-07100KL | Yageo | 100 kOhm ±1% | Source-declared resistor; no additional power/voltage claim added here | 0603 / `R_0603_1608Metric` |
| R17 | 1 | RC0603FR-0722K1L | Yageo | 22.1 kOhm ±1% | Source-declared resistor; no additional power/voltage claim added here | 0603 / `R_0603_1608Metric` |

## Verified evidence links

- [TI LMR51430 datasheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf): device limits and 500 kHz/3.3 V selection guidance.
- [Samsung CL32B106KBJZW6E product page](https://product.samsungsem.com/mlcc/CL32B106KBJZW6.do): exact C9 identity, rating, dimensions and construction.
- [Samsung assembly guidance](https://m.samsungsem.com/resources/file/global/support/product_catalog/MLCC_Automotive_2512.pdf): board-specific land review for MLCC assembly.
- [Retained Murata DC-bias data](sources/cout-bias-25-lowac.json): C11/C12 exact MPN, 25 °C, 10 mVrms trace.
- [Retained Murata temperature data](sources/cout-temperature-3v465-lowac.json): C11/C12 exact MPN, 3.465 V, 10 mVrms trace.
- [Retained Bourns SRP1265A datasheet](sources/SRP1265A.pdf): exact L2 ratings and test conditions.
- [Source declaration](../../../../elec/src/modules.ato): authoritative exact MPN/value/footprint declarations in `BuckConverter3V3`.

## Remaining measurements

1. Declare the board VIN-ripple budget, then qualify C9 at 13.5, 15 and
   16.5 V for the 0.5 A continuous and 1 A pulse profiles, including initial
   tolerance, temperature, aging, AC amplitude, ESR/ESL and measurement
   uncertainty. Typical Samsung bias data alone cannot populate the Rust
   `effective_min_uf` gate.
2. Qualify C11/C12 against the output transient/ripple procedure using the
   retained exact-part curves as starting evidence; do not treat their
   nominal or typical values as a combined lower bound.
3. Treat 8.35 A at 105 °C as the separately proposed L2 hot-saturation stress
   criterion (1.25 × the 6.68 A U3 fault-current ceiling), not an operating
   current. Test it in a standalone inductor fixture with controlled
   temperature and DC bias, measuring AC inductance versus current and
   temperature. The U3 converter must not be used to regulate above its own
   fault-current limit, and this is not a fault-survival/recovery test.
