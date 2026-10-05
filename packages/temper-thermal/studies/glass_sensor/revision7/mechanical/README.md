# R7 experimental cartridge coupons

Three nominal D6 coupons now have complete installed cartridge CAD: a clearance-corrected M222 0.100 mm control, a 0.075 mm M222 bond, and an IST308 with a 0.075 mm bond. This is **experimental geometry for dry instrumented test preparation**, not a production release. Physical measurements and supplier/process qualification are `NOT_RUN`.

The IST308 is not a drop-in replacement in the R5 head. Its longer package collides with the original anchor and four hot wire approaches. R7 relieves the cover and anchor, reroutes those approaches, and measures their changed volumes and lengths. The D6 cap, retention hooks, support, stops and witness structure remain inherited R5 geometry. Both M222 variants receive the same cover relief around the union of their supplier maximum body envelopes, so their comparison continues to isolate bond thickness. Their cover capacities differ from R5; the frozen R5 remains a separate historical numerical baseline.

## Geometry and identity

The fixed datum is the nominal glass top at z=0 mm. At rest the cap face is z=0.60, its underside z=0.45. The roof is 0.15 mm thick. The cartridge housing is Ø28 mm, with an Ø18 mm glass aperture. The full assembly includes the inherited unsealed witness rods and seal envelopes. A solid seal shape does not establish a closed gas/liquid boundary.

| Coupon | Package envelope (mm) | Bond pad (mm) | Native lead installed | Extension routes |
|---|---|---|---|---|
| M222 control | 2.3 × 2.1 × 0.9 | 2.7 × 2.5 × 0.100 | Two Ø0.2 × 1.0 mm | Four 60 mm Cu/PFA |
| M222 thin bond | 2.3 × 2.1 × 0.9 | 2.7 × 2.5 × 0.075 | Two Ø0.2 × 1.0 mm | Four 60 mm Cu/PFA |
| IST308 thin bond | 0.8 × 3.0 × 0.6 | 1.2 × 3.4 × 0.075 | Two Ø0.15, measured curved paths | Four 60 mm Cu/PFA, rerouted hot approaches |

Both stock sensors require trimming in these models. **Complete installed native leads are modeled; full stock leads are not retained.** Installed calibration and an approved trim/form/join process are prerequisites for using either coupon. A four-wire extension does not remove the resistance or temperature dependence of the two native lead stubs between the element and split joins.

The IST part is P0K1.308.3K.A.007 (order 101941). Its supplier sheet specifies a 3.0 × 0.8 × 0.25 mm substrate, 0.6 mm overall height and 7 mm Ø0.15 leads. It does not dimension the selected pad pitch or precisely locate the active film within the package. R7 assumes both leads exit the short end at x=±0.2, y=1.5, z=0, relative to the package shown. Its nominal bond-to-film path remains the R6 0.125 mm proxy, with thermal sensitivity required across the full height. The modeled full envelope is **not an assertion that all 0.6 mm consists of dense ceramic**. Thermal results must bracket the effective capacity.

The M222 model uses YAGEO 32208550 and retains its nominal R5 chip envelope and lead arrangement, with corrected cover clearance. The datasheet resistance reference is 8 mm beyond the body; the installed 1 mm leads require calibration. No claimed Class A result is transferred unchanged to this trimmed assembly.

The IST native lead uses a 0.5 mm centerline bend radius. The inherited extension routes use 0.5 mm static and 2 mm moving-loop radii. These are modeled forming hypotheses, **not supplier fatigue limits**. Native lead plating thickness, weld alloy/geometry, insulation clearance and cure process remain unverified. The welds are process envelopes with geometric connectivity checks.

## What the CAD checks establish

`build.py` exports four poses per coupon: rest, loaded (common 0.490909 plus local 0.109091 mm), full stroke (1.2 plus 0.25 mm), and cap capture (0.2 mm cap lift). It checks valid B-reps, rigid intersections, lead/extension-to-rigid interference, extension-to-extension interference, correct weld-to-native and weld-to-extension overlaps, rejection of wrong native connections, and reimported STEP validity and total volume parity.

Native-to-package entry is an intentional terminal attachment intersection; it is excluded from collision rejection and is not treated as insulation verification. All other conductive-to-rigid intersections are screened. The inherited witness rods and membrane shapes are envelopes. These checks do not prove contact detection, seal integrity, preload, retention strength or thermal expansion tolerance.

`audit.py` independently checks swept wire/native volume against cross-section × full centerline length, introduces a disconnected weld to demonstrate rejection, and tests supplier maximum body envelopes against neighboring CAD. **Nominal fit is distinct from maximum-envelope fit**; consult `independent-audit.json` for actual collision findings. No maximum package collision is hidden or absorbed into a release claim.

`thermal_geometry.csv` is the actual rest-pose scalar contract. Unchanged dimensions inherit a pinned R5 row; every modified chip, native lead, cover, cover film and anchor volume comes from the R7 solids. Rest support volume is explicitly compared with R5. Four individual routed hot/cold lengths are retained in `geometry.json`; the thermal contract uses their arithmetic mean. For IST, effective anchor path length is measured by intersecting the full swept wire with the anchor envelope and dividing by its cross-sectional area. Actual boundary conductance remains a model assumption. Radial thermal bins still approximate non-axisymmetric covers and the anchor.

## Assembly and inspection preparation

1. Identify the received element part/lot, measure package and lead geometry, and resolve the lead exit/film orientation with the supplier or sacrificial sections. Record received stock dimensions before trimming.
2. Inspect the cap roof and hooks, and dry-fit the chosen element, relieved cover/anchor and harness. Use the supplier maximum-envelope audit to decide whether larger clearances or selected dimensions are required before a physical build.
3. Establish bond thickness using an external calibrated cure fixture, not loose conductive spacers beneath the face. The 0.075 mm layer is a design target; flatness, particle size, shrinkage, voids, cure and electrical isolation must be measured.
4. Form the native leads with supported tooling; join the four extension wires using a developed weld process. Measure installed resistance, pull strength and isolation to the cap. Add the ceramic join covers and their separate 0.075 mm attachment films. R7's channel cuts establish nominal fit, not a guaranteed insulation wall.
5. Assemble the cartridge and route all four 60 mm extensions without loading the sensor. Inspect minimum clearances through the full motion, measure harness force hot/cold, and perform installed calibration before comparing response.

The next supported stage is a **controlled engineering prototype**, contingent on the reported geometric checks and unresolved process assumptions. No hardware is available in this task, so all bond sections, weld pulls, force, sticking, response, induction and endurance tests remain NOT_RUN.

## Reproduce

Run `./run.sh` with CadQuery 2.6.1. The default prepared interpreter is `/private/tmp/temper-center-sensor-env/bin/python`; override `CAD_PYTHON` for an existing compatible environment. No installation or Cargo build is needed. Python only constructs/inspects CAD and renders presentation; the thermal computation stays in the separate Rust study.

The canonical R5 and R2 sources are immutable pinned dependencies, verified before generation along with the inherited scalar CSV. Scratch-only copies are fallback dependencies outside the repository. The supplied STEP files are full assemblies and hot-head subsets; section SVGs and `coupon-cutaways.png` are inspection aids. `inputs.sha256` records source and derived artifact identity after successful generation; the runner removes an older receipt before starting. Derived scalar values are serialized to nine decimal places to avoid insignificant OCCT numerical tails changing the thermal input identity; unchanged inherited scalar text is preserved. STEP timestamps may change on regeneration; their byte identities are snapshots, while the scalar contract provides reproducible geometry identity.

## Primary sources

- [IST 300 °C series, DTP300_E2.4.3](https://www.ist-ag.com/sites/default/files/downloads/DTP300_E.pdf), dimensions/order entry and stated tolerances; retrieved 2026-10-04.
- [YAGEO Nexensos M222](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN), exact order and resistance-reference datum; retrieved 2026-10-04.

The source drawings do not qualify this assembly, the selected bond, the formed routes or an appliance seal.
