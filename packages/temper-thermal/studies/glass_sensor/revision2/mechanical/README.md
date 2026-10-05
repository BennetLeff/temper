# PR2 mechanical revision — dry instrumented prototype

This revision replaces the heavy skirt with a positively captured8mm metal face, separates cap-local motion from the main guide and seal, and selects a 250°C-capable seal compound. It is **simulation and test preparation**. No supplier has accepted the custom drawings and no hardware has been built. The dry fixture has open witness/lead passages; **it is not a spill-sealed product**.

## Build and inspect

```sh
/private/tmp/temper-center-sensor-env/bin/python build.py
```

CadQuery2.6.1 writes five full assemblySTEP states, a sectionSTEP/SVG, and `geometry.json`. All rigid components are checked pairwise, solids are checked valid, STEP is reimported, and the script fails if any rigid overlap exceeds1e−5mm³. Flexible membranes, glass, wires and witness routes are labeled envelopes and excluded from those rigid checks. Geometry is in millimetres; z0 is glass top. This is a new instrumented upper cartridge, not a drop-in production replacement. Lower spring/module installation is an external fixture interface at the main stem; PR1 spring force must be remeasured with this heavier assembly and new membrane.

| State | Main-carrier depression | Local-island depression | Purpose |
|---|---:|---:|---|
| rest |0|0|Free cap top+0.6mm|
| loaded |0.45mm|0.15mm|Cap flush with nominal glass|
| local stop |0|0.25mm|Overload pads just contact; maximum M222 body|
| full stroke |1.2mm|0.25mm|Combined lower-travel envelope|
| upper capture |0|−0.10mm|Island upward fingers just contact|

A bare 0.15mm316L disc is positively retained by three discrete0.8mm-wide,0.15mm-thick formed hooks attached beneath its edge. The hooks end below three ceramic retention arms with0.05mm lift clearance. Welded tab geometry is a manufacturing candidate: welding distortion, peel strength and fatigue need coupon validation. Cap-to-RTD adhesive never retains the cap. Three separate hooks avoid a closed metal skirt/retaining ring; they do not make the disc immune to induction heating. Exact complete cap volume, including hooks, is in `geometry.json`.

## Thermal isolation with a buildable load path

The recommended candidate uses three Morgan CIM Zirconia posts,Ø0.30×2.00mm, on a six-arm zirconia spider. The spider has aØ3.2/bore2.2mm central hub, three 0.6mm-wide load arms, three 0.8mm-wide retention arms,2.3mm arm length and0.7mm thickness. This reduces projected hot-face-to-support area relative to a full disc. The posts support the cap at r3.1mm,60/180/300°; hook arms sit at0/120/240°. Normal force goes through the posts, not through a full ceramic contact face. Hook toes should remain clear in compression.

The complete ceramic island also includes a hollow stalk, an inner flexure platform and clamps. **Model its full volume, not only the top spider.** `geometry.json` exports exact volumes for the recommended spider, long-post solid-puck comparison, and initial short-post alumina comparison. The parent thermal model includes support capacitance, post conduction, gas across the gap and radiation; a post-only conductance would overstate improvement. Wetting/contamination of the open cavity could dominate all those dry paths.

[Manufacturer Morgan CIM Zirconia data](https://www.morganthermalceramics.com/media/00td54fl/cim-zirconia.pdf):k2.9W/mK at20°C, density>6g/cm³,cp610J/kgK,elastic modulus220GPa at20°C,CTE9×10⁻⁶/K over20–1000°C. These are indicative coupon values. A custom0.3mm post drawing requires a manufacturing response and flaw/side-load testing. Quote monolithic micro-machined or molded pieces with finish-ground contact tips; do not glue three unsupported needles into place and assume equivalent strength. Root fillets and final post tolerances must be agreed before hardware release.

A250µm alumina/AlN8mm head remains a thermal/induction comparison in sibling simulations. It is not mechanically retained by these metal-welded hooks, so this CAD does not claim a buildable ceramic cap substitution.

## Cap-local force path and jam cases

Three electrically separate INCONELX750 flat blades support the ceramic island. Each free span is7×2.1×0.08mm, with0.5mm inner and0.6mm outer clamp pads. End pads are actual CAD solids rather than unsupported beam endpoints. The free span must not rub the main carrier: three clearance windows are cut through its upper rim. Local normal motion0–0.20mm is followed by a0.25mm compression stop; independent fingers capture0.10mm upward motion. Parent/contact Rust screening supplies stiffness/stress calculations; the CAD spline is only a deformation visualization.

[Special Metals X750 bulletin](https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-x-750.pdf) distinguishes strip temper and heat treatments and bases its flat-spring stress guidance on5% relaxation in7days. [Elgiloy X750 strip/foil](https://www.elgiloy.com/strip-inconel-alloy-x750) is a material procurement route. No tested foil lot, heat treatment, etched edge quality or fatigue allowable has been selected. Clamps need a bolted or otherwise positively fixed process with known free length; the geometry's ceramic clamp blocks are contact-location fixtures, not a claim of an already manufactured joint.

The outer guide and rolling membrane act on the **main carrier**. The cap/inner island motion is measured relative to it, so a jammed main plunger does not automatically preserve the local contact signal. However, debris bridging the cap/island to the carrier, a seized local island, bent hooks rubbing the surrounding rim, liquid adhesion, wire drag or a trapped fragment can still mimic contact or prevent return. A frozen loaded island is statically indistinguishable from a loaded pan. Do not call this design jam-proof or a safety-qualified contact detector. Dynamic proof/release checks and independent product safety protections remain required.

TwoØ0.4mm witness rods are reserved at x±0.8mm. Their2×2mm ceramic flags lie at different elevations below the stem to avoid overlapping. Contact team's two external displacement heads compare the flag positions in the cold dry fixture. Rods are envelopes: unsupported length, thermal expansion, tilt, bending, mounting and optical range require measured characterization. They must not pass through sliding seals whose friction would enter the sensing load path.

## 250°C seal selection and remaining liquid barrier

Choose **DuPont Kalrez Spectrum6375** for both custom membrane and static face-gasket RFQs. [Primary datasheet](https://www.dupont.com/content/dam/dupont/amer/us/en/kalrez/public/documents/en/KZE-H82112-00-F0719_Kalrez_Spectrum_6375.pdf) gives275°C maximum service,75ShoreA, and typical24–25% compression set after70h at204°C. Those data establish a material candidate above250°C; they do not establish membrane force, hot lifetime, sealing performance or food-contact status. Do not use100% tensile modulus as a small-deflection membrane spring constant.

The dynamic CAD envelope is a0.3mm custom convolution between the main-carrier lip(r5.4mm) and fixed body(r8.5mm). Its1.2mm carrier stroke and force budget require supplier analysis and hot-cycle measurement. Inner lip attaches to the carrier, not the sensing island. The static glass interface is now a **custom axial face gasket**,ID18.6/OD24mm,1.0mm free thickness with0.7mm installed target under the glass. A stock1.78mm cross-section O-ring cannot simply fit the original0.5mm radial gap. The30% axial compression target is a prototype process proposal, not a validated6375 gland specification. Glass stress, clamp load, extrusion space, compression set, cleaning fluids and thermal growth must be validated.

[Kalrez7075](https://www.dupont.com/content/dam/dupont/amer/us/en/kalrez/public/documents/en/KZE-H90161-00-H0719_Kalrez_Spectrum_7075.pdf) offers327°C and lower coupon compression set, but its manufacturer discourages severe aqueous/amine applications and prefers6375 there. The wet cooking/cleaning duty makes6375 the starting candidate; final chemistry and food-contact evidence remain open. Standard-ring dimensions are not proof of custom-compound shrinkage tolerances.

**The current witness and wire passages leave the cartridge open.** The membrane and gasket do not remedy that. The concrete next sealed concept is an extended housing containing the entire island/rod/flag cavity, with a static side optical window near cold flags and a hermetic RTD feedthrough. No rod sliding seal. This still admits liquid into the island cavity from the top unless a secondary flexible island-to-carrier barrier is added or the wet cavity is separately detected and heating inhibited. A secondary barrier introduces cap-local stiffness/hysteresis; contact team proposes≤10mN measured parasitic return force and total measured island stiffness1.6–2.4N/mm. Neither limit has been demonstrated. Window reflection, refraction, fogging and alignment need recalibration; the narrow hollow stem is not a validated laser viewport. Hermetic feedthrough and window assemblies are a new custom sealed revision, not included physical parts in these STEPs.

## Bond and lead interface

M22232208550 remains the selected RTD. Its2.3×2.1×0.9mm nominal body fits beneath the0.15mm roof and0.10mm bond. The maximum2.5×2.3×1.2mm body with0.15mm bond bottoms at−0.90mm, well above the optimized spider's−1.55mm top. The central2.2mm island bore and2.8mm main-stem bore reserve wiring and separate witness rods. Four-wire bundle envelopeØ0.9mm is offset to y0.6mm in the lower bore; it is **not a verified formed harness**.

Use the sibling `bond_leads/` specification for two protected Kelvin weld regions,0.30mm individual wire envelopes, an external8×12mm slack pocket and≥2mm proposed bend radius. The factory nickel element leads should be strain-relieved on the island; only the selected flexible copper leads cross its motion. No solder or polymer is silently assigned250°C service. A lead-joint ceramic cover, exact four-wire S-loop and clamp screws are not yet fully modeled; their mass/force/heat leakage must be added before treating the assembly as a finished drawing.

## Evidence to accept the next revision

The next build needs vendor acceptance of thin-post geometry, cap weld/forming and microblade clamp/free-length control; inspection of hook and upper/lower-stop clearances at cold/hot extremes; current-limited RTD/insulation checks; measured membrane and wire drag; and dry/wet jam injection. Load testing must include off-axis pan drag and single-particle roof indentation, not only axial spring force.250°C compound selection and a collision-free STEP are progress toward that build, not qualification. Current result is a dimensionally consistent **dry fixture candidate**, with sealed-product work explicitly outstanding.

Verified geometry: all five states contain29 valid part shapes and no rigid pairwise intersections. Exact optimized cap9.051822mm³; full island59.010861mm³ plus1.125mm³ inner clamps; projected spider area12.698499mm²; three blades4.0824mm³ including mounting pads. The parent Rust simulation owns all thermal/stiffness conclusions; these are CAD measurements.
