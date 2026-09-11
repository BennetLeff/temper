# CST3015 footprint review

Reviewed read-only against Coilcraft CST3015 datasheet, `cst3015.pdf`,
page 2, and the supplied official land-pattern crop
`official-land-pattern.png`. Reviewed footprint:
`pcb/libs/temper.pretty/CST3015_Datasheet2025.kicad_mod`.

The four copper lands match the datasheet recommended land pattern:

| Check | Datasheet | Footprint | Result |
| --- | ---: | ---: | --- |
| Primary land size | 4.8 x 9.0 mm | 4.8 x 9.0 mm | pass |
| Primary inner gap | 6.36 mm | 6.36 mm | pass |
| Secondary land size | 3.0 x 4.6 mm | 3.0 x 4.6 mm | pass |
| Secondary inner gap | 10.76 mm | 10.76 mm | pass |
| Primary lower edge to secondary upper edge | 18.5 mm | 18.5 mm | pass |

The root-authored centers are consistent with those dimensions. The primary
centers at x = +/-5.58 mm produce `(4.8 + 6.36) / 2 = 5.58`; the secondary
centers at x = +/-6.88 mm produce `(3.0 + 10.76) / 2 = 6.88`. With primary
y = -11.55 mm and secondary y = 13.75 mm, the row-center delta is 25.30 mm
and the edge gap is `25.30 - 4.50 - 2.30 = 18.50 mm`.

Pin orientation also matches the datasheet top view: pad 1 is upper-right,
pad 2 upper-left, pad 3 lower-left, and pad 4 lower-right. The footprint pin-1
marker is at the upper-right. The 23 x 30 mm body envelope and 15.2 mm
maximum-height statement are recorded in the footprint description; the
footprint has no 3D model, which is optional and does not block this geometry
review.

Independent review result: no geometry or pin-view error found. This is a
visual/document comparison only; no board placement, routing, isolation or
physical clearance claim is made here.
