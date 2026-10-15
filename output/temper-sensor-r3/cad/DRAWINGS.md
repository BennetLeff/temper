# C1 cartridge drawings: critical dimensions and tolerances

The 3-D source is `cartridge_r3.py` (build123d). STEP files:
- `C1-cartridge-assembled.step` (at rest)
- `C1-cartridge-half-section.step`
- `C1-cartridge-at-flush-0p6.step` (pan on, disc flush)

These tables give what the 2-D drawings must control. Every other dimension is ±0.05 (ISO 2768-f) taken from the STEP.

**World frame:** sensor axis at X0, Y261. Z is the R43 world Z: glass top Z110.0, glass underside Z106.0. The body's rim face, which bears on the glass underside, is **datum A**. The axis of the pad ID is **datum B**.

The two tolerance chains (G2 protrusion and stroke to the hard stop) are computed in `checks.py` `g2()`. The values that feed them are marked ★.

## Si3N4 contact disc (`disc_Si3N4`)

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| Diameter | 8.00 | −0.04 / 0 | Fits the Ø8.0 neck rim; glued edge-to-edge |
| ★ Thickness, after lapping | 0.320 | ± 0.015 | G2 chain |
| Top chamfer | 0.20 × 45° | ± 0.05 | Contact Ø7.6 (45.4 mm²) |
| Top flatness | ≤ 1 µm | | Contact model |
| Top Ra | ≤ 0.1 µm | | Contact model |
| Edge chips | ≤ 0.05 | | G6 strength |

## Post (`post_polyimide`), Vespel SP-1, one piece

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| Neck OD | 8.00 | ± 0.01; Ra ≤ 0.4 µm | Wiper interference (0.075–0.125 radial) and pad clearance (0.05 radial) |
| Neck wall | 0.25 | ± 0.02 | G4 cold leak |
| ★ Shoulder face (up-stop) to neck top | 6.270 | ± 0.015 | G2 chain. CAD shows 6.28 line-to-line: 6.27 plus the 0.01 mean glue line. |
| Inner support tube | Ø3.80 / Ø3.40 | ± 0.01 | G6: disc span over the pocket |
| Inner tube top | Coplanar with the neck top | ± 0.005 | The disc bonds to both rims |
| Shoulder | Ø10.4 × 0.8 | ± 0.02 | Up-stop face; clears the Ø9.0 stop-collar ID by 0.7 |
| Foot | Ø6.0 | ± 0.02 | |
| Nose | Sphere R1.50, centre 5.000 below the shoulder face | ± 0.02 | Stroke chain; sphere on cone |
| Lead bore | Ø1.20 | +0.03 / 0 | Fused-silica capillary OD 1.0, potted |
| Runout | Neck OD to nose sphere ≤ 0.02 | | Seat stays on axis |

## Body (`body_PI`), Vespel SP-1

The R43 exterior is kept unchanged: spigot Ø38.2, flange Ø43 Z94–97, three lugs Z86.5–89.5 with the Ø2 × 0.5 detent bump, gap key, rib, and NTC pocket Ø1.8 × 3.5 at r14.5 (+Y).

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| Rim face (datum A) | r12.2–13.0 at Z106.0 | Flatness 0.01 | Glass datum |
| Collar OD / top | Ø16.0, 3.80 above A | ± 0.02 / ± 0.03 | 1.0 radial gap to the Ø18 glass bore |
| Top relief | Ø11.0 | ± 0.05 | Keeps the neck off the body except at the pads (G_hot) |
| Guide pads, three at 90° / 210° / 330°, 0.6 wide | ID Ø8.10 at 3.00–3.50 above A | +0.02 / 0; position to B ≤ 0.01 | Pivot is 0.75 below the disc face; ≥ ±5 mrad of rocking |
| Wiper counterbore | Ø12.20, 1.00 above A down to 0.20 below A | H7 | Wiper press; stop-collar bond |
| Main bore (sump) | Ø12.20 to Z74 | ± 0.03 | G9: ≥ 2 ml sealed sump |
| O-ring gland | r9.75–12.20, floor 1.10 below A | ± 0.03 | 26.7 % squeeze on the 1.5 CS ring |
| ★ Bayonet groove | Ø13.6, Z80.0–81.0 (upper face 25.00 below A) | ± 0.01 | Stroke chain: the washer seat |
| Bayonet slots | 2 × 3.2 wide at 60° / 240°, from the bottom up to the groove | ± 0.05 | Washer lugs |
| NTC lead hole / splice entry | Ø0.8 at r14.5; Ø1.0 radial at Z77.5 | | Unchanged route |

## Stop collar (`stop_collar_PI`), Vespel SP-1

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| OD / ID / height | Ø12.2 / Ø9.0 / 1.80 | −0.02 −0.04 / ± 0.05 / ± 0.02 | Bond gap; post shoulder passes |
| ★ Bottom face position | 2.000 below A | ± 0.02 | Set by fixture while the bond cures. G2 chain: the up-stop. |

## Wiper (`wiper_FFKM`), Kalrez 6230, moulded

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| OD | 12.30 (0.10 diametral press in Ø12.20) | ± 0.03 | Static seal into the counterbore |
| Lip ID, free | 7.80 | ± 0.04 | 0.075–0.125 radial interference; friction ≤ 0.185 N even at μ 1.0 (G5) |
| Lip thickness | 0.30 | ± 0.03 | |
| Lip points | Up (toward the pan) | | Wipes liquid off the neck on the up-stroke |
| Height | 1.20 | ± 0.05 | |

## Seat cup (`seat_cup_PEEK`), PEEK 450G

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| Cone | 90° included, Ra ≤ 0.8 µm | ± 0.5° | Tangent to the R1.5 nose; contact circle r1.06 |
| ★ Cone apex to pilot face | 1.079 | ± 0.02 | Stroke chain |
| Pilot / flange | Ø7.2 / Ø9.4 | ± 0.03 | Spring ID 7.5 |
| Lead hole | Ø1.6 | ± 0.05 | |

## Spring washer and hard stop (`spring_washer_bayonet_PEEK`), PEEK 450G

| Feature | Value | Tolerance | Why |
|---|---|---|---|
| Thickness | 1.00 | −0.02 / −0.04 | Slides into the 1.0 groove |
| OD / lugs | Ø12.0 / two lugs to r6.5, 3.0 wide, at 0° / 180° | ± 0.03 | Bayonet: in through the slots, turn 60° |
| ★ Stop-tube top above the seat face | 12.60 | ± 0.02 | Hard stop at 2.2 mm of travel |
| Stop tube | Ø3.6 / Ø2.4 | ± 0.03 | Leads pass inside |

## Spring (`spring_A286`)

| Item | Value |
|---|---|
| Wire | A-286, d 0.50, aged |
| Mean diameter | D 8.0 (ID 7.5 over the cup pilot) |
| Load points | P1 1.30 ± 0.08 N at L1 15.60; P2 1.70 ± 0.08 N at 13.40 |
| Rate | ≈ 0.182 N/mm |
| Coils | ≈ 6.0 active |
| Free length | L0 ≈ 22.75 |
| Solid height | ≈ 3.5 |
| Ends | Open, unground; no end turn closed |
| Stress | τ 317 MPa at F_max vs 490 allowed (`tilt-follow.json`) |

## Strain-relief plug (`cable_strain_relief_PEEK`), PEEK 450G

The plug fills the Ø12.2 bore over Z74–75, with a Ø6.6 × 6 boss below. Its bore is Ø3.4 for the pigtail bundle, and the bundle is bonded in it. Re-check the bore against the measured M22759/12-26 bundle.

## Assembly notes that set tolerances

1. **Up-stop collar.** The stop collar is bonded with the body on a datum-A fixture, so its face sits 2.000 ± 0.02 below A. Do not machine this.
2. **Disc bond.** The disc is bonded to the post with the post shoulder on a flat. The glue line is 0.00–0.02 thick and is held by a 0.1 N weight while it cures.
3. **Leads.** Each lead runs in its own capillary bore: S+/S− in adjacent bores, F+/F− in adjacent bores. The two Kelvin joints sit 0.3 above the capillary top. Pot the foot, then the splice cup. All four splices at one height, within 0.5 mm.
4. **Glass.** Thickness 4.00 ± 0.03 within Ø40 of the bore. This is an interface change and goes on the glass RFQ.
