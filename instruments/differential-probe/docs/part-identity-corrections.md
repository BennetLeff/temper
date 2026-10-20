# Rev B orderable-part corrections — 2026-10-20

The JLC quote exposed three incomplete or unsupported manufacturer/order-code pairs. These corrections are made in `tools/build.rs`, then propagated through the schematic and generated BOM. They do not authorize vendor substitutions or change the divider specification.

| References | Selected order code | JLC ID | Reason |
|---|---|---|---|
| R12, R32 | Yageo RT0805BRD07220RL | C865304 | The old code omitted the resistance-unit R. The RT ordering table uses XXXR for 100–976 ohms. This remains 220 ohms, 0.1%, 25 ppm/°C, 0805, 125 mW. |
| D4–D7 | Diodes Incorporated B140-13-F | C15759 | Replaces the unverified SS14/Diodes Incorporated combination with a documented 40 V, 1 A Schottky in SMA. |
| D8 | Diodes Incorporated 1N4148W-7-F | C83528 | Replaces the unverified 1N4148W,115/Nexperia combination with a documented SOD-123 switching diode. |

## Electrical and footprint checks

D4/D5 provide series battery-polarity protection; D6/D7 clamp reverse rail excursions. B140 has 40 V blocking rating, 1 A average current at the datasheet terminal-temperature condition, and maximum 0.5 V forward drop at 1 A/25°C. The normal 9 V battery and approximately 60–80 mA per-rail load are within that selection envelope. The 30 A surge rating applies only to the specified 8.3 ms half-sine, not arbitrary faults. Its leakage allowance is acceptable on supply rails; it is not a substitute for the low-leakage input clamps. Keep the existing supply sequencing, reverse-polarity and thermal bench checks.

B140-13-F explicitly selects SMA, not the B140B SMB variant. The existing KiCad D_SMA pads have 4.0 mm center spacing, 2.5 × 1.8 mm size and 1.5 mm inner gap; the manufacturer recommends 4.0 mm centers, 2.5 × 1.7 mm pads and 1.5 mm gap. Cathode band/notch maps to footprint pad 1 and schematic K; pad 2 is A. No placement or route change is required.

D8 has 100 V reverse rating, 300 mA continuous-forward rating and 4 ns maximum reverse recovery under the datasheet test conditions. Its normal reverse bias is the 9.6 V rail span. The reset pull-down is 100 kohms (96 µA at that span), and C95 is 100 nF; its maximum nominal stored energy at 9.6 V is 4.61 µJ. That energy does not bound peak discharge current, so retain the power-down/reset transient bench check. D8 is not an HV safety barrier.

The 1N4148W-7-F ordering table specifies SOD-123 and a cathode band. Existing D_SOD-123 pads are 0.9 × 1.2 mm with 3.3 mm center spacing, compared with the recommended 0.9 × 0.95 mm pads at 3.15 mm center spacing. The lead-span range is 3.55–3.85 mm and both lands overlap the terminal envelope. Pad 1 remains K/RESET; pad 2 remains A/−4V8. Vendor placement polarity still requires review.

## Evidence

- [Yageo RT ordering table, page 2](https://www.yageogroup.com/content/datasheet/asset/file/PYU-RT_1-TO-0-01_ROHS_L), local `sources/Yageo-RT.pdf` and `.txt`.
- [B140 DS13002 Rev.20-2](https://www.diodes.com/datasheet/download/B140.pdf), local `sources/B140.pdf` and `.txt`; ordering and polarity page 1, ratings page 2, SMA land pattern page 5.
- [1N4148W DS30086 Rev.31-2](https://www.diodes.com/datasheet/download/1N4148W.pdf), local `sources/1N4148W.pdf` and `.txt`; ordering and polarity page 1, ratings page 2, package/land pattern page 4.

Live JLC stock lookup on 2026-10-20 returned 24,592 of C865304, 35,302 of C15759 and 242,015 of C83528. These are availability observations, not reservations. Bench qualification remains unperformed.
