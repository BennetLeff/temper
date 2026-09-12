# Power-entry candidate BOM

| Function | MPN | Package / note |
|---|---|---|
| Bridge | GBU2510A | 1000 V / 25 A, heatsink required |
| Fuse holder/link | 0031.2510 / 0034.3129 | Schurter 5x20 holder with replaceable link |
| Common-mode choke | B82726S2163N030 | 4-pin, 16 A class |
| NTC | SL32 10015 | 10 ohm, 15 A |
| Bypass relay | RT33K012 | 12 V coil, 360 ohm; 91 ohm series dropper |
| Boost inductor | 760800301 | source-build-18 identity; thermal/core-loss verification open |
| MOSFET / SiC diode | STW65N65DM2 / C3D20065D | 650 V class; switching/thermal verification open |
| Bulk capacitors | LGX2W561MELC50 x4 | 560 uF, 450 V, 50 mm height |
| Controller | UCC28180D | SOIC-8, TI CCM PFC controller |
| Current shunt | WSL2726R0100FEA | 10 mOhm, 3 W |
| HV divider | RC1206FR-07200KL x5 + RC1206FR-0713KL | 200 kOhm series chain + 13 kOhm bottom |
| Controller passives | source-build-18 exact RC1206/RC2512 and C0805/GRM32 identities | values and identities are in resolved source export |
| Y1 / output | VY1102M31Y5UQ63V0 / 1714971 | safety capacitor; Phoenix MKDS 5/2-9,5 |
| Bleeders | RC2512FR-07150KL x2 | 150 kOhm; passive discharge is ~21 min nominal |

This is a construction candidate only. Ratings, control-loop calculations, connector assembly, thermal performance, and all native gates remain subject to verification.
