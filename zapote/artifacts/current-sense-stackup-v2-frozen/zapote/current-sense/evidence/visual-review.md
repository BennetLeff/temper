# Native board visual review

Reviewed the native front copper / silkscreen and back copper / fabrication exports and the official transformer land-pattern drawing on 2026-09-11. The board is 80 × 83 mm, with the primary solder lands and wide tracks at the top, the transformer spanning the domain gap, and the low-voltage circuit and host connector below. Copper pours begin at y = 40 mm on both layers. Primary and host pin labels match the source interfaces.

The transformer footprint is checked against the official Coilcraft drawing in `footprint-review/`. Its primary pads are 4.8 × 9 mm, secondary pads 3 × 4.6 mm, and the 18.5 mm dimension is the edge gap between the rows. The legacy shared footprint is not used. The nominal transformer body outline is present; no accurate 3D model is available, so this review does not establish 3D interference clearance or assembly fit.

The low-voltage components are deliberately clustered around the transformer secondary and comparators. Decouplers have short supply connections and dedicated ground vias. No mounting holes are included; fixture support must use the edges or a separately reviewed carrier. The primary bare lands need a qualified wire/busbar assembly design before powered use.

Native DRC provides a separate check of copper, silkscreen and courtyard geometry. Rust geometry results are recorded separately; visual inspection is not a substitute for either validator.

The final flat source-derived schematic PDF was also rendered and inspected. All 21 symbols and their net labels fit the sheet. It is a connectivity sheet using generated generic symbols, not a hand-composed functional drawing. Its inherited template footer date/build hint is not release provenance; the acceptance manifest and VALIDATION.md govern identity and replay.
