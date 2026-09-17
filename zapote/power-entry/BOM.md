# Power-entry candidate BOM

| Function | MPN | Package / note |
|---|---|---|
| Bridge | GBU2510A | 1000 V / 25 A, heatsink required |
| Fuse holder/link | 0031.2510 / 0034.3129 | Schurter 5x20 holder with replaceable link |
| Common-mode choke | B82726S2163N030 | 4-pin, 16 A class |
| NTC | SL32 10015 | 10 ohm, 15 A |
| Bypass relay | RT33K012 | 12 V coil, 360 ohm; 91 ohm series dropper |
| Boost inductor | 760800301 | source-build-22 identity; thermal/core-loss verification open |
| MOSFET / SiC diode | STW65N65DM2AG / C3D20065D | 650 V class; package marking `65N65DM2`; bounded switching model complete, physical qualification open |
| Bulk capacitors | LGX2W561MELC50 x4 | 560 uF, 450 V, 50 mm height |
| HF bus capacitor | B32672P6474K000 | 470 nF, 630 VDC PP film, 15 mm pitch |
| Controller | UCC28180D | SOIC-8, TI CCM PFC controller |
| Current shunt | WSL2726R0100FEA | 10 mOhm, 3 W |
| HV divider | CRCW2512200KFKEG x5 + RC1206FR-0713KL | 200 kOhm 2512 series chain, 1 W / 500 V each + 13 kOhm bottom |
| Controller passives | source-build-22 exact RC1206/RC2512 and C0805/GRM32 identities | values and identities are in resolved source export |
| Y1 / output | VY1102M31Y5UQ63V0 / 1714971 | safety capacitor; Phoenix MKDS 5/2-9,5 |
| Bleeders | RC2512FR-07150KL x2 | 150 kOhm; passive discharge is ~21 min nominal |

Exact component census is in source-build-22/build/default.csv. Native and Rust construction checks pass; the overall hardware qualification remains INDETERMINATE. Current stock, pricing, thermal performance and assembled mechanical fit have not been established for procurement.

The authored source, this BOM and the native board now carry order code
`STW65N65DM2AG`; `65N65DM2` is retained as the physical package marking. Native
and manufacturing receipts were regenerated against the current board hash.
