# Contact-plane drawing correction — 2026-10-04

The first version of this study used the wrong sign for half the lead thickness in both package calculations. **Its positive-gap conclusion is withdrawn.** This correction changes drawing-derived evidence and guidance; it does not change or release the cold STEP.

In the Infineon side view, A1 extends from the rear plane to the lead edge **nearest** that plane. The centerline is another c/2 farther away. In the Diodes side view, P likewise terminates at the nearest lead edge, so its centerline is another R/2 farther away. Therefore:

`lead-center Y = rear-plane Y + near-edge distance + half lead thickness`

Solving for the rear plane requires subtracting both distances. The previous formulas added half the lead thickness, which would describe a far-edge dimension. The independent reviewer inspected 500 dpi crops, the parent independently confirmed both endpoints, and the cooling worker reviewed the same crops before correcting the evidence. This is an independent drawing interpretation check, not a physical measurement.

| Quantity | Corrected result, mm |
| --- | --- |
| MOS back: 4.215 − A1 − c/2 | 1.170..1.825 |
| Bridge back: 4.6 − P − R/2 | 1.300..1.800 |
| Bridge minus MOS, independent corners | −0.525..+0.630 |
| MOS back minus fixed model interface at 1.515 | −0.345..+0.310 |
| Bridge back minus fixed model interface at 2.200 | −0.900..−0.400 |

The generic MOS plane at 1.515 mm is **inside** the corrected interval. Negative signed difference means interference with the fixed ceramic interface; positive means a gap. The former claim that every real MOS would leave a 0.290..0.945 mm gap was incorrect. Its corresponding MOS interval 1.805..2.460 mm and bridge interval 2.000..2.500 mm are rejected historical results, not alternative tolerances.

The modeled bridge plane at 2.200 mm is outside the corrected 1.300..1.800 mm interval. Its signed difference is −0.900..−0.400 mm: geometric interference throughout the straight-lead assumptions used here. This is not a measured assembled interference. The current 0.685 mm bridge boss is still not established: the corrected independent bridge-minus-MOS interval does not justify that offset. These bounds assume straight leads seated with their centerlines at the saved footprint positions. Real seating height, permitted lead forming, contact finish, ceramic thickness/flatness, clamp pressure and simultaneous coplanarity remain unverified. A generic face falling inside a dimensional interval does not make four devices coplanar or validate contact resistance. Do not use clamp force to pull soldered leads into the CAD planes.

The inputs remain the exact manufacturer drawings:

- [Infineon IPW65R018CFD7 Rev2.0, page 12](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf), A1=2.20..2.60 mm, c=0.38..0.89 mm. PDF SHA-256 `c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2`.
- [Diodes GBJ2510 DS21221 Rev11-2, page 4](https://www.diodes.com/datasheet/download/GBJ2510.pdf), P=2.50..2.90 mm, R=0.60..0.80 mm. PDF SHA-256 `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02`.

Local review crops were `/private/tmp/temper-contact-review/mos-side.png` and `gbj-side.png`; they are temporary review aids, not published deliverables. The full PDFs used for independent review matched the hashes above.

[Corrected dimensions](../../../../../../zapote/power-stage-120v/prototype-closure/cooling/contact-tolerances.json) and [replay checker](../../../../../../zapote/power-stage-120v/prototype-closure/cooling/check_contact_tolerances.py) enumerate the independent dimensional corners using exact decimal arithmetic. The checker rejects each historical plus-sign interval separately. [Check receipt](../../../../../../output/temper-prototype-closure/cooling/contact-tolerance-checks.json) records those rejections, source hashes and the corrected intervals. It cannot independently recover a drawing endpoint from pixels; that part is the documented visual review above.

The underlying `build_study.py`, `interface.json`, main geometry receipt and cooling STEP remain byte-identical. Their zero-intersection result is still limited to the included generic native18 models and retained R4 solids. Native19 integration and all physical/thermal/electrical qualifications remain open.
