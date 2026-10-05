# R8 seal and contact build-readiness packet

Status: **SIMULATION AND TEST PREPARATION ONLY. All physical measurements: NOT_RUN. Supplier requirement draft: NOT_SENT.** Prepared 2026-10-04. No supplier was contacted; no material, detector or sealed cartridge is qualified. This packet adds a supplier feasibility decision, complete boundary requirements and discriminating experiments to R7. It does not change production code or CAD.

## Decision to take next

Take a **single continuous fixed-housing-to-island barrier** to the first feasibility review, alongside a complete two-boundary alternative. The single boundary minimizes sealed joints and makes its force path explicit; its 1.45 mm endpoint envelope and extremely small permissible reaction may make it impractical. Do not attach the barrier to the freely captured cap by default: that adds the separate 0.20 mm retention motion and can make the seal carry the retention load. Attachment to the island still requires a demonstrated continuous wet boundary around the cap/island interface; that interface is currently unresolved.

The first decision is whether an actual supplier geometry can satisfy the **installed hot cyclic force curves**, not which compound has the largest temperature number. Keep custom Kalrez 6375 as the inherited elastomer reference, compare 7375 for wet exposure, and retain a custom edge-welded metal barrier as the material-independent alternative. A rolling diaphragm is conditional on demonstrated shape stability at zero and reversing pressure. None is ready to replace the R7 dry cartridge.

If both single and two-boundary candidates fail the complete force budget, stop that architecture and revisit the mechanical/contact-sensing arrangement. Increasing optical debounce or silently reallocating the 10 mN cannot fix an unobservable mechanical load. Moving the seal into a nominally cool region is only an alternative after proving its worst-case local temperature; the thermal model's assumed body temperature is not that proof.

## What the public supplier evidence actually establishes

| Candidate | Primary evidence and its scope | Disposition and missing evidence |
| :-- | :-- | :-- |
| Custom Kalrez 6375 diaphragm | The compound sheet gives 275°C maximum service temperature, explicitly dependent on seal design/application. Its 70-hour compression-set data at 204°C concern pellets/O-rings, not a flexing diaphragm. | Retain as an exact compound candidate, with no selected finished part. Require 250°C cyclic force, pressure reversal, attachment and wet-aging data for the proposed geometry. [Manufacturer sheet](https://www.dupont.com/content/dam/electronics/amer/us/en/kalrez/public/documents/en/KZE-H82112-00-F0719_Kalrez_Spectrum_6375.pdf). |
| Custom Kalrez 7375 comparison | Qnity lists 300°C maximum application temperature, hot-water/steam seal-force-retention applications and O-ring compression-set results including 70 hours at 260°C. | Wet-exposure comparison, not a qualified replacement or evidence of lower diaphragm force. No public miniature moving-seal force/stroke/life curve establishes this application. [Manufacturer page](https://www.qnityelectronics.com/products/kalrez-7375.html). |
| Bellofram reinforced rolling diaphragm | Its manual lists silicone code B to 315°C, but explicitly identifies these as stationary temperatures. Food-grade silicone code C ends at 232°C. Pressure reversal can create damaging pleats that do not recover on repressurization. Its general low-friction description supplies no millinewton bound. | Consider only a supplier-designed convolution with exact reinforcement, cure and attachments. Request zero-pressure stability and both pressure signs; a positive-pressure pneumatic design is not sufficient. No part is selected. [Design manual, printed pp. 22, 29](https://damapi.marshbellofram.com/uploads/design_manual_3e8071e17a.pdf). |
| Custom Senior edge-welded metal barrier | The manufacturer describes stainless, nickel-alloy and titanium construction, with spring rate dependent on geometry/material/thickness and life dependent on stroke, pressure and fatigue. It advises primarily compression and avoiding lateral offset during axial motion. Broad temperature capability is not a rating for a selected miniature assembly. | A valid custom feasibility branch. Require spring/reaction curves, effective area, joints, thermal conductance and induction response. No exact part, weld schedule, 250°C life or acceptable reaction is established. [Manufacturer design guide](https://www.metalbellows.com/bellows-101/). |
| Servometer catalog flexible bellows, including standard FC-1 | The catalog's bellows environmental table ends at +350°F, approximately 177°C. FC-1 lists 5.90 lbf/in spring rate, equivalent to 1.033 N/mm: approximately 258 mN for 0.25 mm compression before preload/pressure. The catalog's separate static electroforms have a different temperature scope. | Reject **FC-1 as a direct 250°C moving-seal candidate**: both the published temperature scope and nominal spring reaction fail this screen. This does not reject all custom metal bellows or other manufacturers' alloys. [MW/Servometer catalog, printed pp. 4, 11, 13](https://info.mwcomponents.com/hubfs/PDFs/MW-COMPONENTS/MWC-Catalogs%20and%20Brochures/MWC%20Catalogs/Servometer-Metal-Bellows-Catalog.pdf). |

These are manufacturer publications, not endurance results for Temper. No Shore hardness or 100%-strain modulus has been converted into small-deflection seal stiffness. A change of metal also adds a heat-conduction and induction-heating question; it cannot inherit the dry cartridge's thermal result.

## Coupled movement and force accounting

Reference coordinates: fixed housing `H`; main carrier `C`; local sensing island `I`; captured contact cap `K`. Common travel is `H→C = 1.20 mm`; local travel is `C→I = 0.25 mm`; cap capture is a separate `I→K = +0.20 mm` condition. The island-to-carrier upward catch has a separate +0.10 mm cold nominal take-up. Challenge cap-to-island +0.20 mm and island-to-carrier +0.10 mm independently, then together. Approximately +0.30 mm sequential take-up is a rigid, fixed-carrier illustration, not a validated operating stroke; the combined pose is not checked by R7. The sum 1.45 mm is an endpoint envelope, not proof that both downward maxima occur under a flat pan.

| Architecture | Barrier attachment and movement | What must be included in the decision |
| :-- | :-- | :-- |
| Single boundary | H→I, up to 1.45 mm endpoint travel | Pressure, preload, spring reaction and hysteresis act through the island. Show how the wet boundary remains continuous during cap capture without making the membrane retain the cap. This is the first feasibility sketch, not finished geometry. |
| Two boundaries | H→C outer barrier: 1.20 mm; C→I inner barrier: 0.25 mm | Include both effective areas, their pressure references, both force curves and coupled spring equilibrium. The outer reaction can change pan force and main-stage position even when it is outside the local detector. The inner reaction remains directly relevant to local evidence. Scoring only the 0.25 mm membrane is incomplete. |
| Barrier attached to cap | H→K or C→K | Resolve normal movement and independent +0.20 mm capture states, including trapped liquid and peeling. Do not automatically add all displacement maxima into a claimed operating stroke. Reject any design that relies on the seal for positive cap retention. |
| Relocated cooler barrier | Actual selected attachment, with longer mechanical/thermal path | Requires a temperature bound under hot soak, blocked cooling/reference, spill, fault and induction. Add rods, joints, harness route and their reactions. A cooler nominal CAD location is not sufficient. |

The inherited R5 development allocations are **3 mN pressure + 3 mN seal hysteresis + 4 mN complete harness/witness = 10 mN total local parasitics**. The 4 mN covers all leads and both witnesses together, not each lead or rod. R6 shows that additional seal elastic reaction/preload must fit inside the same remaining total:

`B_available_elastic = 10 − B_pressure − B_hysteresis − B_harness`, all in mN.

At all three allocation maxima, **zero elastic margin remains**. At zero pressure, holding 3 mN hysteresis and 4 mN harness leaves at most 3 mN: a linear, zero-preload screen gives `k ≤ 0.012 N/mm` over 0.25 mm or `k ≤ 0.00207 N/mm` over 1.45 mm. These are optimistic analytical upper bounds, not selected spring specifications. Installation preload, thermal drift and aging consume them too. A measured reduction in another term may create room; no reduction is assumed here.

Use absolute uncertainty-bounded reactions; do not rely on pressure opposing friction in one sweep. A known spring contribution already included in the installed 1.6–2.4 N/mm local-slope model is not charged again, but an unmeasured seal cannot be fitted away as “spring.” Record pressure, rate dependence, preload and forward/reverse branches separately before evaluating the complete assembly.

For each pressure boundary, measure `A_eff = ∂F/∂Δp` through movement and temperature. An 8 mm physical hole or 6 mm cap does not establish effective area. The 3 mN pressure allocation implies the following ideal limits, before instrument/area guardbands:

| Hypothetical effective diameter | 6 mm | 8 mm | 10 mm | 12 mm |
| :-- | --: | --: | --: | --: |
| Maximum absolute differential pressure | 106.10 Pa | 59.68 Pa | 38.20 Pa | 26.53 Pa |

R7's proposed 2.2 Pa pressure bound and hypothetical 8.00±0.05 mm effective diameter reduce the permitted observed magnitude to **56.744 Pa**. This is a metrology example, not measured capability or a certified area. A 6.08 mm water head consumes the ideal 3 mN at 8 mm; an open dry reference does not cancel liquid pressure on the wet face.

Do not grant a second 10 mN to the common stage. Its permissible reaction must be obtained from the pan-contact force, flatness/rocking and two-stage equilibrium requirements. That complete main-stage force allocation is **not established** by the local detector budget and is a required architecture input.

## Complete boundary: required drawing before sealed build

The R7 cartridge is dry and unsealed; Station B is a separate membrane test cell. Its connected ports do not create a pressure connection in the cartridge. A proposed sealed drawing must identify every one of these paths:

| Path | Required construction/evidence, currently unresolved |
| :-- | :-- |
| Glass aperture → fixed housing | Static seal lands, compression stops, radial clearance, glass stress and expansion; demonstrate liquid cannot bypass the cartridge exterior. The existing mount is not a sealed mounting detail. |
| Fixed housing → carrier/island → exposed cap | Continuous primary barrier and sealed attachments for every moving body, including capture states. Show cap/island leakage paths, trapped cavities and direction of every membrane reaction. Cap retention remains structural and separately tested. |
| Four RTD leads | A stationary feedthrough concept with individually sealed conductors and strain relief; stop leakage/wicking along insulation and conductor interstices. Preserve the complete 60 mm lead routes in the force/thermal comparison. Potting around an unqualified sheath is not a hermetic feedthrough claim. |
| Carrier and island optical witnesses | Prefer rods entirely inside the dry enclosure with optics behind a stationary window or inside a proven cool dry volume. Any penetrating moving rod introduces another seal and reaction. Both rods remain in the combined harness/witness budget. Window seals, condensation, alignment and actual component-temperature limits require evidence. |
| Dry pressure reference | Connected chamber, tubing, bends, vent/filter, cold plenum and open termination, all with dimensions and contamination behavior. Pressure reference and liquid drainage are different functions. Avoid routing the dry vent through a sump that can fill and block it. |
| Secondary drainage | A gravity path that routes bypass/primary-seal leakage away from electronics, with spill, tilt, blockage and cleaning access checks. Specify what event inhibits operation when drainage/reference fails. An unmonitored blockage cannot be assumed detected by mechanical-channel agreement. |
| Housing joints/service split | Static seals, fasteners, compression limits, datums and reassembly inspection. Supply lot/cure traceability, surface finish, burr limits and seal replacement rules. None is qualified by an interference-free STEP. |

R5's reference concept used a 1.5 mm-ID, 100 mm tube and open 10 mL cold plenum; its analytical 10 K/s plus 20 mm/s case produced approximately 25.08 Pa before downstream restrictions. R7 Station B instead has a 120 mm center-to-center connected path and total modeled plenum/ports of 11.293915 mL. Its pressure response must be measured or recalculated using that actual geometry. Closing the reference is not equivalent: R5's sealed-plenum hot case produces approximately 207 mN. A blocked-reference fault therefore needs an inhibition strategy independent of merely promising a clean vent.

## Supplier geometry and force requirements draft — NOT_SENT

Request a feasibility response for **complete assemblies**, with separate single-boundary and two-boundary sketches. Attach the final R7 STEP snapshots and source hashes when this draft is transmitted; do not substitute a rendered screenshot for geometry. This packet does not authorize outreach.

1. **Envelope and interfaces:** glass top datum z=0, 4 mm glass, nominal Ø18 mm aperture; fixed housing Ø28 mm lower body and Ø17 mm upper neck with Ø15.4 mm bore. These are reference interfaces, not available seal-land dimensions. Supplier must mark proposed static/moving attachment lands, compression stops, required envelope changes and assembly access. Include retained-cap and complete lead/witness swept envelopes.
2. **Movement:** provide H→I full endpoint envelope or both H→C and C→I curves, in compression/extension and every separate capture/service state. State allowable lateral offset, tilt, rotation and minimum convolution clearance, then compare with an actual tolerance stack. Unspecified manufacturing offsets are not zero.
3. **Reaction:** report absolute installed force versus displacement for both directions, at actual seal temperatures 25/100/200/250°C, near-zero and both signs of pressure, initial and aged/reassembled. Include preload, relaxation, rate effects, breakaway, uncertainty, part variation and raw curves. Requested 0.1/2/20 mm/s rates are exploratory screening points, not established service limits. Demonstrate the complete 10 mN local budget and separately supply common-stage reactions; do not respond only with nominal spring rate.
4. **Pressure:** propose and then measure effective area versus position/temperature; provide collapse/eversion and proof limits for both signs. Low-pressure screening is ±25/50/60/100/200 Pa, including reversals through zero. These are test points, not operating or survival ratings. Blocked-hot reference pressure is a separate fault envelope; R5's fully trapped-gas screen reaches approximately 76.5 kPa. It must not be applied to unproved fixture hardware. State a pressure-survival design or independent pre-limit inhibit/relief requirement.
5. **Temperature/media:** 250°C compatibility is required; continuous dwell, excursion temperature/duration, life cycles and allowable drift are still **UNDEFINED**. Provide qualified material, reinforcement, joining process and media limitations; separate hot dry exposure from transient water/steam, oils, salts and the eventual approved cleaning chemistry. No general food-contact claim is inherited from a material name.
6. **Life and inspection:** quote feasibility evidence at explicit temperature, pressure, stroke and rate combinations. Request raw cycle count, failures/censoring, sample count, lot variation, permanent set, leak method/detection limit and pre/post force curves. Product life, permissible leakage and proof load require owner-approved requirements before qualification. Supplier family marketing and O-ring compression-set tests are insufficient.
7. **Thermal/electrical integration:** supply material thickness/tolerance, conductivity, mass, wetted geometry, joining heat exposure and electrical path. Identify metallic loops or magnetic materials for induction review; report uncertainty instead of assuming zero added heat leak/self-heating.

The [Senior design data sheet](https://www.metalbellows.com/assets/Bellows-Design-Data-Sheet-Submit.pdf) is a useful request-field checklist. The required Temper force curves and full two-stage boundary are additional application-specific evidence, not information already supplied by that form.

## Bench matrix: measure discriminators before endurance

Use Station A for independent cartridge force/displacement and Station B for seal pressure/force. Combine them only after a connected sealed cartridge has a reviewed drawing. R7's Ø6 force coupon is appropriate for stroke characterization; a wide flat pan landing on the glass is a separate rocking/contact test and cannot be driven through the same full-stroke path.

The proposed initial screen uses three specimens and three independent assemblies per candidate, ten forward/reverse cycles per condition. These are exploratory repeatability choices, **not a reliability demonstration or qualification sample plan**. Perform diagnostic screens first; expand only candidates that remain observable and within guarded budgets. Hardware execution requires selected instruments and a reviewed procedure; nothing below has run.

| Test block | Conditions and independent measurements | Decision / evidence retained |
| :-- | :-- | :-- |
| A: dry reference | 25°C, complete leads/witnesses, seal absent; common-only, local-only and coupled sweeps. Independent force and displacement, specimen temperature and fixture tare. | Establish base spring curves and residuals without fitting later seal forces into the baseline. Record actual no-contact cap gap. |
| B: hot dry seal | 25/100/200/250°C measured at the seal, both directions, 0.1/2/20 mm/s; common/local endpoints and zero-pressure dwell/relaxation. | Guard combined parasitics ≤10 mN and local slope 1.6–2.4 N/mm under their development assumptions. Record any hysteresis, stiction, buckling and loss of return. Body setpoint is not seal temperature. |
| C: signed pressure | At each intended normal pose and temperature: 0, ±25, ±50, ±60, ±100, ±200 Pa, approached from both signs. Record independent Δp, force and relative position. | Measure effective area, zero crossing, shape recovery and pressure-induced false contact. Exceeding a development allocation is a failure datum, not a revised limit. Stop before a supplier/fixture proof limit. |
| D: open / restricted / blocked reference | Open path, measured restrictions, condensate trap, then bounded blockage fault using reviewed pressure hardware. Include heating and cooling transients. | Determine actual chamber pressure and whether the contact classification can remain falsely loaded. Full hot blockage is not authorized by a low-pressure cell check. Verify inhibition before any specified unsafe pressure/load limit. |
| E: wet face / cleaning | Ambient water head 0/3/6/10 mm with actual fluid temperature; separate controlled hot-surface spill/evaporation at 100/200/250°C initial cap temperature. Oils/cleaner tests await named chemistry. | Record both sides' pressure, actual cooling/steam transient, leak location, drain flow and force classification. Water is not assumed to remain a 250°C ambient-pressure liquid layer. Compare before/after drying; residue can create a later jam. |
| F: mechanical faults | Jam carrier depressed and released; separately jam island, either witness and cap; repeat after valid acquisition. Add side load, guide/seal debris, pan lift/tilt and insulating contamination. | Independent external load and gap must identify true release. Preserve raw channels when they falsely agree. A hot/cold pass with a freely sliding stem is insufficient. |
| G: retention / service | Separate cap-to-island +0.20 mm and island-to-carrier +0.10 mm capture states, then the combined sequential challenge; actual pull through cap and downstream hooks/support; seals present and absent, post-reassembly. | Pull load, cycles and permanent-set limit remain UNDEFINED. Do not perform a claimed proof test at inherited 1 N/2 N screens. Qualify the grip first: pulling hook toes can bypass the roof/attachment failure path. |
| H: aged repeat | Repeat A–G after an owner-defined thermal/wet/cycle duty and replacement/service sequence. | NOT_READY until duty, life and leakage criteria exist. Record first failure, interrupted samples and survivors; no “zero failures” claim from unrun or censored tests. |

The R7 proposed force uncertainty is 0.60 mN per reading. Two readings plus 2 µm position mismatch at 2.4 N/mm yield **6.0 mN** possible ambiguity, too large to resolve 3 mN seal hysteresis. Its proposed 0.2 µm matched-position capability reduces this to **1.68 mN**, leaving at most **1.32 mN measured loop** to guard a 3 mN limit. Actual instrument selection/calibration and in-situ drift must establish those bounds. The production optical 15 µm error assumption cannot serve as hysteresis metrology.

Report complete-assembly residuals once: they already include seal, pressure and harness. Use component tests to attribute failures; do not add those components a second time to an already inclusive measured residual. Keep raw forward/reverse data, pressures, sample timestamps, reference force, actual gap, temperatures, specimen/assembly identity and instrument calibration identifiers.

## Contact observability: what can still fool the proposed detector

Two mechanical channels are independent only against the fault paths they do not share. R5's local island and carrier witnesses improve on a lower spring-seat force reading, but their agreement alone is not an independent observation of pan-to-cap heat transfer.

| Counterexample | Why apparently consistent evidence can survive | Discriminating evidence required |
| :-- | :-- | :-- |
| Stem jams after acquisition; pan lifts | Spring compression and carrier position can remain loaded. Startup release proof has already passed. | Independent external cap load/gap during pan removal, with induction presence held true. Local force sensing must exclude guide/seal/stop reaction paths. |
| Seal pressure or drag holds island | Both mechanical coordinates may look like pan load; restriction can worsen with temperature or condensate. | Independently measured signed pressure, local force and true cap gap; a qualified fault response to reference loss. |
| Compliant jam follows commanded motion | A carrier-retraction challenge can produce correlated witness changes without pan contact. Commanded stage movement is not an independent observable. | Measure actual external geometry/load. R5's inhibited 0.4 mm retraction remains a bench challenge, not proof against every compliant jam. |
| Insulating debris supports the pan | Real mechanical force exists but cap-to-pan thermal conductance is poor. | Reference pan temperature plus transient response and known contamination; reject a claim of thermal contact if accepted and unacceptable populations overlap. |
| Electrical continuity bridge | Conductive liquid, a metal sliver or a wiring short can mimic contact with negligible useful thermal conductance; coatings can break continuity during real contact. | The optional R5 cap-to-pan AC test remains an unpowered bench discriminator, not a product fallback. |
| Thermal pulse into an alternate sink | Wet glass, probe body or debris can absorb heat resembling a pan response. | Bound parasitic thermal paths and use an independent pan reference in the discriminating experiment. Temperature dynamics alone cannot establish the identity of the sink. |
| Common timestamp/frontend fault | Fresh-looking duplicated evidence or shared supply/ADC/processor failure can sustain LOADED. | Fault injection at the acquisition source, independent reference capture, electrical diagnostics and timestamp integrity. Two derived values from one cached sample are not two fresh observations. |

Useful new work is the **classification dataset and load-path redesign decision**, not another debounce layer. Capture raw channels for actual release, clean loaded contact, hot pressure faults and each jam/contamination case. Predeclare uncertainty-expanded valid intervals and evaluate them on held-out specimens/assemblies under the root calibration protocol. If a no-contact fault overlaps the loaded interval, keep the backend unavailable; do not select thresholds from the nominal clean curve. Mechanical contact and acceptable thermal coupling need separately stated claims.

## Existing inhibition interface versus missing hardware

The code already fails closed without a physical backend. `firmware/main/main.c` leaves contact unavailable and schedules the control task at 10 ms. A future passive driver belongs immediately before `state_machine_update()` in that task. `contact_guard_submit()` consumes a classified enum and acquisition timestamp; it does not inspect raw mechanics or prove that LOADED means cap contact.

The current guard requires 100 ms continuous RELEASED evidence, followed by 100 ms LOADED acquisition, with accepted sample gaps strictly below 50 ms. Stale/future/reversed/conflicting timestamps or diagnostics invalidate it. Identical timestamp replay cannot refresh freshness. Active PAN_DET, PREHEAT and HEATING entry and update paths are gated; PAN_DET's 5% excitation is included. Contact loss invokes the hardware-cut path before further positive commands, sets the contact fault and cancels queued transitions. Recovery does not automatically resume cooking.

Existing `contact_detection/status.json` records 18 focused host tests, 300 loss/timing combinations, 14 registered CTest suites, 23/23 designed SIL fault/state pairs and a gate-removal mutation check. **Those are inherited software evidence, inspected here, not new R8 test runs.** The dedicated contact target uses the real guard; some broader suites mock contact as valid. The recorded all-target build has a separate pre-existing `test_profiles.c` compile failure. No hardware waveform, physical detector, ESP-IDF target build or sealed-cartridge result follows from these host tests.

| Useful work possible before hardware | Input still unavailable; cannot be closed by software |
| :-- | :-- |
| Define raw-channel/timestamp/diagnostic schema and one control-task publisher; map every acquisition failure to unavailable/fault. | Qualified sensor hardware, independent observable and actual signal/noise/drift envelope. |
| Trace each physical counterexample to a recorded test and expected guard transition; replay future measured traces through the existing guard. | Evidence that raw signals discriminate that physical counterexample. Synthetic separation is not qualification. |
| Budget acquisition, scheduler and actuator timing; prepare a common-clock capture of pan gap, raw sample, classification, fault command and physical gates. | Maximum permissible heat-after-loss and measured worst-case physical cut time. |
| Specify boot-with-pan/release interaction and explicit recovery using the existing latch policy. | Whether passive acquisition and release are possible for actual cookware and mechanism without excitation. |
| Define diagnostic coverage for blocked reference, frozen producer, shared supply and control-task stall. | Chosen pressure/reference observable, sensor independence and verified hardware latch/watchdog behavior. |

The nominal task schedule gives a software missing-sample decision before 60 ms after the last valid sample when execution remains on schedule; **it is not a physical loss-to-cut bound**. The complete chain is: actual contact loss → sensor/diagnostic latency → acquisition timestamp → control-task classification/guard → state-machine fault → power/PWM/PLL and hardware-cut commands → observed gate/energy cessation. Add jitter and test task stalls. A producer that renews timestamps on cached values breaks the chain before the guard can help.

## Criteria authority and stop decisions

| Criterion | Authority / current status | Required closure |
| :-- | :-- | :-- |
| 250°C-compatible seal | User requirement; exact dwell/excursion/life undefined | Named geometry/material/process plus hot dry/wet cyclic evidence at an agreed duty. Compound rating alone cannot close it. |
| Pressure 3 mN, hysteresis 3 mN, harness/witness 4 mN, total 10 mN | R5 development allocation; R6 complete-force screen; not a standard or measurement | Guarded installed measurements, no duplicate allocations, explicit remaining elastic margin. |
| Local slope 1.6–2.4 N/mm, minimum contact force 0.12 N, optical error 15 µm | R5 model assumptions | Hot/cold, tolerance and reassembly data supporting separation of actual contact/non-contact distributions. |
| Release/acquire 100 ms; sample age <50 ms | Existing firmware engineering budgets | Verify scheduling and source timing; derive physical cut acceptance from hazard/thermal-energy requirements. |
| Leakage, cleaning chemistry, service life, retention proof load/cycles and permitted permanent set | UNDEFINED | Product/mechanical owner must set measurable requirements before a qualification run. Historical screening numbers are not their authority. |
| End-to-end contact-fault inhibition | Required behavior, maximum physical latency UNDEFINED | Simultaneous independent loss reference and physical gate/energy capture under hot, wet, jam, CPU-load and later induction conditions. |

Stop advancement of a sealed cooking cartridge if: no complete boundary drawing exists; the supplier cannot provide a plausible force curve with positive uncertainty margin; pressure reversal or capture changes the seal state unpredictably; effective-area/reference behavior exceeds the force envelope without an independent inhibit; the measurement system cannot resolve the allowance; or any tested no-contact fault can still produce accepted loaded evidence. A boundary-temperature relocation is stopped until its worst-case temperature is established. Retention and endurance qualification are stopped while their acceptance values are undefined.

The next reviewable deliverable is a supplier-ready comparison drawing and returned feasibility curves, followed by isolated seal-cell measurements and then a complete sealed cartridge trial. Until those exist, R7 remains the reproducible **dry** geometry and fixture reference and the firmware backend remains unavailable.

## Internal evidence used

All paths below are relative to `/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper`; source was read without modification:

- `packages/temper-thermal/studies/glass_sensor/revision6/seal/README.md` and its analytical force/stiffness tables.
- `packages/temper-thermal/studies/glass_sensor/revision5/safety/README.md` for force allocation, reference path, jam challenge and observability limitations.
- `packages/temper-thermal/studies/glass_sensor/revision7/fixture/README.md`, `BUILD_AND_TEST.md`, `VERIFICATION.md`, `requirements.csv` for fixture scope, metrology, pressure path and NOT_RUN boundaries.
- `packages/temper-thermal/studies/glass_sensor/contact_detection/README.md` and `status.json` for prior test receipts and outstanding hardware blockers.
- `firmware/main/contact_guard.c`, `contact_guard.h`, `main.c`, `state_machine.c` and `firmware/test/test_contact_interlock.c` for the current producer/guard/state-machine boundary and focused host assertions.

Manufacturer sources above were accessed 2026-10-04. Public evidence establishes no completed 250°C moving cartridge, miniature seal cyclic force curve, safe blocked-reference assembly or qualified contact detector. Numerical conversions and force limits in this packet are closed-form screens from the cited inputs, not additional simulations or measurements.
