# Exact construction BOM

| References | Quantity | Part | Value / role |
|---|---:|---|---|
| J1, J2 | 2 | JST B2B-XH-A(LF)(SN) | Two-pin external sensor connector |
| J3 | 1 | JST B6B-XH-A(LF)(SN) | Six-pin host connector |
| U1, U2 | 2 | TI TLV3201AIDBVR | SOT-23-5 comparator |
| R1 | 1 | Yageo RC0603FR-0710KL | 10kΩ ±1% |
| R2 | 1 | Yageo RC0603FR-079K09L | 9.09kΩ ±1% |
| R3, R8 | 2 | Yageo RC0603FR-0711K5L | 11.5kΩ ±1% |
| R4 | 1 | Yageo RC0603FR-0734K8L | 34.8kΩ ±1% |
| R5 | 1 | Yageo RC0603FR-073K32L | 3.32kΩ ±1% |
| R6 | 1 | Yageo RC0603FR-073K16L | 3.16kΩ ±1% |
| R7 | 1 | Yageo RC0603FR-074K42L | 4.42kΩ ±1% |
| C1–C4 | 4 | KEMET C0603C104K5RACTU | 100nF ±10%, 50V |
| Off-board sensors | 2 | Vishay NTCALUG01A104GA | 100kΩ lug NTC assembly |

17 PCB components, plus two off-board sensors. Exact source/netlist/footprint fields are in `candidate/source-manifest.json`; the external sensor identity is in `sensor-contract.json`. Mating housings, crimps, extensions and mounting hardware require the physical harness definition. No live distributor stock, pricing, substitution approval or purchase is claimed.
