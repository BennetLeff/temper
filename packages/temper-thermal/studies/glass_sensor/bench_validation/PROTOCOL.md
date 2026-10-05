# Field-free cartridge bench protocol — PREPARATION / NOT_RUN

Revision bench-v1, 2026-10-04. Intended stage: controlled engineering prototype. No production or safety release is implied. This procedure does not authorize an energized induction test; that is a separate package and setup.

## Fixture and procurement preparation

Use the included existing `fixture_snapshot/adjustable-sensor-fixture.step` as a dimensional starting point: 160×140×4 mm glass-ceramic coupon with a supplier-prepared Ø18 mm aperture, adjustable three-stud carrier, Ø26 mm cartridge flange interface, frame and guard. Supplier must review aperture edge finishing and permissible glass loads. The existing frame is 6061-like metal and intended **field-free only**. The cold print feet, carrier, retainers and guides in the original BOM are not hot-test parts. Replace them with dimensionally inspected metal/ceramic parts before heating; verify differential expansion leaves the glass able to move without clamping/point loading. Adhesive tape or printed plastic must not be used as a hot load path. Do not field-energize this metal bench fixture.

Datums: A is the cleaned upper glass surface; B/C locate the carrier to the aperture without binding it. Three adjustment studs set carrier position; they are not a substitute for a guide clearance inspection. Measure free tip height from A with a bridge/depth indicator. Map pan bottom recess relative to its actual glass support points; a nominally flat coupon is insufficient. Route flex leads in a repeatable slack loop and photograph it: lead drag belongs in force/hysteresis results. Position a manual translation stage directly over the tip with a low-range force transducer and a spherical-ended nonrotating flat platen; align axis before advancing. A separate travel stop must prevent exceeding the reviewed cartridge stop force/stroke. Remove transducer/platen entirely for free-pan rocking tests, because a restrained pan cannot demonstrate freedom from rocking.

| Item | Procurement candidate or requirement | Acceptance before use |
|---|---|---|
| Low-force sensor | FUTEK LSB200 family, candidate 100 g or 250 g range, quote exact SKU with amplifier and traceable tension/compression calibration | Range must cover full measured tip force including breakaway with overload margin; combined standard uncertainty target ≤0.01 N at 0.2–0.6 N. Family choice is not a bought/calibrated instrument. |
| Force isolation | Ceramic pushrod, radiation shield, separate temperature monitor at load cell | Actual load-cell body stays in compensated range. Manufacturer standard drawing gives 15–72°C compensation and -50–93°C operation; a hot specimen does not make the load cell hot-rated. |
| Displacement | Three or four calibrated indicators/LVDTs, resolution ≤0.005 mm, range ≥2 mm; one tip and two opposed rim channels plus uniform-lift check | Combined standard uncertainty target ≤0.01 mm including glass/fixture deflection. Keep electronics outside heat zone; log actual contact forces so gauges do not stabilize a light pan. |
| Temperature reference | Fine-wire calibrated welded junction near local pan underside, plus an independent comparison probe; sacrificial metal coupon with a close blind hole permits reference placement | Measure the installed reference response and spatial bias separately. A reference glued to a remote pan point cannot resolve local probe error. No reference may sit between cap and pan. |
| Temperature logger | NI-9213 thermocouple module with compatible chassis is a candidate; actual configured noise/rate must be checked | Manufacturer rates high-speed conversion at 740 µs/channel and 75 samples/s with all channels; high-resolution mode differs. Verify actual timestamps and channel skew, do not infer rate from requested logger frequency. |
| DUT readout | Four-wire-capable calibrated resistance acquisition or production ADC with raw values and processing timestamps | Record excitation, wiring scheme, filtering and self-heating check at two currents. Production PT100 conversion/firmware version is identified. |
| Heat source | Field-free calibrated hot block/plate or guarded oven with local pan/coupon reference | Control and stop independently of DUT. Temperature limited by weakest reviewed part, wire, bond, seal, fixture and instrument. |
| Surface inspection | Flat reference, straightedge/profilometer or dial mapping, scale, shim set with actual measured thickness, magnifier | Record cookware mass, support radius, COM eccentricity proxy, local recess, roughness/finish, coating and cleanliness. |

Instrument candidates were checked against manufacturer pages on 2026-10-04: [FUTEK LSB200](https://www.futek.com/store/load-cells/s-beam-load-cells/miniature-s-beam-lsb200/pb00155), [LSB200 standard drawing](https://media.futek.com/content/futek/files/pdf/productdrawings/fsh00107.pdf), [NI-9213 datasheet](https://download.ni.com/support/manuals/374916a_02.pdf). These are procurement leads; certificate, exact range, stock and fixture compatibility remain to confirm. [NIST thermocouple calibration](https://www.nist.gov/pml/sensor-science/temperature-humidity/thermocouples-calibrations-services) supports separating reference calibration from the installed measurement's added errors.

## Assembly and metrology checks

1. Record cartridge revision, purchased part IDs/lots, cap mass/roof dimensions, actual spring and seal, bond cure schedule, bond-line spacers/thickness, guide diameters, stroke limits and lead route. Photograph each assembly and the contact surface; assign serial numbers. At least three independently assembled cartridges are a learning pilot, not proof of production capability.
2. Inspect glass edges/aperture, frame flatness and support strips. Check free motion across intended stroke without a pan, then with wiring and seal installed. Measure before and after each reassembly. Inspect guide scoring or cap distortion.
3. Zero indicators against A with cartridge absent. Record complete readings with probe retracted and representative pan present, so original pan warpage is not attributed to the probe. Establish all four edge heights and uniform lift. Tare force with lead loop installed and vertical orientation fixed.
4. Check load cell at zero and 0.2/0.4/0.6 N equivalents in both directions using traceable standards. Record local gravity if masses are used; do not silently call 1 g exactly 0.01 N. Verify displacement with independently measured shims. Log pre/post drift; exceeding budget invalidates the affected batch.
5. Verify the reference/readout in at least three reviewed temperature points spanning the run range, with certificates and installed attachment checks. Quantify reference lag with a faster reference in the same field-free event. Synchronize clocks by a common trigger observed in both streams; measure skew, filtering and multiplex delay. A screenshot or manually entered temperature is not a transient reference.

## Acquisition settings and mechanical runs

Target ≥100 samples/s for force/travel/bounce, ≥20 samples/s per thermal channel for ~3 second response, and event timestamps from the same clock. These are planning targets; qualify actual effective bandwidth and noise. Preserve native raw files. Set metadata `max_gap_s` to a predeclared budget tied to the verified configuration. Mark dropouts/invalid channels; never interpolate them into a passing acquisition.

At each approved temperature, equilibrate until all relevant monitored parts are stable and record ≥60 seconds. Perform ten slow load/unload cycles across usable stroke, then ten release cycles; save **one** cycle per mechanics CSV with preload → load → unload → release phases in that order. Use a manual or controlled stage at 0.1 mm/s for quasi-static force, with denser sampling near breakaway and stop. Do not force beyond the supplier/reviewed stop. Capture release for at least 2 seconds. Repeat after lateral perturbation representative of pan placement and after 90° rotation; measure actual lateral displacement/force rather than an unrecorded shove. Extract hysteresis at common stroke, breakaway peak, available return force margin, residual displacement, and return time. The current reducer reports force/curve envelope; slope/preload/friction should be reviewed from the raw curves before replacing model assumptions.

Free-pan test: remove loading hardware. Test actual pan empty and at intended minimum contents, centred and at measured offsets. Alternate small **measured** downward forces near opposite edges without restraining the pan. Log opposed-edge heights and uniform lift; compare against cartridge retracted baseline and glass motion. A force screen of 0.2/0.4/0.6 N is an experiment, not acceptance. Freeze allowable added tilt/lift against cooking and coil-gap requirements before claiming a pass. For interim characterization, report millimetres and uncertainty, never simply 'no rocking'.

## Predeclared initial matrix

All entries are **NOT_RUN**. The matrix bounds a learning experiment and cannot establish the entire cookware population.

| Axis | Prepared points |
|---|---|
| Cartridge | 3 independent builds, each before/after reassembly; label part and bond lots |
| Local recess relative glass support | measured 0, 0.35, 0.6 mm plus unreachable 0.9 mm negative control; -0.2 mm dimple coupon only after interference/stop review |
| Free height | measured 0.45, 0.60, 0.75 mm setup points within verified stop budget |
| Total force | measured 0.2, 0.4, 0.6 N trials, and lower-force corner of selected part tolerances |
| Cookware | thin carbon steel, cast iron, induction-compatible clad/aluminium-core; actual smallest supported pan and largest intended pan |
| Mass/COM | 0.15/0.30/0.60/1.0 kg study range as fixture weights/cookware where physically representative; include user's actual minimum permitted pan; COM offset 0/30/60 mm only while inside actual support polygon |
| Surface | clean dry baseline, controlled oil film, representative surface roughness/coating; record applied amount and cleaning method |
| Temperature | ambient then 40/80/100/150/200°C **only when every part and seal hotspot is approved for it**; 250°C is blocked for the current seal concept |
| Excitation | ≥20°C field-free placement steps; 0.5/2/5°C/s measured ramps; cooling/recontact runs |

Avoid immediately multiplying every axis. First establish free return and bounded force at ambient on all builds, then thermal response on the minimum-mass/recess extremes with clean surfaces. Carry every failure corner into repeat tests and lower the intended envelope if necessary. Separate different pan conditions rather than averaging their errors. Recess ≥free height is an explicit no-contact case; the correct outcome is detection and inhibition, not fabricated temperature accuracy.

## Thermal step, ramps and holdout

Mount local reference in a sacrificial coupon/pan near the cap's contact area without putting it in the contact sandwich. Record cap-adjacent and several annular references to bound gradients; an optical check should use independently established emissivity/spot size. The controlled step is lowering an independently heated pan/coupon onto the cold cap at known contact time and load. It may not be an ideal imposed-temperature step: record the local reference transition and cooling. If transition+reference lag exceeds 0.3 seconds, report effective response to that measured input and withhold the 3 second step pass. A two-block reference step or thinner coupon may improve the input only after representativeness review.

Record baseline ≥5 seconds, event, response, and stable final plateau ≥60 seconds; ≥120 seconds total is a starting setting, extend until the system actually stabilizes. Separately run rising and falling ramps at measured 0.5/2/5°C/s. Record peak sensor-minus-reference error and cooling positive error; the basic CLI is for steps/plateaus and effective fitting, so ramps require reviewing residual traces and timing before making a phase-delay claim. Reposition pan between repeats; reserve complete new acquisitions as holdout before fitting.

Thermal continuity tests with deliberate physical contact loss belong in separate files; importer intentionally rejects using disconnected intervals for contact calibration. Hold the pan at a plateau, create a controlled gap without changing temperature significantly, and record independent gap/contact evidence. A healthy hot PT100 can remain hot while disconnected. This procedure can characterize detector observability later but is not executed here.

## Human completion and disposition

Needed after this preparation: review fixture/material limits, procure or identify calibrated instruments, manufacture/inspect cartridges, freeze actual cookware/temperature requirements and guardbands, acquire signed raw data and certificates, run the reducer, inspect residuals, update model envelopes, then rerun the study and separately evaluate energized induction behavior. Responsible roles: mechanical owner for force/stroke/glass loads, metrology owner for reference/uncertainty, thermal owner for model transfer, controls owner for interlock integration. No electrical operation is initiated by this package. Physical result tables and certificates remain empty until those steps happen.
