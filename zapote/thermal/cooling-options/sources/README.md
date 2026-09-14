# Cooling-options sources

Retrieved 2026-09-14.  These are source-bound engineering inputs and
availability snapshots, not procurement commitments or assembly guarantees.

| Record | Authority | SHA-256 / status |
|---|---|---|
| `wakefield-bonded-fin.pdf` | Wakefield Thermal Solutions, *Extruded Heat Sinks for Power*, 2021 catalog | `d7f9c8636915b10c858c0df9940547f51925ed9fe30d7a6416e192928f3d5952` |
| `../../cooling-sources/wakefield-catalog-page-74.pdf` | Wakefield 394/395/396 page retained by v1 baseline | `15ecbb307fa22c0f0cbdb7a09b1c1aa684c02d54beab113c4b5bab53a210aae7` |
| `../../cooling-sources/sunon-mf80251v1.pdf` | Sunon exact `MF80251V1-1000U-G99` datasheet | `7f959f5b7f8b3db41285325ca167ab3e6b7b23ec9b01f17b69e4a4dbd0f3eb0c` |
| `../../cooling-sources/henkel-tsp1800.pdf` | Henkel/Bergquist SIL PAD TSP 1800 datasheet | `f383628f88916adc5b1d3d1c886bef4ed730a2ec827f1d7028b195fa76059a1f` |
| `sanyo-san-ace-e.pdf` | Sanyo Denki *San Ace E* catalog, page 181/183; exact `9RA1212E1001` fan table and curve | `a9dd3971db4030adab9935759c83c4ca7d6ad785ff6692113a231ea97ab4962e` |
| `yangjie-gbu2510a.pdf` | Yangjie-authored `GBU25005A THRU GBU2510A`, S-B407 Rev. 2.5, distributor mirror | `8bae78604e65be4d011c2989bbaddd9aab32b55fbdd40a79891aa8803f997794` |

## Distributor snapshots

These are dated web snapshots and must be rechecked before ordering.  DigiKey
pages are JavaScript-rendered; stock and price can change without notice.

| Exact MPN | Distributor identity | Snapshot | Observation |
|---|---|---|---|
| `395-1AB` | DigiKey `345-1177-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/395-1AB/4899820) | 62 units, USD 37.07 in retained baseline snapshot |
| `396-1AB` | DigiKey `4899822` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-vette/396-1AB/4899822) | 53 units, USD 39.23; active |
| `395-2AB` | DigiKey `345-1178-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/395-2AB/4899821) | 59 units, USD 48.37; active |
| `392-120AB` | DigiKey `345-1173-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/392-120AB/4864907) | 160 units / USD 114.04 in one page snapshot; another DigiKey index showed 0 stock, so status is **conflicted—recheck** |
| `9RA1212E1001` | DigiKey `1688-9RA1212E1001-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/sanyo-denki-america-inc/9RA1212E1001/17867185) | 22 units / USD 44.22 in snapshot; active |
| `MF80251V1-1000U-G99` | DigiKey `259-1859-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/sunon-fans/MF80251V1-1000U-G99/7927795) | 40 units, USD 8.15 in retained US snapshot |

The Wakefield manufacturer catalog is the authority for dimensions and thermal
curves.  DigiKey attributes for `392-120AB` report 120 × 125 × 135.8 mm,
`0.50 °C/W` natural and `0.20 °C/W @100 LFM`; the manufacturer table reports
`0.16 °C/W @100 CFM`.  The comparison preserves the manufacturer value and
labels the distributor discrepancy as unresolved rather than blending them.

The Sanyo catalog table gives `9RA1212E1001` as 12 V, 7–13.8 V operating,
0.47 A, 5.6 W, 3600 rpm, 3.4 m³/min (120 CFM) maximum airflow and 100 Pa
(0.402 inH₂O) maximum static pressure, with pulse sensor and 120 × 120 × 38 mm
dimensions.  Its page-183 12 V curve is the basis for the candidate’s
low-pressure system-point guard; the 120 CFM and 100 Pa values are endpoints,
not a simultaneous operating point.

The Sanyo manufacturer product page is
<https://products.sanyodenki.com/en/sanace/dc/dc-fan/9RA1212E1001/>; the
retained catalog PDF is the byte-bound technical source for the table and curve.

The Yangjie PDF mirror is
<https://datasheet4u.com/pdf/1564764/GBU2510A.pdf>; its document metadata and
content match the manufacturer URL and revision recorded in
`yangjie-gbu2510a-web-cache.md`.  The origin endpoint was checked separately
and returned 4xx, so the mirror URL and byte hash remain part of the evidence
chain.
