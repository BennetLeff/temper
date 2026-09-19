# Source packet

| Item | Primary source | Relevant location | Retained hash / state |
|---|---|---|---|
| Reference active bridge | [Infineon KIT-ACT-BRD-60R022S7 application note](https://www.infineon.com/assets/row/public/documents/24/42/infineon-evaluation-kit-kit-act-brd-60r022s7-applicationnotes-en.pdf) | pp. 5–9 control topology; p. 17 schematic; p. 19 BOM | `sources/infineon-kit-act-brd.pdf`, SHA256 `f6d559251aa4b3c32734dc6aafa910947746c04b617daa45d275db1bd7337350` |
| High-side driver | [TI UCC21530-Q1 datasheet](https://www.ti.com/lit/ds/symlink/ucc21530-q1.pdf) | pin/package and BQ UVLO variant; current orderable `UCC21530BQDWKRQ1` | `sources/ti-ucc21530-q1.pdf` SHA256 `5df004147881b4d750a78f5bae8fc75df3ece35da513e53487f15f61601638dc`; BQ UVLO turn-on max 8.9 V, turn-off max 8.4 V, recommended minimum 9.2 V (p.7) |
| MOSFET | Infineon IPW60R017C7 datasheet | prior AR-ACTIVE retained packet | `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-ACTIVE/attempt-001/raw/Infineon-IPW60R017C7.pdf`, SHA256 `2c5a60a28231e7d2457e59b1329740a4711d88815611a0d9c4bdac40c7f9b617` |
| Passive bridge | Diodes GBJ2510 data | prior bridge redesign source packet | `zapote/power-entry/loss-budget/sources/Diodes-GBJ2510.pdf`, SHA256 `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02` |
| Auxiliary module | Mean Well IRM-10-SPEC | 85–305 Vac input, 15 V output, ±2.5% tolerance, 200 mVpp ripple; standard package mapping is 1=AC/N, 2=AC/L, 3=-Vout, 4=+Vout | `harness-lab/audits/buck-final-20260910/margin-resolution/IRM-10-SPEC.PDF`, SHA256 `1aab6b30492328818e4d0900416676891eeb1076f409d56dc2277d7119ed208a` |
| Bootstrap bulk (selected) | Panasonic FC-A radial datasheet | 100 uF/25 V EEU-FC1E101: ø6.3x11.2 mm P2.5, ±20%, 290 mA ripple, 0.35 ohm, leakage ≤0.01CV, 1000 h @105 °C (ø6.3 class), -55…+105 °C | `sources/panasonic-fc-a-series.pdf`, SHA256 `31d50abf415e2782654b0a9e9e8cf10aa30a666961dc1d2fcb60ac0ccde42206` |
| Bootstrap resistor (selected) | Panasonic ERJ PA/P series datasheet (via RS Online) | ERJ-P08J221V (1206): 220 ohm ±5%, TCR ±200 ppm, 0.66 W @70 °C, limiting 500 V, overload 2xRCWV/5 s, AEC-Q200, -55…+155 °C | `sources/panasonic-erj-p-series.pdf`, SHA256 `3bb6b21a42f2f946a4581abcb453747ffabbf56bad31f0d9a6a9ac4c53ab4ebf` |

IR11688S and BSP300 are identified from the Infineon reference design and
remain source-capture tasks before release. This directory does not treat a
reference schematic as a substitute for each exact part's datasheet or SOA.
