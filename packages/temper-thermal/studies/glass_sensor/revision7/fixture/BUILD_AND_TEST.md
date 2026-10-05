# Build and test sequence — physical NOT_RUN

## Preparation and assembly

1. Freeze cartridge/CAD/source hashes and specimen IDs. Inspect cap flatness, all six ears, three hooks and welds, bond/cover locations, native terminals and full lead routes. Preserve the build/lot evidence alongside these fixture records.
2. Complete the missing fixture clamp fasteners, translation guide, force-cell mounting and optical target/access details against the received instrument drawings. Design the clamp to locate the fixed housing without ovalizing its moving guide. Check force curve before/after each clamp tightening. Prototype suggested volume: three separately built cartridges and repeats per condition for exploratory variability, not process capability or lifetime inference.
3. Establish frame/glass datum and support the glass without forcing it flat through the cartridge. Assemble the dry cartridge with no pressure-cell plumbing added to a nonexistent cavity. Align the load train and verify the coupon does not touch the glass during a cap-only force sweep. The defaultØ6 coupon clears the glass hole; the separateØ36 accessory must not be used for full cap-only travel, because it lands on glass at the loaded pose and collides below that. Record the actual pan/glass contact state separately.
4. Calibrate load and displacement against independent references at the fixture, including the thermal standoff. Record instrument serials/ranges, calibration dates, force span, polarity, tare/repeatability and drift. The0.60mN and0.20µm allocations are capability targets requiring evidence. If the loop cannot resolve3mN, mark INCONCLUSIVE, not PASS.
5. Assemble cell B separately with a supplier-defined membrane and actual seals/joints only after material, pressure and temperature ratings are established. Map its fluid connectivity using low-energy leak/flow checks appropriate to the approved apparatus rating. CAD connectivity is not a leak test. Measure pressure at the cell, not only at a remote controller. Determine effective area from signed dF/dp at several positions and temperatures.

## Force/sticking sequence

Use the same installed lead route and witness assembly intended for the thermal comparison. Record independent absolute pan/carrier/island positions, both witness channels, direct force, fixture temperature, glass/body/head temperature and time. Suggested study temperatures25°C and250°C are user-requested endpoints; actual apparatus and ramp/duty must be engineered before hot use. Record intermediate thermal states; no250°C-capable apparatus has yet been selected.

At each temperature and after reassembly: approach from both directions; dwell to expose creep; unload/reload; measure zero return and sticking. Sweep only the approved travel/load envelope. R5 common0…1.2mm and local0…0.25mm are mechanical model limits, not actuator commands that may ignore a contacted stop. Fit the installed linear region independently, then report raw loops, residuals and fixture uncertainty. Retain the complete assembly and diagnostically removed-seal/removed-harness configurations with build IDs. Removing a part changes load path; keep raw comparisons rather than asserting subtraction cleanly identifies one part.

Use a repeatable pan support fixture for pan rocking: separately measure pan plane at three locations and glass clearance while applying actual cap force. The centeredØ6 force coupon is not a cookware mass/flatness surrogate. Use declared cookware and support geometry for that test. Any fixture constraint that prevents rocking invalidates a claim that the real pan remains flat.

## Contact and jam injections

Heating remains inhibited; these are bench observations, not a new production interlock.

| Injection | Independent ground truth | Record and interpretation |
|---|---|---|
| Pan lifted with island free | Pan/cap gap and direct force | Loss of force and witness state; record actual inhibition latency only if an implemented end-to-end backend exists |
| Main carrier held at loaded position | External carrier metrology | Pan removal while local island remains free; differentiate main jam from local jam |
| Local island held depressed | External island metrology plus real pan gap | Can spoof loaded position; witness alone cannot establish contact |
| Local island held released | External island metrology under loaded pan | False negative and stop/load consequences; remain inside approved loads |
| Compliant jam | Independent load/support location | Can reproduce a legitimate unload/reload trace without a pan; preserve as a blind case |
| Witness rod held; fresh frozen or command-correlated samples | Independent physical targets and recorder | Sample freshness is not physical motion; do not use replay values as ground truth |
| Insulating load-bearing debris | Coupon gap, force and thermal reference | Mechanical contact need not provide useful thermal transfer |
| Conductive sliver/bridge | Gap and independent thermal response | Optional pan-cap continuity can pass with negligible thermal coupling |
| Retract challenge | Verify0.4mm actual carrier withdrawal at carrier target | Prior challenge assumption, not proof of a designed actuator; a pan-stage command is not necessarily carrier withdrawal |

Mechanical holding devices and debris coupons are replaceable fault tooling; they are not installed seals or product features. Capture the injected geometry and force paths. Do not mark a fault “covered” without observed end-to-end inhibition and an approved latency. Mark all remaining equivalence cases explicitly; healthy-looking traces do not close them.

## Pressure, reference blockage and leak/drain work

With cell B's approved source and load fixture, sweep positive and negative differential pressure around zero, including increasing/decreasing ramps at multiple membrane positions. The analytical±25/60/120Pa points are screening points only; actual safe pressure is undefined until the fabricated cell is rated. Measure force and pressure simultaneously, and record flow/temperature histories to identify restrictions and phase delay. Meter signed top/bottom pressure if the top face is not ambient.

Establish open-reference baseline, then controlled reference restriction/blockage and recovery with an independent pressure limit/relief appropriate to the real apparatus. Blockage plus heating can produce pressure far above the small screen: do not infer a safe test from±120Pa CSV rows. The cold plenum is openly vented in nominal CAD; a sealed10mL reservoir is not an equivalent reference. Condensate, wet reference and liquid-head cases belong to a separately engineered liquid fixture, not improvised filling of this dry cell. No leak acceptance or spill drainage design is present.

A final cartridge test must repeat this with the actual complete sealed boundaries and both stage load paths. Cell B measures a specimen's installed behavior but cannot qualify an absent cartridge seal, feedthrough or drainage path.

## Retention and damage sequence

Separate cap-only retention from whole-cartridge extraction and side drag. Fixture the downstream retained island/support load path and apply load through the cap itself. **Do not pull directly on a hook toe and call that cap retention:** it can bypass the roof-to-hook attachment or alter catch engagement. D6's ears are recessed, with maximum radial envelope4.0695mm; a continuous under-ear ring can collide with the three support posts. No validated retention gripper is supplied.

Prepare a received-CAD-specific split cap grip or sacrificial top pull attachment. Section/inspect its attachment to prove it does not bridge cap-to-island parts, reinforce hooks or load the RTD/lead covers. A bonded/welded pull tab can stiffen the0.15mm roof, so report the altered load application and use multiple locations. A gripper/attachment failure is an invalid retention result, not a cap pass. Engineer this adapter and its strength after the handling load envelope is defined.

Test axial, off-axis and asymmetric single-hook-first conditions, then inspect cap flatness, cracks, hook welds, toes, ceramic upper fingers and permanent set. Record displacement through the0.20mm nominal cap lift before retention engages. Follow with reassembly and thermal calibration to catch latent damage. Required handling load, cycles and allowable permanent set are UNDEFINED;1N/2N historical model screens may be recorded as exploratory values only after approval of fixture loads, never used as qualification acceptance.

## Evidence decision

Save raw synchronized acquisition, instrument calibration, uncertainty calculations, specimen/CAD hash, photos of actual load path, environmental conditions, all failed or inconclusive runs, and operator observations. Blank templates deliberately contain no measurements. An engineering prototype can advance only when measured bounds support the declared study assumptions. No production release, lifetime or autonomous-contact assurance follows from this package.
