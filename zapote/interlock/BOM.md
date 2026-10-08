# Interlock Rev A parts

Source-build-02 compiles 25 installed components in nine orderable groups. Manufacturer identities are selected; no dated distributor stock or price snapshot has been taken. Compiler CSV price fields are placeholders, not quotations.

| References | Qty | Exact MPN | Role / package |
|---|---:|---|---|
| J1, J2 | 2 | JST B8B-XH-A(LF)(SN) | 8-pin, 2.50 mm vertical XH header |
| U1, U2 | 2 | TI SN74LVC14ADR | Six Schmitt inverters, SOIC-14 |
| U3 | 1 | TI CD74HC30PWR | Eight-input NAND, TSSOP-14 |
| U4 | 1 | TI SN74LVC1G74DCUR | D flip-flop, VSSOP-8 |
| U5 | 1 | TI TPS3823-33DBVR | Supervisor/watchdog, SOT-23-5 |
| U6 | 1 | TI SN74LVC1G08DBVR | Two-input AND, SOT-23-5 |
| R1–R8, R10, R11 | 10 | Yageo RC0603FR-0710KL | 10 kΩ ±1%, 0603 |
| R9 | 1 | Yageo RC0603FR-071KL | 1 kΩ ±1% watchdog pulldown, 0603 |
| C1–C6 | 6 | KEMET C0603C104K5RACTU | 100 nF ±10%, 50 V, 0603 |

Mating housings, crimp contacts, cable, fixtures and downstream electronics are not included. Select these with an explicit harness drawing and continuity test before assembly. Both headers share a form factor; label their different functions and use a reviewed harness to prevent interchange. Supply tolerance, connector ambient limits and unpowered injection behavior require review before integration.

The 1 kΩ WDI value is deliberate. Substituting the ordinary 10 kΩ bias resistor changes the evidence for watchdog disable prevention. Exact source values and pin mappings are validator inputs, not decorative BOM text.
