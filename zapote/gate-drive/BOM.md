# Gate-drive BOM

The source09 export is the BOM authority. Exact orderable parts and native
footprints are retained in `source-build-09/build/default.csv` and the final
native extraction. Key power and timing parts are:

| Ref | Exact MPN | Native footprint |
|---|---|---|
| U1 | UCC21550BDWKR | `SOIC16W_Isolated` |
| D1 | UF4007-E3/54 | `Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal` |
| R4 | RC0603FR-0739KL, 39 kΩ ±1% | `Resistor_SMD:R_0603_1608Metric` |
| C3,C4 | GRM32ER71H106KA12L | `Capacitor_SMD:C_1210_3225Metric` |
| R5,R7 | RC1206FR-073R9L, 3.9 Ω | `Resistor_SMD:R_1206_3216Metric` |
| R6,R8 | RC0603FR-072K2L, 2.2 kΩ | `Resistor_SMD:R_0603_1608Metric` |

D1 is a 1000 V, 1 A axial diode used for the bootstrap path. U1's rendered
16-lead model is approximate: the DWK package physically omits pins 12 and
13, so the model must not be used for mechanical qualification.
