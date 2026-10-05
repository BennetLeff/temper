# Revision 2 test preparation addendum

**NOT_RUN — no physical measurements.** Use the existing [bench protocol](../bench_validation/PROTOCOL.md), [strict import/calibration tools](../bench_validation/README.md), [bond/lead assembly instructions](bond_leads/ASSEMBLY.md) and [induction test plan](../induction_validation/TEST-PLAN.md). This addendum identifies what the new assembly changes. It is not permission to energize an unqualified wet or mains assembly.

## Record before acquisition

Record cartridge serial, CAD/hash, actual cap dimensions and mass, RTD part/lot, cured bond thickness/coverage, wire diameter and developed length, nickel stub and weld lengths, installed route photographs, alloy temper/heat treatment, measured free blade lengths/thicknesses, seal lot/geometry and all calibration certificates. Separate dimensional measurements from simulations and manufacturer catalog values. Record the independent run/holdout allocation before fitting.

The proposed CAD loaded state is a clearance pose; it is not spring equilibrium. Record main-carrier and cap-island movement separately. Determine effective main preload with the final island mass, membrane and harness installed. Do not reuse the PR1 spring's nominal force as the assembled value.

## Dry mechanics and detector

| Preparation | Acquired channels / cases | Evidence sought |
|---|---|---|
| Force-path separation | Calibrated force, main travel, local differential, both raw optical channels, head/rod temperatures, diagnostic codes and timestamps | Total local stiffness1.6–2.4 N/mm and ≤10 mN total parasitic force are proposed qualification targets, including wires and future barrier |
| Metrology | Known local displacements across0–250 µm at controlled head temperatures; repeat tilt, mounting and hot-rod gradients | Worst-case total error≤15 µm is a target requiring an actual uncertainty budget, not an RSS of datasheet headlines |
| Contact envelope | Available depression0.05/0.10/0.25/0.60 mm; net preload and measured local stiffness; realistic pan flatness, mass and offset | Force≥0.12 N over a declared cookware envelope; reject corners below it; measure uniform lift and rocking relative to glass |
| Fault injection | Hold main guide; hold main seal; independently seize island and rods; bend/rub a retention tab; insert force-transmitting insulating debris; block optics; hold a credible fresh reading | Main-jam rejection alone is insufficient. The known blind cases must remain recorded as failures until independent diagnostics are demonstrated |
| Release timing | Independent physical loss-of-contact event, unfiltered channels, filtered differential, detector state, control inhibit and actual output extinction | Measured end-to-end latency with uncertainty. The50 ms firmware freshness guard does not prove physical release latency |

Do not zero a loaded or possibly seized island. Establish unloaded state independently. The two optical heads form one differential instrument, not two redundant proofs. Place them within their specified cold operating conditions; do not assume a long rod guarantees this.

## Thermal and bond coupons

Compare at least the baseline M222 stack, R2 M222 and small-IST coupon with identical reference attachment and controlled force. Record both t90 relative to the RTD endpoint and t90 relative to the pan step. Retain steady error, ramp error and the slow thermal tail; a short normalized step metric can hide bias. Measure glass, carrier, island and lead-route temperatures to replace assumed60/80°C boundaries.

Use0.075/0.10/0.15 mm bond candidates, measured after cure, with process/void records. A0.05 mm simulation is not a manufacturing specification. Coupon actual welds and shared nickel stubs; characterize resistance drift versus their temperature as well as RTD self-heating/current dependence. Inspect insulation and strain relief after cycling. Do not claim solder, coating or ceramic cement as the complete250°C wet insulation barrier from a catalog value.

Characterize support heat transfer in the dry assembly before fitting it. Compare the measured full thermal response against the model; fit selected physical parameters only when the experiment distinguishes them. Lead G, contact G and support G can compensate for each other in an underdetermined fit. Preserve separate fitting and holdout runs; a good fit is not validation across cookware.

## Sealed revision and induction

Before fabricating a sealed product, obtain a supplier-reviewed membrane/gasket design, defined compression/clamping loads, custom molding tolerance, media/temperature duty and food-contact evidence where required. Specify the cold static optical window and electrical feedthrough and explicitly close the cap-to-carrier cavity. Re-measure local stiffness, parasitic force, optical uncertainty and thermal leakage after installing every barrier.

Complete cap hook retention, thin-post side-load/dent and flexure/clamp fatigue evidence on representative manufactured parts. Thermal cycling and cleaning must include the actual bond, welded leads, coatings and seals. Freeze application-specific acceptance limits and sample count before these tests; simulation has not set validated life claims.

The induction plan must include the final hooks, beams, clamps, welds, harness loops and surrounding metal. Measure coil-on/off electrical pickup, actual cap/island/beam heating and force-zero shift against a dissimilar reference. Do not subtract a room-temperature dummy-resistor error and treat that as proof of no real cap self-heating. Repeat loss-to-inhibit tests while switching, with representative pan offsets and wet/cleaned states only after the fixture and liquid barriers are qualified.

The existing acquisition templates remain deliberately empty. Never store simulated rows as physical calibration or mark a hardware gate passed from this study.
