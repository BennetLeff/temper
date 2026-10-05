# C9-BOLTED: separate dry prototype geometry

This M222 0.100 mm control derivative replaces the three unanchored ceramic capture fingers with three independent **316L catch brackets, each held by an M1.6 screw and nut**. It supplies an explicit positive attachment concept without relying on adhesive tensile strength. R7 remains unchanged. This is nominal CAD and assembly-access evidence, **not retention strength, hot preload, sealing or thermal/induction qualification**. Physical NOT_RUN. Reviewed 2026-10-05.

## What changed

Each bracket preserves the inherited upper-catch lip location and the nominal 0.10 mm island clearance. Its outward foot spans local r = 4.05…8.80 mm, width 3.40 mm and thickness 0.30 mm at z = −8.00…−7.70 mm. The proposed Ø1.80 mm clearance hole and bolt axis are at r = 7.10 mm, angles 60/180/300°. These are experimental design dimensions, not supplier tolerances.

The carrier receives three through-holes plus three radial insertion passages. Each lower foot passage spans local x = 4.00…5.80 mm, y = ±1.80 mm and z = −8.00…−7.60 mm; a narrower upright passage spans x = 4.40…5.60, y = ±0.50 and z = −7.60…−5.50 mm. A foot-only passage was tested and fails: its carrier intersection during a 1 mm radial offset is **0.615372 mm³**. The narrow upper opening is therefore an assembly requirement. An earlier lower pocket beginning at x = 4.40 also intersected the foot's corners by 0.00025946 mm³; extending the pocket to x = 4.00 removes the real round-ring corner clash without changing the collision tolerance.

The r = 7.10 axis keeps the Ø3 mm screw head radially clear of the r = 5.40 carrier ring by 0.20 mm nominally. Head top is z = −6.10 mm at rest and −5.70 mm after the carrier rises 0.40 mm; the housing underside remains z = −5.30 mm. No washer or locking compound is silently added.

## Exact nominal fastener references

| Reference | Primary dimensions used | Limit of evidence |
| :-- | :-- | :-- |
| [Accu SSCF-M1.6-4-A4](https://www.accu.co.uk/metric-cap-head-screws/3942-SSCF-M1-6-4-A4), Technical Specification, retrieved 2026-10-05 | Natural A4, full-thread M1.6 × 4, pitch 0.35 mm; head Ø3 and height 1.6 mm, both +0/−0.14; socket 1.5 mm, depth 0.7 mm | Supplier geometry reference. No hot joint allowable, torque, availability or locking qualification claimed |
| [Accu HPN-M1.6-A4](https://www.accu.co.uk/hexagon-nuts/7901-HPN-M1-6-A4), Technical Specification, retrieved 2026-10-05 | Natural A4, DIN 934, M1.6 × 0.35; across flats 3.2 +0/−0.18 mm; height 1.3 +0/−0.25 mm | Exact natural finish reference; no black finish or pre-applied threadlocker substitution |

The CAD uses nominal external envelopes, a Ø1.6 cylindrical shaft/bore mating representation and the actual nominal socket. **Helical thread flanks are not modeled.** Load transfer between screw and nut relies on the explicitly specified matching threaded components; it is not a B-rep proof of thread engagement strength. Nominal nut engagement length is 1.3 mm and nominal screw projection below the nut is 1.4 mm. Lead-in chamfers, root radii, thread tolerance class, manufacturing variation and preload remain unresolved.

## Evidence and assembly scope

`bolted-candidate-checks.json` records the full modified M222 assembly at rest, combined cap/island capture and housing capture. All non-seal solids and all modeled electrical joins are checked. Three STEP assemblies are reimported, and both the new head/nut bearing interfaces and the retained cap/island/carrier/housing interfaces are checked on the imported B-reps.

Each loaded bracket has 0.594659 mm² island bearing, **4.523893 mm² foot-to-head bearing**, and **6.323410 mm² nut-to-carrier bearing**. The nut footprint crosses two coplanar carrier face fragments; the audit sums their areas for each joint rather than counting CAD face fragments as separate joints. These areas describe geometry only.

The assembly study assumes the inherited moving sensor module is already present in an open carrier. Install brackets radially through the new passages, add screws from above and nuts below, then lower the housing; glass/seals remain absent during this open-bench operation. Eighteen bracket positions include the other two installed brackets and their fasteners; six housing positions are checked. Conservative straight screw insertion and rotating-nut swept envelopes also pass, with a minimum 1.5 mm hex-key shaft envelope. A selected wrench/driver handle, full torque stroke and the inherited sensor-module assembly sequence have not been qualified.

This closes the **missing positive-attachment geometry concept** in a separate candidate. It does not qualify the reduced carrier section, sharp bracket roots, ceramic bearing/preload, fastener loosening, carrier material, unequal hook loads, lateral escape or mounting strength. Three metal brackets and six fasteners change conduction, thermal mass and induction coupling: **no R7 thermal result applies to the exact candidate without a new export/model**.

Run `sh run_candidate.sh`, then `shasum -a 256 -c candidate-artifacts.sha256`. Its receipt is separate from the unchanged eight-STEP baseline/witness receipt. No canonical CAD is replaced.
