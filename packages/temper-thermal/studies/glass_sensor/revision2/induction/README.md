# PR2 cap and suspension induction tradeoffs

**Simulation and test preparation only.** No field, pan temperature, seal performance, material aging or physical response was measured. This study owns only `revision2/induction/`; it does not modify CAD, firmware, the existing validation package or the mechanics model.

Recommendation: carry the **D8 skirtless316L head with separate retention hooks** as the metal baseline and compare **D8 alumina** as the electrically insulating alternative. Keep exposed AlN conditional on grade/finish-specific cleaning and moisture qualification; its conductivity advantage does not settle the complete cartridge design. Avoid any continuous metal retaining ring or conductive outer anchor tying the three flexure beams together. The final material choice also depends on the thermal/contact and mechanical results from the other PR2 workstreams.

The new metal geometry removes the PR1 circumferential skirt and reduces head radius5→4mm. For the same imposed uniform axial RMS field, the unshielded **head-only** loss coefficient falls to9.1% of PR1. This is a topology comparison, not a measured efficiency or guaranteed91% reduction in actual device heating. Retention tabs, force-sensor flexures, strain gauges and wiring remain part of the electromagnetic assembly.

## Exact identities and input status

| Item | Geometry/material | Authority and limitation |
|---|---|---|
| Original CAD baseline | D10roof0.35mm; skirtRo5/Ri4.6/h1.65mm | Prior study frozen CAD |
| PR1 baseline | D10roof0.15mm; skirtRo5/Ri4.6/h1.85mm,316L | Integrated parts_revision at470ac33ec |
| PR2 metal head | D8×0.15mm316L | Parts agent's proposed revision; manufacturing tolerance/flatness not measured |
| PR2 ceramic comparisons | D8×0.25mm,Rubalit710F alumina or Alunit170C AlN | Grade-specific property screens; custom part availability/edge finish not established |
| Retention | 3 separate316L hooks,0.8mm wide×0.15mm thick; **total CAD extra volume1.512mm³** | Captured actual bent-hook CAD includes toes/retention metal. Equal-volume straight-strip surrogate length is4.2mm per hook; this is not its3-D electromagnetic current path |
| Load-island beams | 3separate INCONELX750 foils,freeL7/w2.1/t0.08mm,radialanchorsr4–11,z−6mm | No closed metal outer ring; ceramic anchors proposed. Weld pads, gauges, adhesives, wiring and anchor thermal resistance excluded |
| Alternative closed ring | Ro5.5/Ri4.5/t0.25mm316L | Deliberate topology counterexample, not a recommended part |

Geometry identity: `mechanical-geometry.snapshot.json` is the read-only snapshot of `/private/tmp/temper-r2-mechanical/geometry.json` supplied by the mechanics workstream. `geometry-source.sha256` pins its exact bytes and is checked before reproduction. Its final rest/loaded/local-stop/full-stroke cap volume is9.05182236861571mm³; the separately labeled initial short-post alternative is not used. The disc is7.53982236861550mm³, leaving1.512mm³ of hooks. `results/actual_cap_geometry.csv` attributes mass and capacity separately. The snapshot's own status says DRY instrumented prototype with unsealed witness/lead passages; it does not establish sealing.

The `topology_comparison.csv` has198 imposed-field cases covering11head/retainer configurations. `retainer_radius_sweep.csv` has36counterexamples; `clip_topology.csv` has9generic well-separated narrow-clip cases; `PR2_suspension_sensitivity.csv` has27 strip-approximation sensitivities with the full CAD hook volume. Each sensitivity is SIMULATED. `bash run.sh` compiles standalone Rust, runs16tests and recreates results with source/toolchain receipts. Nothing uses shared Cargo/pyo3 artifacts.

## Electrical calculation and validity

For an electrically closed axisymmetric conducting disc/annulus in uniform axial sinusoidal RMS fieldB:

`E_phi(r)=ω B r/2`, `P=π ω² B² h (Ro⁴−Ri⁴)/(8ρ_e)`.

This is the same Faraday/Joule integration as PR1, tested against its recorded13.946065631mW at40kHz/1mT. Components occupy disjoint head/skirt volumes. Resistivity316L0.75µΩm is the room-temperature supplier value. Ceramic bulk resistivity1e9Ωm is an explicit comparison value, matching the supplier's Rubalit710F lower tabulated value at200°C; it is below the corresponding AlN value. It is **not** a proved minimum at250°C or after contamination. The tiny ceramic bulk-conduction result does not include dielectric loss, surface conductive films, metal pads/metallization or gauges. Twelve decimal display rounds that tiny result to0; do not interpret this as zero total parasitic heating.

The local wall/skin-depth screen and sheet-reaction parameter `μσωRo*min(h,Ro−Ri)` must each be≤0.3. Values useμr1; actual manufactured-metal permeability must be measured. These are heuristic small-parameter checks, **not an error bound**. At40kHz PR2 D8metal head has reaction0.253 and passes that heuristic; PR1closed skirt has0.842 and fails. At60kHz the PR2head fails it. A passed scalar screen does not validate field uniformity, edge coupling, weld geometry, pan shielding or nonlinear magnetic behavior. Values outside regime remain sensitivity coefficients only, not upper bounds.

The narrow-strip comparison uses `P=σ ω² B_normal,rms² L w t w²/12`, derived by integrating the long-strip electric field across its width; current closes near ends. Independent strips must not be reconnected by anchors, gauges, conductive adhesive or mounting hardware. The actual hook volume implies4.2mm equal-volume developed length at0.8×0.15mm section; its surrogate aspect is5.25, but the actual bent toes, welds and head connection violate the isolated straight-strip boundary conditions. Beam aspect3.33 is too short for an accurate long-strip claim. **Every PR2suspension row therefore says OUTSIDE_LONG_STRIP_ASPECT_REGIME_NO_HARDWARE_PREDICTION. Actual bent-hook eddy loss is unresolved.** The generic3×0.5mm strips have aspect6 but remain unvalidated asymptotic estimates. Neither the equal-volume strip nor a slotted-ring proxy is a rigorous heating bound.

Tabs are attached to the conducting head, which changes the3-D boundary conditions; simply summing isolated-strip loss is a diagnostic approximation. The beam field is separately swept at0.1/0.3/1×headfield. Moving a beam6mm below the glass does **not** prove field attenuation. These ratios are not a rigorous actual-field range. Transverse fields, pan return flux, ferrite fringing and drive harmonics remain unresolved. Use RMS consistently; summing harmonic `f²B²` contributions requires valid linear assumptions at each frequency.

## What the numbers mean

At the entirely hypothetical40kHz/1mT axial field:

| Component | Unshielded or strip estimate | Interpretation |
|---|---:|---|
| PR1head+closedskirt | 13.946mW | Outside small-parameter regime |
| PR2D8metal head | 1.270mW | Head alone; heuristic screen passes at40kHz, unvalidated |
| Three PR2hooks, full-volume straight-strip surrogate | 6.792µW | Actual bent/welded geometry unresolved; not its loss prediction |
| Three PR2X750beams withBbeam=Bhead | 67.128µW | Outside long-strip geometry regime |
| Proposed metal head+surrogate hooks+beams subtotal | 1.344mW | Diagnostic sum only; not a qualified total |
| Ceramic head's same surrogate hooks+beams subtotal | 73.920µW | Conductive hardware remains; ceramic/gauge/interface losses excluded |

The3X750beams add approximately29.21mg and12.59mJ/K. Their ideal straight-path conductance is0.000864W/K using12W/mK; contacts, ceramic anchors, gauges and temperature variation alter the actual path. **The full CAD hooks add12.096mg and6.048mJ/K**, giving actual metal cap mass72.415mg and capacity36.207mJ/K. This supersedes the earlier2.2mm-strip approximation, which omitted toe/bent retention volume. It is useful loading information for the thermal model, not a claim these parts all equilibrate with the head.

A D8×0.15mm316L disc **alone** has mass60.32mg and capacity30.16mJ/K. D8×0.25mm alumina and AlN disc-only comparison capacities are38.20 and28.68mJ/K using tabulated100°C heat capacities and density as screening values; their actual retention design still needs closure. Vertical head resistance over the M2224.83mm² face is2.070K/W for both metal and alumina, and0.3045K/W for AlN. An additional optional IST1.92mm² face comparison gives5.208/5.208/0.766K/W respectively. These one-dimensional head figures exclude spreading, bond, RTD, contact resistance and mechanical carrier. Alumina does not automatically produce faster response than the thin metal head; the complete network must decide.

## Material and cleaning constraints

The grade-specific [CeramTec property table, PDFp.2](https://www.ceramtec-group.com/fileadmin/user_upload/Corporate/11_Downloads/06_Electronic_Heatsinks/Datasheet_Electronic_Applications.pdf) identifies Rubalit710F and Alunit170C. Room-temperature conductivity is25 and170W/mK respectively; listed density lower values3800/3260kg/m³ and100°Ccp800/700J/kgK are used as comparison points. Strength and substrate dielectric values in that table are test-method-specific; they are not cookware impact allowables or an appliance insulation rating. Custom thin-disc finish, defects, support, thermal gradients and point contact require the mechanics workstream's analysis and tests.

AlN hydrolysis is relevant to **sintered ceramic**, not just powder. [Tamai etal., original ceramic-corrosion study](https://ceramics.onlinelibrary.wiley.com/doi/10.1111/j.1151-2916.2000.tb01710.x) reports boehmite formation and strength loss under some hot-water/vapor conditions. Its abstract distinguishes180°Cimmersion from180°Cvapor outcomes; it cannot be converted into a domestic-cleaning lifetime or a universal percentage strength derating. The study's material/condition is not proof of behavior of this proposed supplier grade.

[Alconox's manufacturer cleaning note](https://technotes.alconox.com/industry/medical-device/how-to-clean-aluminum-nitride-aln/) specifically warns about prolonged/repeated alkaline cleaning of AlN and proposes a mild-acid process. That is supporting process evidence, not permission to require a proprietary detergent for a consumer cooker or a validated recipe for this seal/bond assembly. The product must tolerate its intended cleaning agents, spill chemistry, abrasive wipe and hot/cold cycles. No retrieved source establishes the selected grade's endurance in this exact service.

Do not close the AlN issue by adding an unqualified coating: pinholes, abrasion, chipped edges and thermal cycling can expose it; a metal coating can restore induction loss and a thermal overcoat changes contact response. Compare approved-grade/finish coupons after representative wet/alkaline/acid/salt/oil exposure, measure surface change, strength distribution, insulation/leakage, mass and thermal response. Alumina also needs chemical/process qualification; preference here is avoiding a documented additional AlN-specific mechanism, not claiming alumina is universally inert.

[Special Metals X750 bulletin, Tables2–3](https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-x-750.pdf) supplies density8.28g/cm³, resistivity1.22µΩm(731ohm-cmil/ft), room-temperaturecp431J/kgK and conductivity≈12W/mK. Its permeability depends on heat treatment. This model uses room-temperature linear nonmagnetic behavior only; it does not establish gauge accuracy, cyclic force or heat-treated0.08mmfoil properties.

## Required field-model geometry and decision constraints

Before a numerical EM result can become a device heating prediction, obtain coil winding centerlines/strand bundle, turns, ferrite blocks with complexμ(B,f,T), conductive shielding and attachments, glass/probe3-D locations, actual resonant current spectrum/burst envelope, and each cookware layer's dimensions/conductivity/complex permeability over temperature. Include the actual cap, welds/hooks, X750beams, resistive gauge grid/backing, bridge traces, lead return paths, all metal fasteners and electrical connections. Model pan offsets/gaps and component motion; mesh convergence alone does not validate material or excitation data.

Check three failure geometries explicitly: (1) a metal ring replacing ceramic retention, (2) continuous metal anchors or strain-gauge ground joining otherwise separate beams, and (3) conductive contamination/metallization bridging an intended insulating interruption. Retaining ring loss grows strongly with radius; moving a loop outward is not an automatic improvement. Retest hot-point contact, impact and cleaning after any slot, coating or retention change. No CAD collision check demonstrates ceramic strength or seal integrity.

Keep the PR1[coil-on/off acquisition plan](../../induction_validation/TEST-PLAN.md), including dummy-resistor tests and dissimilar optical references. Add independent beam/island temperature and local force-zero drift under switching. Real beam self-heating can mimic a contact-force change even when the RTD channel appears clean. Preserve the complete contact-to-PERMIT/current-extinction chain; geometry choices here do not prove continued pan contact.

Sources checked2026-10-04. No parts ordered, energized tests performed, standards compliance asserted or files published.
