# Cooling-options sources

Retrieved 2026-09-14.  These are source-bound engineering inputs and
availability snapshots, not procurement commitments or assembly guarantees.

| Record | Authority | SHA-256 / status |
|---|---|---|
| `wakefield-bonded-fin.pdf` | Wakefield Thermal Solutions, *Extruded Heat Sinks for Power*, 2021 catalog | `d7f9c8636915b10c858c0df9940547f51925ed9fe30d7a6416e192928f3d5952` |
| `../../cooling-sources/wakefield-catalog-page-74.pdf` | Wakefield 394/395/396 page retained by v1 baseline | `15ecbb307fa22c0f0cbdb7a09b1c1aa684c02d54beab113c4b5bab53a210aae7` |
| `../cooling-sources/sunon-mf80251v1.pdf` | Sunon exact `MF80251V1-1000U-G99` datasheet | `7f959f5b7f8b3db41285325ca167ab3e6b7b23ec9b01f17b69e4a4dbd0f3eb0c` |
| `../cooling-sources/henkel-tsp1800.pdf` | Henkel/Bergquist SIL PAD TSP 1800 datasheet | `f383628f88916adc5b1d3d1c886bef4ed730a2ec827f1d7028b195fa76059a1f` |
| `yangjie-gbu2510a-web-cache.md` | Yangjie exact manufacturer URL, indexed primary text | record hash; PDF bytes unavailable (HTTP 403/404) |

## Distributor snapshots

These are dated web snapshots and must be rechecked before ordering.  DigiKey
pages are JavaScript-rendered; stock and price can change without notice.

| Exact MPN | Distributor identity | Snapshot | Observation |
|---|---|---|---|
| `395-1AB` | DigiKey `345-1177-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/395-1AB/4899820) | 62 units, USD 37.07 in retained baseline snapshot |
| `396-1AB` | DigiKey `4899822` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-vette/396-1AB/4899822) | 53 units, USD 39.23; active |
| `395-2AB` | DigiKey `345-1178-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/395-2AB/4899821) | 59 units, USD 48.37; active |
| `392-120AB` | DigiKey `345-1173-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/392-120AB/4864907) | 160 units / USD 114.04 in one page snapshot; another DigiKey index showed 0 stock, so status is **conflicted—recheck** |
| `MF80251V1-1000U-G99` | DigiKey `259-1859-ND` | 2026-09-14, [listing](https://www.digikey.com/en/products/detail/sunon-fans/MF80251V1-1000U-G99/7927795) | 40 units, USD 8.15 in retained US snapshot |

The Wakefield manufacturer catalog is the authority for dimensions and thermal
curves.  DigiKey attributes for `392-120AB` report 120 × 125 × 135.8 mm,
`0.50 °C/W` natural and `0.20 °C/W @100 LFM`; the manufacturer table reports
`0.16 °C/W @100 CFM`.  The comparison preserves the manufacturer value and
labels the distributor discrepancy as unresolved rather than blending them.
