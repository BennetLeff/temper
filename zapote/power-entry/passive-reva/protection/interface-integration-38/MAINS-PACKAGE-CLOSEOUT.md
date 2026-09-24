# Rev38 MOV and relay-drop resistor package closeout

Scope: the `ac_input.ato` MOV and 91 Ω relay coil series resistor package
assignments only. This is a mechanical and pad-number review, not mains
surge, thermal, creepage, or fault-current qualification.

## MOV: Littelfuse V150LA10AP

The [Littelfuse LA datasheet, p. 10, Product Dimensions](https://www.littelfuse.com/assetdocs/littelfuse-varistor-la-datasheet?assetguid=f7c547ce-c2fa-4789-86cc-ec39a5060afb)
identifies V150LA10AP as a 14 mm LA model and gives these *maximum* envelope
dimensions for V130LA–V320LA 14 mm parts: `A = 20 mm` vertical height,
`ØD = 17 mm` disc diameter across the leads, `E = 5.6 mm` thickness, and
`Øb = 0.86 mm` maximum lead diameter. Lead pitch `e = 6.5–8.5 mm` and lead
stagger `e1 = 1.5–3.5 mm`. The 20 mm dimension is vertical height; it is not
the disc width in the PCB plane.

The installed `Varistor:RV_Disc_D15.5mm_W5.2mm_P7.5mm` footprint is too
small for the maximum 17 × 5.6 mm body, and its 0.8 mm drill is smaller than
the allowed 0.86 mm lead. Rev38 therefore uses
`temper:RV_Littelfuse_V150LA10AP_D17.0mm_W5.6mm_P7.5mm`, a local two-pad
derivative of that KiCad footprint. Its two pads are `1` at `(0, 0)` and `2`
at `(7.5, 2.3)` mm; both offsets fall within Littelfuse's lead ranges. Each
pad is 2.2 mm diameter with a 1.1 mm finished hole. The fab body is
17.0 × 5.6 mm (`x = -4.75..12.25`, `y = -1.65..3.95`); the courtyard is
17.5 × 6.1 mm (`x = -5.0..12.5`, `y = -1.9..4.2`). A 20 mm vertical keepout
must be checked in the enclosure, and the failed-MOV thermal boundary needs
physical review. The footprint deliberately has no misleading generic 3D
model link.

KiCad 10 parsed and exported the local footprint to SVG. The SVG was rendered
and visually checked: two staggered through-hole pads, the body rectangle,
and the surrounding courtyard appear in the intended order. This checks
geometry and parser acceptance; it does not test insertion tolerances or
thermal separation on a routed board.

## Relay coil-drop resistor: Yageo RC2512FK-0791RL

The original `RC2512FR-0791RL` orders *paper tape* (`R` packaging code).
The [Yageo RC_L datasheet, p. 2 ordering code and p. 7 packing table](https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L)
lists RC2512 only on *embossed tape* (`K`, 7-inch reel), so the source now
names `RC2512FK-0791RL`. The same datasheet specifies 2512 body
`6.35 ± 0.10 × 3.10 ± 0.15 × 0.55 ± 0.10 mm`, two terminations,
91 Ω within the 1% resistance range, and 1 W at 70 °C for the standard
power part. [Yageo's RC2512FK product-family entry](https://www.yageogroup.com/component-documentation/download/specsheet/RC2512FK-0718RL)
confirms this code family uses the same 2512 dimensions and 1 W class;
the exact 91 Ω FK ordering code is also listed as active by
[DigiKey](https://www.digikey.com/en/products/detail/yageo/RC2512FK-0791RL/5922450).

The installed `Resistor_SMD:R_2512_6332Metric` has pads `1` and `2` at
`x = -2.9625` and `+2.9625 mm`, each 1.225 × 3.35 mm. Its 6.3 × 3.2 mm
nominal fab body and 7.66 × 3.86 mm courtyard contain the Yageo tolerance
envelope (6.45 × 3.25 mm). This is a package assignment; relay steady-state,
startup pulse, PCB copper heat spreading, and worst-case ambient remain
unqualified.

## Rebuild result

`uvx --from atopile==0.2.69 ato --non-interactive build -b ac_input -b
integrated -t netlist -t bom` completed. The generated BOM records MOV
`V150LA10AP` at `U8`/`U243` with the new local footprint and the resistor
`RC2512FK-0791RL` at `U13`/`U248` with the installed 2512 footprint.
`rustc --edition=2021 --test audit.rs` ran 119 tests, all passing. One
`TBD_REVIEW_ONLY` footprint remains in the joined netlist: the PFC F2
fuse/clip assembly; that is a separate physical-boundary decision.
