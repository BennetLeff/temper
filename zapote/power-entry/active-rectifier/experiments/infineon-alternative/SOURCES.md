# Primary source packet

Captured 2026-09-19. Hashes are SHA-256 of the retained PDFs in `sources/`.
Web product pages are recorded separately because their HTML is dynamic.

| Source | URL | Relevant pages / facts | SHA-256 |
| --- | --- | --- | --- |
| Infineon KIT_ACT_BRD_60R022S7 application note, V1.0 (2019-12-19) | https://www.infineon.com/assets/row/public/documents/24/42/infineon-evaluation-kit-kit-act-brd-60r022s7-applicationnotes-en.pdf | pp. 1, 3: 85--265 Vac, 12 V bias, 22 mΩ IPT60R022S7, 2EDF7275F, IR11688S; p. 3: about 1200 W low line / 2400 W high line; pp. 5--9: five-pin daughterboard, 200 V IR11688S sense limit and T1/T2 extension, VDS control; p. 15: passive bridge retained for surge; p. 17: schematic; p. 19: BOM; p. 10: 35 × 6 × 30.5 mm and 40 °C ambient test envelope | `f6d559251aa4b3c32734dc6aafa910947746c04b617daa45d275db1bd7337350` |
| TI UCC21530 datasheet, Rev. D (SLUSDC0D, revised 2024-11) | https://www.ti.com/lit/ds/symlink/ucc21530.pdf | pp. 1--3: 4 A/6 A, 3.3 mm channel spacing, 5.7 kVrms reinforced input isolation, 1850 V output-to-output, pins and supplies; pp. 4--6: 8/12 V UVLO variants, >8 mm package clearance/creepage, 1500 Vrms working isolation, 8000 Vpk transient; pp. 33--35: two-layer layout example, no copper under barrier, maximize high-side/low-side spacing; p. 38: UCC21530DWKR Active production orderable | `84da68758e2e65b1a3ef667211aeef2740090e10e7aeba8b5e22a7c082b10c27` |
| Infineon 2EDF7275F product page | https://www.infineon.com/part/2EDF7275F | Retrieved 2026-09-19: 2-channel, 4 A source / 8 A sink, functional isolation, 650 V; product status **not for new design**. This is why it is not selected for a new construction. | Dynamic page; use URL and retrieval date |
| Infineon 2EDS8265H product page | https://www.infineon.com/part/2EDS8265H | Retrieved 2026-09-19: reinforced isolation, 4 A source / 8 A sink, 650 V, WB-DSO-16; product status **not for new design**. It is not a current alternative. | Dynamic page; use URL and retrieval date |
| TI UCC21530 product page | https://www.ti.com/product/UCC21530 | Retrieved 2026-09-19: product status ACTIVE; DWK option, 4 A/6 A, reinforced isolation and 3.3 mm channel spacing. | Dynamic page; use URL and retrieval date |
| Maintained project operating screen | `zapote/power-entry/loss-budget/RESULTS.md`, `zapote/power-entry/active-rectifier/README.md` | 120 Vac nominal, 108--132 Vac, 15 A true-RMS ceiling, 1796.4 W ideal input at 120 Vac; current board uses four IPW60R017C7 and UCC28180D | Repository bytes in the input snapshot |

The Infineon reference and TI datasheet are manufacturer documents. Their
ratings are not transferred as a product-compliance conclusion: the board
layout, appliance standard, surge contract, cooling, and fault protection still
need their own evidence.
