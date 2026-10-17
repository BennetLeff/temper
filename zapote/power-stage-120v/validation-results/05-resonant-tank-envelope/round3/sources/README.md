# A5 source record

| Source | Identity and location | SHA-256 | Use |
| --- | --- | --- | --- |
| `942C.pdf` | [CDE Type 942 catalogue](https://www.cde.com/resources/catalogs/942C.pdf), no printed revision, PDF created 2021-11-16, printed p. 3 1200 Vdc rows and p. 4 RMS-voltage curves | `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310` | Exact 942C12P22K-F / 942C12P1K-F values at 70 °C and 100 kHz; typical ESR/ESL; catalogue curve limitation. |
| `rc1206.pdf` | [Yageo RC1206 specification V.2](https://pccomponents.com/datasheets/yageo-rc.pdf), 2004-09-03, printed pp. 4–5 | `7445a468b35a28771c4ec09f3f9b8f3fa4348338fa6a52838942185e58e8c044` | 200 V maximum working, 400 V overload, 0.25 W at 70 °C for R22–R25 screen. |
| Saved board (external to this result directory) | `native-15/section.kicad_pcb` | `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155` | Net topology and part placements. |
| Frozen BOM and netlist (external) | `frozen/default.csv` and `frozen/default.net` at kit commit `44417ae1489fd00e2d652fd3b2c1582b76d17630` | See repository for immutable commit content | C5/C6, C38–C41 and R5 identities; R5 between `leg_ret` and `hv_ret`. |
| TDK part information (project source) | [`PROTOTYPE-POWER-LOOP.md`](../../../../PROTOTYPE-POWER-LOOP.md) lines 11–14 and its linked official TDK product pages | Bound by kit commit above | C5/C6 2.7 µF ±5%; C38–C41 0.1 µF ±10%. |
| `a3-thresholds.json` | Snapshot of A3 `02-protection-timing/round3/outputs/thresholds.json` from worktree `ps-r3-a3`, source revision `44417ae1489fd00e2d652fd3b2c1582b76d17630` | `ae11cac0cc3abb2f5d85bfe07a80fd7b2eaf8f4a1bc1d914ac54806610291195` | Static CT and R5 OCP current screens only; A3 dynamic timing remains separate. |

[CDE's film capacitor application guide](https://www.cde.com/resources/technical-papers/filmAPPguide.pdf) describes frequency and temperature dependence of dissipation factor generically, but does not supply an exact-part thermal resistance or a hot 34–60 kHz current limit for these two 942C parts. No value from that generic guide is used numerically. The local network could not resolve CDE to retain that additional PDF, so the committed catalogue is the only numeric CDE source for this round.
