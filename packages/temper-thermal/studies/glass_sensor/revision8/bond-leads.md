# R8 bond and native-lead readiness

**Public evidence does not make the R7 bond/lead process fabrication-ready.** It does identify two concrete conflicts with treating the CAD as a build instruction: both modeled bond thicknesses sit below Cotronics' published generic guidance, and the generic ceramic post-cure exceeds the IST308 operating range. Preserve the R7 numerical controls; obtain an exact Resbond908 process or qualify an alternative before claiming their geometry is manufacturable.

Scope: dry engineering coupons, simulation and test preparation. Physical result: **NOT_RUN**. No supplier contact, procurement or hardware operation occurred. Reviewed R7 mechanical README, PR1 parts selection and R5 build package. Applied the Temper manufacturing-review skill; its methods do not establish numerical acceptance limits.

All sources below were retrieved or rechecked **2026-10-04**. Document versions are stated where visible; retrieval does not establish that an undated catalog controls a received lot.

## Evidence that changes the next step

| Item | Evidence and exact primary source | Status / consequence |
| :-- | :-- | :-- |
| M222 identity and native material | 32208550 is Pt100 F0.15; wires are platinum-clad nickel; nominal resistance is referenced 8 mm beyond the body. [M222 datasheet, pp.1–2](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN). | **CONFIRMED.** R7's pure-nickel thermal properties remain a proxy. Trimming to 1 mm does not preserve the catalog resistance datum. Cladding thickness and composite properties are unknown. |
| M222 joining and lead strength | Welding, crimping and brazing are listed; lead tensile strength ≥9 N is listed. No qualifying test setup for the proposed four-wire splice is given. [M222, p.2](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN). | **CONFIRMED / LIMIT.** The 9 N figure is not a permissible installed pull load or an assembly acceptance limit. No weld energy, alloy or splice process is qualified. |
| M222 forming and insulation | The sheet permits batch-dependent V-shaped delivered leads; it lists element insulation resistance >100 MΩ at20°C and >2 MΩ at500°C. [M222, p.2](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN). | **UNKNOWN assembly qualification.** Delivered V-shape is not permission for arbitrary re-forming. Neither resistance value qualifies the cap/bond/join insulation. |
| IST exact element | P0K1.308.3K.A.007, order101941: Pt100 F0.15, 3×0.8×0.25/0.6 mm, 7 mm wires with Ø0.15 exception to the table's Au-coated Ni-wire family. Range−200…300°C. [DTP300_E2.4.3, pp.2–3](https://www.ist-ag.com/sites/default/files/downloads/DTP300_E.pdf). | **CONFIRMED.** Au thickness, exact exit coordinates, pad pitch and tolerance of those coordinates remain unreported. R7 has only 0.806628494 mm of installed native lead. |
| IST electrical datum | General application note: electrical contact is **5 mm from wire end**. [ATP_E2.4.4, §6, p.4](https://www.ist-ag.com/sites/default/files/downloads/ATP_E.pdf). | **NEW DATUM / PRODUCT CONFIRMATION NEEDED.** Nominal7−5=2 mm suggests a body-edge offset if the listed wire-length datum applies; this is an inference, not an exact101941 calibration drawing. It must not be substituted for M222's differently stated datum. |
| IST film construction | A platinum meander lies on ceramic, with glass passivation and separate lead fixation. [ATP_E2.4.4, §2, p.3](https://www.ist-ag.com/sites/default/files/downloads/ATP_E.pdf). | **PARTLY CONFIRMED.** No dimensioned101941 film location identifies which CAD face should meet the cap. R7's0.125 mm path remains hypothetical; neither the whole0.6 mm envelope nor half of it is a verified ceramic heat path. |
| IST forming | The manufacturer advises against bending/twisting close to the element. [IST FAQ, “Sensor processing: What precautions should I take…”](https://www.ist-ag.com/en/faq?istr=4). | **CONFLICT TO RESOLVE.** The R7 sub-millimetre stub and R0.5 bend are near the element. No public numerical stand-off/radius approves them. Supplier-formed or differently routed leads may be necessary. |
| Sensor/bond compatibility | IST warns of reactions between some ceramic casting compounds and sensor glasses, stress from hard/post-curing compounds, and unsuitable prolonged humidity or immersion. [ATP_E2.4.4, §11, p.6](https://www.ist-ag.com/sites/default/files/downloads/ATP_E.pdf). | **NEW EXPLICIT COMPATIBILITY GATE.** No public statement reviewed approves Resbond908 directly against this sensor. |
| Resbond908 product data | Two-component alumina; table mix100/33; k15 BTU·in/(h·ft²·°F), dielectric200 V/mil and resistivity10¹⁰Ω·cm. Room-temperature cure; water insolubility after250–300°F exposure/post-cure. [Cotronics catalog, printedpp.24,26](https://www.cotronics.com/catalog/cotronics_catalog.pdf). | **CONFIRMED MATERIAL DATA ONLY.** No duration is provided for the908-specific water-insolubility statement. These values do not establish a thin installed bond's properties or moisture seal. |
| Ceramic instructions | Generic recommended gap0.010–0.020in; initial air-set1–4h and ≥2h at200°F; maximum-properties post-cure1h at250°F, then1h at600–700°F. Product-label instructions take precedence. [Cotronics catalog, printedp.64 / PDFpage69, “Ceramic Adhesive Instructions”](https://www.cotronics.com/catalog/cotronics_catalog.pdf#page=69). | **GENERIC, NOT908 RELEASE INSTRUCTIONS.** The final generic stage is315–370°C, above IST308's300°C range. Do not apply it to the assembled sensor by default. |
| A second thickness range | Cotronics FAQ gives0.005–0.008in for standard epoxy/ceramic adhesive bonds. [Cotronics FAQ, “Recommended Bond Line Thickness…”](https://www.cotronics.com/vo/cotr/faq.htm). | **UNRESOLVED GUIDANCE.** That is0.127–0.2032 mm; the ceramic instructions give0.254–0.508 mm. R7's0.075 and0.100 mm are below both. Different generic contexts may explain the difference; neither defines an approved908 minimum. |
| Particle size, shrinkage and thin-film ratings | No908-specific maximum/agglomerate size, cured shrinkage, guaranteed minimum thickness, or250°C wet/contaminated thin-layer dielectric performance was found in the reviewed primary sources. | **UNKNOWN.** Do not borrow numbers from neighboring Cotronics epoxy/casting products, or infer particle size from dispensability. |

The dimensional/CAD work is still useful: it defines the assembly to ask suppliers to assess and the specimen to measure. It does not resolve these chemistry and processing questions. Changing to0.15 or0.25 mm because one generic paragraph appears close would repeat the same unsupported selection.

## Controlled traveler: preparation, not authorization to fabricate

Common article record: serial; drawing and scalar hashes; RTD MPN/lot; received dimensions and lead photos; cap alloy/finish/roof measurements; adhesive base/activator lots and shelf condition; governing product-label revision; actual mixture masses; fixture identity; bond target and measured result; film-facing orientation evidence; trim/form/join process revision; calibrated instrument identities; cure time/temperature trace; operator; deviation disposition. Store raw data separately from calculated screens.

| Variant | Controlled difference from matched M222 control | Installed-native target retained from R7 |
| :-- | :-- | :-- |
| M222_control_010 |0.100 mm nominal bond; clearance-corrected common covers | Two1.000 mm stubs, same lead/join geometry |
| M222_thin_0075 |0.075 mm nominal bond only; same cap, covers, process and sensor lot where feasible | Same as control |
| IST308_thin_0075 | Exact101941 package and its relieved anchor/covers/routes;0.075 mm target | Two measured0.806628494 mm paths, R0.5 modeled bend |

These lengths/thicknesses are experimental targets, not tolerances or supplier permissions.

1. **Resolve process identity before dispensing.** Attach received908 instructions and supplier disposition of the thickness/cure conflicts. If unresolved, keep the traveler `PROCESS_UNDEFINED`; do not quietly select a generic schedule. An alternative adhesive creates a new material revision and thermal model input.
2. **Receive and map the element.** Photograph both broad faces and lead exits, identify substrate/passivation/fixation landmarks, and record the surface intended for bonding. Do not abrade the RTD to make a nominal fit. Keep unknown orientation as an explicit model branch.
3. **Characterize the untouched element.** Record resistance at declared reference conditions with actual probe locations and excitation; retain a same-lot unprocessed witness. Measurements made at convenient clip positions are not automatically catalog-datum measurements.
4. **Prepare an accessible cap subassembly.** Establish cap and element datums in an external removable fixture. Record cleanliness, flatness and height-metrology capability. Do not place unmodeled hard spacers, fibres or conductive particles into the heat path.
5. **Dispense and cure under the resolved process.** Record actual wet gap and movement during cure. Cure witnesses beside every experimental article. Use their measured cured thickness/coverage, not the fixture setting alone, as model input. Do not “thin until it fits” by adding unapproved solvent or activator.
6. **Develop the lead operation separately.** Record trimming order, tool support, bend start, bend radius and join location. Make sacrificial joining witnesses before processing the thermal pair. Measure resistance change after each operation so forming damage is distinguishable from bond/cure damage. Four extension wires still leave two native stubs inside the measurement.
7. **Inspect before installing covers.** Image joints and the two electrically distinct nodes; inspect lead-to-cap spacing and insulation continuity. Then install covers using their own recorded attachment-film process. Add all four60 mm routes and measure harness force throughout motion; free lead layout alone does not establish the installed force.
8. **Retain a destructive witness.** Section through the bond and lead-fixation region. Report thickness map, wetting/void distribution, cracks, insulation interruptions and apparent chemical attack as measurements. Do not convert an invented void-percentage limit into acceptance.
9. **Characterize the assembled heat path.** Use the existing R7 calibration protocol with declared reference lag/uncertainty and a different-pan holdout. Keep raw sensor performance separate from fitted compensation. Repeat electrical/mechanical observations after the specified exposure; define exposure count and conditions in the campaign record before testing.

## Inspection gates and acceptance authority

| Gate | Evidence to collect | How it is judged / owner |
| :-- | :-- | :-- |
| Exact process compatibility |908 label, sensor integration response or a reviewed alternative process; material identity | Manufacturing lead resolves contradictions; currently **OPEN**. |
| Thickness and heat path | Calibrated section/metrology map and contact/boundary measurements | Compare actual geometry with the model; rerun if different. R7 supplies nominal targets, not process capability limits. |
| Sensor stability through processing | Pre/post operation resistance data at declared temperature, excitation and probe datum | Separate calibration changes from irreversible damage; temperature-error allocation remains the existing proposed system screen. No new drift allowance is invented. |
| Electrical isolation | Dry/hot and application-relevant contaminated/wet insulation observations | Electrical safety owner must derive voltage/current criteria from system architecture. Material200 V/mil cannot supply the assembly test voltage. |
| Joint and attachment mechanics | Pull/peel displacement curves, failure location, harness force and cap movement | Characterization first; product loads and a reviewed retention/join requirement are still required. Catalog lead strength is not the finished joint criterion. |
| Thermal performance | Independently referenced step/ramp/steady measurements plus uncertainties and holdout | Existing R7 proposed strict<2°C and<2s screens apply only under their stated conditions; they are not certification or proof of all-cookware control. |

## Supplier questions — DRAFT, NOT SENT

**Cotronics (exact908-1 base/activator and intended lot):**

1. Can you specify a controlled process for a cured75 µm or100 µm layer between316L and the exact RTD contact surface? State minimum thickness, maximum particle/agglomerate size and applicable dimensional variation.
2. Which received-lot instructions control the generic gap and post-cure differences above? Provide mix basis/order, allowable dilution, working time, staged cure and minimum water-insolubilization time. Can the complete process remain within the RTD's permitted exposure?
3. Provide cured shrinkage, modulus/CTE and conductivity versus temperature for that process, and any evidence on adhesion/chemical compatibility with alumina, platinum-sensor passivation glass, fixation glass and316L.
4. What insulation/moisture data exist for the actual thin bond after250°C exposure and cleaning/condensation cycles? What specimen thickness, electrodes and conditioning produced the published electrical values?

**YAGEO (32208550):**

5. Identify the film/passivation/bondable faces in a dimensioned cross-section, native lead core/cladding dimensions and the resistance reference datum for trimmed assemblies.
6. Is a1 mm installed stub with the R7 Kelvin split feasible? Provide minimum straight length, permitted forming/support method, and recommended joining process. What must be recalibrated after trimming?
7. Is direct Resbond908 bonding compatible with this element and cure exposure? Which chemical constituents, shrink stresses or surface treatments are disallowed?

**IST (101941 / P0K1.308.3K.A.007):**

8. Supply dimensioned film, substrate, passivation and fixation geometry; exact lead exits/pitch; Au/Ni cross-section; and permitted bondable surface.
9. Confirm how ATP§6's end-referenced electrical contact point applies to this7 mm part, including wire-length tolerances and the effect of trimming to the proposed path.
10. Assess the full R7.8066 mm stub/R0.5 geometry against your near-element forming warning. If unsuitable, specify a factory-formed/custom lead or a minimum routing envelope instead.
11. Confirm Resbond908 chemical/cure compatibility and available qualifying data for an electrically insulating attachment used near250°C. Identify whether an alternate assembly method is preferred.

## Smallest first experiment to prepare

Start with a **bond-process falsification coupon**, not the full moving cartridge. Prepare one316L/alumina witness at each R7 target thickness, plus a manufacturer-specified reference thickness and an unbonded material witness. The reference thickness is deliberately **TBD**, pending exact908 instructions; it is not chosen from a generic range. Use external gap control, photograph and measure the cured section, then characterize insulation and evidence of shrinkage/cracking. One specimen per condition can disprove feasibility; it cannot establish repeatability or qualification.

If that process is credible, prepare the matched M222 pair with the same cap, element lot and joining process, plus an untouched same-lot element witness. Measure the process-induced resistance changes and independently referenced thermal response. Add the IST specimen after its near-element forming and orientation questions are resolved, so a faster nominal simulation does not obscure an unbuildable lead geometry. This sequence remains test preparation: **all specimens and results are NOT_RUN**.
