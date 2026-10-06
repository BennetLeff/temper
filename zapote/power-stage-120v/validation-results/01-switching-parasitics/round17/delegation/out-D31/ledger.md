| Stage | max ns | tag | source |
| --- | ---: | --- | --- |
| shunt front end (R5 filter, TLV3201 at 20 mV overdrive) |  | ROUND-3 | validation-results/02-protection-timing/round3 (A5); see survival.py for the current reached |
| CT front end (crossing -> comparator OR output) | 336.3 | ROUND-3 | validation-results/02-protection-timing/round3/README.md:39 (106 modelled CT rows) |
| NAND SN74LVC1G10 (HOT side, shunt path only) | 6.4 | BOUND | https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf p5, 3.3 V column, worst row |
| ISO7710 (shunt path only) | 21.0 | BOUND | https://www.ti.com/lit/ds/symlink/iso7710.pdf pp14-15, largest of the supply cases |
| OR SN74LVC1G332 | 6.2 | BOUND | https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf p5, 3.3 V column, worst row |
| harness J4.10 out + J4.9 back (2 x 2 m, 5 ns/m) | 20.0 | ALLOCATION | cable length not fixed; D-20 O01 |
| interlock SN74LVC14A (fault input) | 8.0 | BOUND | https://www.ti.com/lit/ds/symlink/sn74lvc14a.pdf p9, 3.3 V +-0.3 V, extended temperature |
| interlock CD74HC30 8-input NAND | 115.0 | BOUND* | https://www.ti.com/lit/ds/symlink/cd74hc30.pdf p6: 2 V, -40..85 C max; not specified at 3.3 V (4.5 V: 23 ns); delay decreases with VCC |
| interlock SN74LVC14A (ALL_GOOD) | 8.0 | BOUND | https://www.ti.com/lit/ds/symlink/sn74lvc14a.pdf p9 |
| interlock SN74LVC1G74 CLR -> Q (= PERMIT) | 7.9 | BOUND | https://www.ti.com/lit/ds/symlink/sn74lvc1g74.pdf p7, PRE/CLR to Q, worst 3.3 V-range column |
| Q1/Q4 AO3400A turn-off (gate Vcc -> Vth min via 100 ohm) | 181.6 | ALLOCATION | https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf p2 (Vth 0.65 V min, Rg 4.5 ohm max); gate C allocated 1000 pF (Ciss 630 pF at 15 V; low-VDS curve p4) |
| DIS node rise to VIH (1 k pull-up) | 360.8 | ALLOCATION | https://www.ti.com/lit/ds/symlink/ucc21550.pdf p9 (DIS VIH 2.3 V max); C allocated 270 pF (AO3400A Coss 75 pF at 15 V, larger near 0 V), lowest rail 3.135 V |
| UCC21550 DIS response (incl. 20 ns filter) | 80.0 | BOUND | https://www.ti.com/lit/ds/symlink/ucc21550.pdf p10, tPD_DIS_HL |
| **CT path, comparator output to DIS response complete** | **787.5** | ALLOCATION/BOUND/BOUND*/ROUND-3 | sum of the applicable rows (front end and gate discharge separate) |
| **shunt path, comparator output to DIS response complete** | **814.9** | ALLOCATION/BOUND/BOUND*/ROUND-3 | sum of the applicable rows (front end and gate discharge separate) |
| **native-20 (R8/R16 330 Ω): CT path** | **545.8** | as above | DIS rise 119.1 ns; 10.61 mA per leg from V3V3 while running |
| **native-20 (R8/R16 330 Ω): shunt path** | **573.2** | as above | DIS rise 119.1 ns; 10.61 mA per leg from V3V3 while running |
