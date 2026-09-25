# Fuse-source retention

This folder records the primary-source identity used by
`../fuse-coordination.md`. The large Mersen 2024 catalogue is already
retained by the campaign packet; it is referenced by path and SHA-256 below
instead of duplicated here.

| Device | Primary source | Pages/section | SHA-256 | Retention status |
| --- | --- | --- | --- | --- |
| Schurter 0034.3129 (F1) | [FST 5x20 datasheet](https://www.schurter.com/en/datasheet/typ_FST_5x20.pdf) | PDF pp. 1, 3–4; variant row and pre-arcing table | not locally retained (web source read 2026-09-21) | web primary; no local hash claimed |
| Schurter 0031.2510 (F1 holder) | [FUP 0031.2510 product page](https://www.schurter.com/en/part/0031.2510) | Technical data and variant table | not locally retained (web source read 2026-09-21) | web primary; no local hash claimed |
| Mersen A70QS50-14F (F2) | `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/attempt-001/raw/mersen-hs-high-speed-fuses.pdf` | HS 20–21 (PDF pp. 20–21) | `e0e5b788fcc883650ff771c4fa006986fec4238293856ab200b56e2cf44e9789` | retained campaign primary PDF |
| Mersen US141/Z331153 (F2 holder) | `zapote/power-entry/passive-reva/protection/sources/Mersen-US14.pdf` and [US141 product record](https://us.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141) | retained DS pp. 1–4; exact product record | `776c47a6781b1d82d762a827d2ceed9d7e17b15439217b9fb5dc259aa9884562` | retained primary PDF + web identity |

No distributor page is used as authority for a rating. Where a source does
not publish a value (F1 total-clearing I²t, F2 capacitor-discharge clearing
I²t, or F2 MBC), the coordination record leaves it unknown.
