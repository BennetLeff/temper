# D12 source register

Accessed 2026-10-02 (America/Mexico_City). Manufacturer documents govern
ratings; distributor product/pricing sections govern availability and price.
Prices are observations from retrieved pages, not reservations or quotes.

| ID | Primary source and precise location | Used for |
|---|---|---|
| TI | [UCC21550 SLUSE89C, revised August 2024](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), local `datasheets/ucc21550.pdf`: pp.3–5 pin map/limits; p.9 UVLO; p.10 DTS; p.19 startup delay; p.25 eq.1; pp.31–33 gate-drive power/bootstrap; pp.34–36 §8.2.2.9 Figs.8-2/3/4; p.38 supply range | Driver, timing, bias circuit. The brief's §8 citation refers to these application pages; power-supply recommendations are §9 in the PDF. |
| DT | [Yageo RT0603BRD0749K9L specsheet](https://yageogroup.com/component-documentation/download/specsheet/RT0603BRD0749K9L), p.1, generated 2026-06-25 | 49.9kΩ, ±0.1%, ±25ppm/°C, 0.1W at70°C, 75V max continuous, −55…155°C, 0603 |
| RC51 | [Yageo RC0603FR-0751KL specsheet](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-0751KL), p.1 | 51kΩ comparison, ±1%, ±100ppm/°C; RC49.9 comparison uses D1's same tolerance/TCR assumption, not a proposed populated part |
| ROFF | [Yageo RC1206FR-071RL specsheet](https://www.yageogroup.com/component-documentation/download/specsheet/RC1206FR-071RL), p.1, generated 2026-02-14 | 1Ω, ±1%, ±200ppm/°C, 0.25W at70°C, 200V max continuous, −55…155°C, 1206. Power also restricts operating voltage; the 200V family limit does not mean 200V across 1Ω is permissible. |
| Z | [Diodes BZT52C2V0–BZT52C51 DS18004 Rev.38-2, October 2017](https://www.diodes.com/_files/datasheets/ds18004.pdf), pp.1–2 ordering/rating/table, p.4 package | BZT52C2V0-7-F and BZT52C3V9-7-F, SOD123. The retrieved document still has this revision despite a current URL. |
| D | [Nexperia PMEG6030EP datasheet, 20 February 2023](https://assets.nexperia.com/documents/data-sheet/PMEG6030EP.pdf), pp.1–2 orderable code/polarity/limits, p.4 electrical table, p.8 footprint drawing | PMEG6030EP,115, 60V/3A, CFP5/SOD128; 3.8×2.6×1mm body; no guaranteed trr or Qrr given. |
| CG | [KEMET C0G commercial SMD datasheet](https://content.kemet.com/datasheets/KEM_C1003_C0G_SMD.pdf), p.1 operating temperature and ±30ppm/°C; [KEMET kit29](https://content.kemet.com/datasheets/CER_ENG_KIT_29.pdf), p.1 exact C0603C102J5GACTU row | 1nF ±5%, 50V, C0G, 0603, −55…125°C. No high-temperature-capacitor rating above125°C is claimed. |
| CZ | [Taiyo Yuden UMK325AB7106KM-T manufacturer specification page](https://ds.yuden.co.jp/TYCOMPAS/or/detail?pn=UMK325AB7106KM-T&u=M), Specifications section (unpaginated) | 10µF ±10%, 50V, X7R ±15%, −55…125°C, 1210; 3.2×2.5×2.5mm nominal. Its linked PDF returned404; these verified manufacturer HTML specifications are the rating source. Manufacturer status is **Non-preferred**, so production sourcing is unresolved even though stock is orderable. |
| Q | [Infineon IPW65R018CFD7 Rev.2.0, 2021-04-19](../../../../03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf) | Use repository path `zapote/power-stage-120v/validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf`, p.5 table6: 234nC typical at400V,58.2A,0→10V. This is a sizing reference, not a bound at15V. |

No
licensed MOSFET simulation library was copied into this folder. Numeric input
hashes for board/netlist/BOM/TI and the long-DT grid are in `evidence.json`.

All eight distributor URLs, their unit-price observations, price breaks and
access dates are machine-readable in [prices.csv](prices.csv). Prices use USD
cut tape at the quantity-one break because each per-board addition is four
parts, and the DT replacement needs two. No reel pricing is applied to these
small quantities. The frozen CSV's zero price cells are placeholders, not
free parts. Existing Cgs part population is three; adding four makes seven,
which still falls below the quoted quantity-ten break.
