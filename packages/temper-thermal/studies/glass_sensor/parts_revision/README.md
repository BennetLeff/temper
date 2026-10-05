# Selected cartridge parts revision PR1 — 2026-10-04

**Simulation and test preparation only.** This is a traceable engineering-prototype candidate, not a qualified cartridge. No parts were bought, no hardware was measured, and no heating was performed. Parent study base: `767f2fbae7a842e58afb288c5966453f10ab3d7a`.

## Decision

Select M222 Pt100 **32208550**, ASRaymond **C01800120560X**, custom **316L cap**, and Cotronics **Resbond 908-1** for procurement/coupon preparation. Use a custom WACKER **ELASTOSIL R 401/30 S** diaphragm as a **bounded lower-temperature development candidate only**. Its published210°C range does **not** cover the proposed250°C cooking envelope. There is no qualified off-the-shelf seal for this geometry. The seal is the principal unresolved part-selection blocker; the current geometry directly connects its inner lip to the hot cap, so a cool body or glass temperature does not bound the inner-lip temperature.

[Candidate BOM](BOM.csv) contains manufacturer/procurement links and explicit statuses. Stock/lead time and lot tolerances were not obtained; a listed catalog identity is not an inventory promise. Ordering, vendor inquiries and physical tests remain outside this simulation-only work.

## What changed in CAD

[Rest STEP](PR1-rest.step), [flat-pan STEP](PR1-flat_pan.step), [full-stroke STEP](PR1-full_stroke.step), [maximum-chip STEP](PR1-max_chip_full_stroke.step), [section STEP](PR1-section.step), [section projection](PR1-section.svg), and individual STEP parts under `parts/` are generated from the frozen source, preserving its mounting datum and carrier geometry.

* Cap stays10mm diameter and0.6mm above glass. Roof reduces0.35→0.15mm; skirt remains0.4mm thick and extends1.85mm to the unchanged bottom at z−1.4. **Full cap volume34.09885mm³**, versus47.3941 originally; only28% mass reduction. A thinner roof does not eliminate skirt thermal mass or induction heating.
* Actual M222 nominal body2.3×2.1×0.9mm replaces3×2×0.4mm. Supplier maximum2.5×2.3×1.2mm also fits. Nominal roof underside z0.45,0.10mm bond, sensor bottom−0.55. At roof0.20/bond0.15/chip1.20 worst selected stack, sensor bottom−0.95; plunger head top−1.40 gives0.45mm body clearance. Chip lead bending, strain relief, Kelvin splice and full10mm supplier lead length are **not** validated by the reserved cable envelope.
* Spring now has actual catalog OD4.6/ID4.0mm and working length13.45mm. Lower plunger diameter changes6→3.6mm below z−15; upper guide remains6mm. Lower spring seat moves to z−28.45; moving upper seat is z−15 at rest. Reserved four-wire bundle reduces to1mm with a0.7mm slack-loop excursion to clear the narrower spring; actual insulated wire gauge and bend-life remain unselected. Spring body is explicitly a cylindrical **installation envelope**, not a guessed manufacturing helix.
* Existing custom diaphragm/static seal envelopes remain labeled as such. No inferred elastomer stiffness, sealing pressure or fatigue life was assigned to them. No detector hardware was added.

Four exported assembly states each contain22 valid solids, STEP round-trip valid, with **zero rigid intersections**. Flexible seal/spring/harness envelopes are excluded from rigid intersection checks. Those checks establish nominal fit only, not load capacity, glass-hole strength or sealing. The max-chip state is not a full tolerance Monte Carlo.

## Spring force and detector interface

Supplier nominal: free14.2mm, rate0.2N/mm, solid≈2.2mm;316 wire to ASTM A313; operating range−196…260°C. Page also lists load1.4 at length8mm, while rounded rate predicts1.24N. **Do not treat the0.2 number as a calibrated force curve.** Confirm units and tolerance with vendor; measure force at13.45,12.85 and12.10mm before setting the seat.

At nominal rounded rate, gross spring force is0.15N at rest,0.27N with a flat pan depressing0.6mm, and0.39N at nominal1.2mm stroke. At worst assumed1.35mm stroke, length12.10mm is9.90mm above approximate solid. Spring travel reserve is ample; force calibration and return drag dominate. Moving-part gravity reduces tip preload:0.01N is about1g, not zero. The study sweeps **net** preload0.12/0.14/0.16N, with±20% rate sensitivity, rather than equating supplier force to net tip force. These are proposed assembly controls/sensitivity bounds, not vendor tolerances.

Nominal0.35mm pan recess leaves0.25mm motion. Height0.45mm at that recess leaves only0.10mm, giving merely0.02N spring-force change. Contact team is evaluating force plus optical position; neither a force reading nor displacement proves clean metal contact. Reserve an **optional instrumented lower seat at z−28.45 for force characterization only**; a commercial force cell changes seat height/compliance and must be designed back into the stack. **A jam after acquisition can leave both lower-seat force and position signals asserted with the pan removed.** Those signals therefore do not independently establish ongoing cap-to-pan contact. A detector would need a cap load path above every guide/seal/stop reaction, or another qualified independent contact measurement; that redesign is unresolved. No force-cell footprint is claimed to fit this revision. Guide and spring must return after heat/cleaning with wire drag included; a stuck depressed tip is a false-positive position signal.

## Thermal results with the actual selected geometry

Rust reuses the original independently tested network solver but builds new capacitances/resistances from actual M222 geometry, full cap volume and sourced material nominal values. It runs21,870 mechanical scenarios,5,832 thermal scenarios and486 material-property sensitivity scenarios. Deterministic grid fractions are **not reliability estimates**.

| Conditional example | t90 of own final rise | t90 of imposed pan step | Error at pan200°C |
|---|---:|---:|---:|
| Middle sensitivity assumptions |6.460s|7.980s|−5.924°C|
| Favorable contact/leakage assumptions |2.185s|2.225s|−0.640°C|
| Weak force0.09N and30% area |16.775s|not reached in120s|−14.712°C|

All three use the same selected parts; contact/loss boundary assumptions change. Favorable is not a prediction. Middle is force0.25N,h_ref1000W/m²K,full area,cap loss0.002W/K,lead loss0.0003W/K. Favorable changes h_ref4000,cap loss0.0005,lead loss0.0001. Weak changes force and area only. Pan k45W/mK; bond0.10mm; nominal chip0.9mm. Step25→100°C with body/glass25°C; error200 uses glass80/body60°C. Only387 of5,832 deterministic thermal grid points meet both t90_final≤3s and|error200|≤5°C; this sparse count says the proposal is conditional, not that it is6.6% reliable.

RTD geometry is now physically faithful; the supplier does not specify its effective heat capacity, ceramic conductivity, film orientation or bonded response. Ceramic volume heat capacity3.12MJ/m³K and conductivity25W/mK remain explicit proxies. Bond volume heat capacity2MJ/m³K is unsourced, swept1–4. Cap room-temperature values are sourced; temperature dependence is swept, not extrapolated as known. Contact-pressure law and h_ref250/1000/4000 remain unvalidated sensitivities. Seal conduction and friction are not calculated from its Shore hardness. Outputs do not include a solved magnetic field, full layered pan or thermal contact resistance measurement.

The21,870 mechanics cases include282 lifted-pan cases and4,860 without guaranteed return. Some intentional stress corners have0.15N drag and net preload0.12/0.14N; others exceed the0.15kg/eccentric pan's force support. This is evidence to specify and test drag and total seal force, not a defect rate.

## Primary-source values and manufacturing constraints

* [YAGEO M222 v03,11/2024](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN):32208550 ClassA valid−50…300°C; dimensions2.3(+0.2/−0.1)×2.1(±0.2)×0.9(+0.3/−0.2)mm; leads10±1mm,diameter0.2±0.02mm; Pt100 excitation0.3–1mA. Water/air response ratings do not apply to the bonded cartridge. Choose0.3mA initial characterization, verify ADC noise budget separately; thermal sweeps exclude self-heating to isolate conduction.
* [ASRaymond catalog](https://www.asraymond.com/en-eu/europe/mechanical-wire-springs/compression-springs/spec-standard-compression-springs-167838/c01800120560x-c01800120560x/): nominal spring data above; squared ends. Formed part, hot relaxation, rate tolerance and cycle life need supplier/lot evidence. Static solid margin is not fatigue life.
* [Outokumpu Supra datasheet](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf):316L/4404 density8000kg/m³,cp500J/kgK,k15W/mK,resistivity0.75Ω·mm²/m at20°C,CTE16×10⁻⁶/K over20–100°C. Custom cap candidate is a machined thin roof with integral skirt for the first10 engineering specimens; process capability, roof flatness, edge radiusing, cleaning/passivation and dent loads require fabricator review. Do not infer post-forming permeability from the nominal austenitic table.
* [Cotronics catalog pp24,26](https://www.cotronics.com/vo/cotr/pdf/A_2020_Catalog-NP.pdf):Resbond908 alumina adhesive; listed k15BTU·in/(h·ft²·°F)=2.1634W/mK; CTE4.5×10⁻⁶/°F=8.1×10⁻⁶/K; two components100/33; RT cure with121–149°C postcure to make water-insoluble;200V/mil and10¹⁰Ω·cm are material coupon values, **not assembly dielectric approval**.0.10±0.025mm bond is an unproven process target: maximum filler size/minimum bond, voids, steel adhesion and brittle CTE mismatch are blockers. Require supplier-specific cure instructions and polished cross-section before crediting that thickness. Use a coupon-limited0.15mm branch if0.10mm cannot be controlled; simulation includes both. Avoid transferring ceramic bulk properties to a porous cured adhesive.
* [WACKER R401/30S](https://www.wacker.com/h/en-us/silicone-rubber/high-consistency-silicone-rubber-hcr/elastosil-r-40130-s/p/000005478):moldable,peroxide-cured compound; stated−55…210°C; heat stabilizer recommended above180°C. Postcure/food-contact statements are conditional on extractables/volatiles. Custom diaphragm0.2mm envelope is a moldability request, not accepted manufacturing capability. Pilot target is to keep **every seal point≤180°C** until a specific stabilized formulation and lifetime are qualified. Since that temperature is unmeasured and the lip touches cap, **250°C operation is blocked** for this candidate.

All sources checked2026-10-04. Numerical nominal data are facts, not in-house measurements. Product-page tolerances absent from those sources remain absent from the model.

## Prototype assembly and evidence needed next

The next stage is a controlled engineering prototype, after vendor review of the custom cap/diaphragm and bond process. Proposed quantity10 supports learning across assembly variation, not a capability claim. Identify each RTD, spring, cap and compound lot. Inspect glass datum, cap roof flatness/thickness, stem clearance and lower-stop travel before assembling. Bond the RTD into a separately fixtured cap, cure per supplier, inspect bond thickness/voids, weld/crimp Kelvin leads with strain relief, then mount the cap on its ceramic plunger. Install selected spring and force-adjust lower seat using a fixture; seal cure/compression and wire routing must precede final hot/cold force verification.

Do not rely on bond adhesion to carry cookware load or seal preload. This revision retains the original cap-on-plunger shoulder geometry; **positive cap retention and peel/load-path details remain unresolved**. The thin roof needs a dent/overload test (including contamination point loads) before on-pan use. Seal leakage, cyclic adhesion, cracked adhesive insulation and return force must be measured on the same assembled revision. A dimensional clearance pass cannot close these items.

Capture actual spring curve, seal incremental force/hysteresis, wire drag, cap mass and thermal step traces in the sibling calibration package. Only then fit contact conductance and leakage and rerun. Contact detection and induction susceptibility are separate sibling workstreams; detector fitting may require a new lower seat/carrier revision.

## Reproduce and verification

From this directory:

```sh
CAD_PYTHON=/private/tmp/temper-center-sensor-env/bin/python bash run.sh
```

Requires rustc/rustfmt and CadQuery2.6.1. No Cargo/pyo3 extension build occurs. Source inputs are `../model.rs` and frozen `../inputs/mechanism.py.txt`; `selected.rs` generates `cad-parameters.json` consumed by CAD. **20 Rust tests passed**, comprising14 inherited solver/mechanics checks and6 selected-part checks (actual chip capacity, no-loss equilibrium, spring solid margin, timestep refinement, weak-contact failure, conductivity unit conversion). STEP roundtrip and rigid intersections pass all4 states. CSVs retain each case;`results/summary.txt` records headline results. Build artifacts go to temporary directories. Reproduction changes only this owned directory.
