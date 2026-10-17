# Source register

The retained `tlv3201.pdf` is TI SBOS561C, revised May 2024, SHA-256
`1777bba814c74772bb54c6f1f56702985039043ce2fb2affaf996a83eaf1076e`.
It is the exact file used to inspect §§6.5–6.9. The other manufacturer
documents were checked through their published pages; network resolution in
this worktree prevented a second local download. Their numerical uses and
locations are recorded here, rather than assigning a hash to an unfetched
copy.

| Source | Used value / section | URL |
| --- | --- | --- |
| TI TLV3201 SBOS561C, May 2024 | §6.5 input offset and bias; §6.6 20 mV, 15 pF, 55 ns maximum; §6.9 typical graph (starts at 20 mV) | [datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) |
| TI LM4040 Rev. Q, A25I table | Initial ±2.5 mV; full temperature ±19 mV; 100 ppm/°C; 80 µA cathode minimum; ≤1 mV load regulation allowance for the relevant low-current span | [datasheet](https://www.ti.com/lit/ds/symlink/lm4040.pdf) |
| Vishay WSK2512 doc. 30108, revision 11 Dec 2023 | F order code is ±1%; **1 mΩ is ±250 ppm/°C** in p. 2 table (the headline <20 ppm/°C is not the 1 mΩ grade) | [datasheet](https://www.vishay.com/docs/30108/wsk2512.pdf) |
| Yageo RT0603BRD07 product specification | 0.1%, ±25 ppm/°C for the 10 kΩ grade; same series part pattern for R30, R32–R37, R40/R41, R43–R46 | [10 kΩ specification](https://www.yageogroup.com/component-documentation/download/specsheet/RT0603BRD0710KL) |
| Yageo RC1206FR-07470KL product specification | 1%, ±100 ppm/°C for 470 kΩ | [470 kΩ specification](https://yageogroup.com/component-documentation/download/specsheet/RC1206FR-07470KL) |
| Yageo RC1206 1.5 Ω grade | 1%, ±200 ppm/°C for R39; the low-ohm grade differs from 470 kΩ | [manufacturer-authored RC1206 series data sheet](https://www.mouser.com/datasheet/2/447/YAGOS01625_1-2572852.pdf), [part listing](https://www.digikey.ca/en/products/detail/yageo/RC1206FR-071R5L/728440) |
| Nexperia BAS116H Rev. 3 | Table 7: 80 nA maximum at VR=75 V pulsed, Tj=150°C; modeled as ±80 µV at R42=1 kΩ | [datasheet](https://assets.nexperia.com/documents/data-sheet/BAS116H.pdf) |
| TI ISO7710 SLLSER9E Rev. E | §7.4/Table 7-2: input PD ≤1.7 V, PU ≥2.25 V, non-F default high; falling UVLO 1.7–1.8 V | [datasheet](https://www.ti.com/lit/ds/symlink/iso7710.pdf) |
| TI SN74LVC1G00 SCES212 | NAND truth table and 1.65–5.5 V specified supply | [datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g00.pdf) |
| TI SN74LVC1G332 SCES489E | OR truth table and 1.65–5.5 V specified supply | [datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf) |
| TI UCC21550 SLUSE89C Rev. C, Aug 2024 | §§4, 5.7, 7.4: input pulldown, DIS pullup, supply UVLO, DT both-high interlock | [datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf) |
| TI TPS3823 Rev. O | 0.9–2.5 s watchdog timeout | [datasheet](https://www.ti.com/lit/ds/symlink/tps3823.pdf) |
| AOS AO3400A | VGS(th) 0.65–1.45 V, no HOT5 supervisor | [datasheet](https://www.aosmd.com/res/data_sheets/AO3400A.pdf) |

The product BOM and net connections are retained at
`../../../frozen/default.csv` and `../../../frozen/default.net`. Part identity
must come from the CSV: the netlist's part-source fields are aliased.
