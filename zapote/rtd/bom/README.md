# RTD BOM and specification audit

This directory records the 33 components instantiated by `rtd_pan` in the
source-02 Top build. The inventory is derived from the generated source
manifest, while the source declaration remains `elec/src/modules.ato`.
Catalog fields are taken from manufacturer product pages or manufacturer
specification sheets linked in the inventory. Distributor pages were used
only as a cross-check during the investigation and are not the authority.

The source-02 generated manifest is present and reports exactly 33
`rtd_pan.*` components. Its recorded input hash is retained in
`rtd_33_inventory.json`; the next board export must bind these instances to
the actual footprint, MPN, pad numbers, and copper connections.

One source discrepancy is actionable: `RC0603FR-0733RL` is a YAGEO 33 ohm
**1%** part. `modules.ato` currently declares ±5% for its four SPI series
resistors. The schematic declaration should be corrected or the MPN changed
before a release BOM is accepted.

The catalog MPN for `C0603C104K5RACTU` is a 50 V, ±10% X7R capacitor even
though the circuit declaration requires only a 10 V rating. That is a valid
minimum requirement, but its DC-bias capacitance must still be checked at the
actual rail. The new `C0603C102J5GACTU` is 1 nF, ±5%, 50 V, C0G in 0603.

For the RTD error budget, the critical `ERA-6AEB431V` RREF is 430 ohm,
±0.1%, ±25 ppm/°C, 0.125 W, 0805, 100 V. At a 60 °C temperature excursion,
the simple worst-case sum of tolerance and TCR is ±0.25%; around a 100 ohm
PT100 this is approximately ±0.25 ohm, or ±0.65 °C using 0.385 ohm/°C.
This is a component contribution only; ADC, reference, sensor, wiring, and
calibration terms remain to be budgeted.

The 1 MΩ diagnostic pullups (`RC0603JR-071ML`) are ±5%, ±100 ppm/°C, 0.1 W
at 70 °C, 75 V continuous, and -55..+155 °C. Their tolerance and leakage
effects belong in the open-lead detector budget rather than the normal
connected-sensor accuracy budget.

This audit does not claim board acceptance or complete the electrical fault
model. See `../../OUTSTANDING_RUST_WORK.md` for the validator work that
remains.
