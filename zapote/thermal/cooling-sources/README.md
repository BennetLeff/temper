# Cooling source records

Retrieved 2026-09-14. These are manufacturer-authored references, not measured
assembly performance. No purchase was made.

| Retained file | Original source | SHA-256 |
|---|---|---|
| `wakefield-catalog-page-74.pdf` | [Wakefield extrusion guide](https://wakefieldthermal.com/content/data_sheets/2021_data_sheets/Wakefield-Thermal-Extrusion-Profile-Guide.pdf), PDF page 74 / printed pages 92–93 | `15ecbb307fa22c0f0cbdb7a09b1c1aa684c02d54beab113c4b5bab53a210aae7` |
| `sunon-mf80251v1.pdf` | [Sunon exact fan specification](https://www.sunonusa.com/wp-content/uploads/2026/02/MF80251V1-1000U-G99-D08062730G-01-1.pdf) | `7f959f5b7f8b3db41285325ca167ab3e6b7b23ec9b01f17b69e4a4dbd0f3eb0c` |
| `henkel-tsp1800.pdf` | [Henkel SIL PAD TSP 1800](https://datasheets.tdx.henkel.com/BERGQUIST-SIL-PAD-TSP-1800-en_GL.pdf) | `f383628f88916adc5b1d3d1c886bef4ed730a2ec827f1d7028b195fa76059a1f` |

The Wakefield page was extracted with Poppler `pdfseparate -f 74 -l 74`.
The complete original PDF hash was
`3656feeffb4df35a55a32338a3004d03d30813caddf680360c0402ec91c0d40b`.
Its drawing and the fan performance curve were visually inspected.

The [DigiKey 395-1AB listing](https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/395-1AB/4899820)
returned 62 units and USD 37.07 each in the retrieval snapshot; the
[fan listing](https://www.digikey.com/en/products/detail/sunon-fans/MF80251V1-1000U-G99/7927795)
returned 40 units and USD 8.15 each in the US retrieval snapshot. Both
must be rechecked by exact manufacturer number before ordering. Distributor
stock and price are not retained as guaranteed procurement quantities.

The exact bridge reference remains
[Yangjie GBU25005A through GBU2510A](https://www.21yangjie.com/pdf/zlqj/zhengliuqiao/GBU25005A%20THRU%20GBU2510A.pdf).
The non-A family sheet is not a substitute for this part. Direct retrieval of
the A-family PDF was unavailable during this session; its referenced thermal
value is not promoted to an installed assembly guarantee.
