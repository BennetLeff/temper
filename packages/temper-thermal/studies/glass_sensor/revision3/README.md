# Glass sensor R3 — retention gap and hot copper-lead anchor

**Simulation, CAD and test preparation only. Physical measurements NOT_RUN.** This revision develops the approved contact/heat-leakage direction into a dimensioned dry coupon assembly and stronger model. The M222 and existing copper wire remain the preferred first experiment. No production sensor backend, electrical hardware or firmware was changed.

[Engineering report](report.html) · [Mechanical CAD](mechanical/R3-rest.step) · [Selected cap](mechanical/R3-cap.step) · [Results](thermal/results/comparison.csv) · [Verification](verification.md)

## Decision

Use a **0.20 mm nominal retention clearance** and test a **hot copper-lead anchor on the cap**. Keep the cap Ø8 ×0.15 mm and retain the M222. Compare flat face finishes first. A crowned face may match one pan curvature while worsening another, so it is not selected as a universal contact improvement. The modeled thin-cap and small-RTD alternatives remain later coupons.

The preferred *target case* predicts **1.78 s to90% of its own endpoint,1.89 s to90% of the pan step, and1.92°C thermal underread at200°C**. This depends on doubling the unmeasured contact coefficient, achieving0.0002 W/K other direct loss and a0.003 W/K lead-to-cap anchor. These are qualification targets, not properties established by CAD. At low depression the same target yields2.37 s /2.57°C, and at weak contact4.15 s /4.40°C. No blanket cookware claim is supported.

## A missed path in R2

The R2 cap hooks sit0.05 mm below the ceramic arms. CAD gives **0.720 mm²** total opposing area, independently consistent with three0.30 ×0.80 mm overlaps. A thin air gap conducts heat even without a solid collision. The earlier four-node model had no explicit hook-to-island path; its aggregate support estimate did not document this geometry. It may have absorbed some of that loss implicitly, so the new result is a resolved-path hypothesis, not a measured correction.

R3 separates the cap disc and hooks into thermal nodes. At assumed k_air0.04 W/mK, thin-gap conduction is0.000576 W/K for R2. Including the steel path and an assumed radiation term gives0.0004168 W/K in series. Increasing clearance to0.20 mm reduces the total to0.0001343 W/K, about68%, while increasing cap volume only9.05182→9.10582 mm³. Nominal cap mass is72.85 mg using the inherited8000 kg/m³ proxy.

This change buys a small temperature improvement; it is not the whole solution. With resolved hooks and unchanged copper/contact/loss assumptions, R2 underreads4.80°C and R3's larger gap4.56°C at200°C. R2's former4.42°C figure did not contain the explicit gap path. The new split capacitance also changes normalized response, making pan-step time a better comparison than a flattering fast response to a biased endpoint.

The increased clearance also allows **0.20 mm cap lift before capture**. The sensor and anchor move with the cap. A stuck-to-pan cap, lead pull, free-flight/rattle, debris in the catch, wear and cap retention strength therefore require retest; clearance is not a free thermal improvement. Six CAD poses include cap capture. Hooks still retain mechanically, independently of the RTD bond.

## Keep copper, move where it loses heat

The new coupon embeds four intact PFA-insulated copper segments in a1.3 ×1.5 ×0.42 mm cap-side pad centered at x0,y−2 mm. FourØ0.232 mm passages at0.28 mm pitch locate the wire outer envelopes. The geometry preserves the0.15 mm cap and leaves clearance from the maximum RTD body and three ceramic posts. Net pad volume is **0.565360 mm³**; its modeled heat capacity is0.001131 J/K using the unverified bond Cv proxy2 MJ/m³K. The CAD does not include a verified full formed wire route or native-lead weld shape.

The thermal network routes heat from the RTD through two shared nickel stubs and short copper segments to a separate lead-anchor node. That node connects both to the cap and to the remaining wire fins. This transfers some of the heat load from the RTD to the cap; **it does not eliminate heat flow into the cold wiring**. Anchor/wire capacitance is included. With unchanged contact and ambient loss, the anchor improves underread4.56→4.18°C and slightly slows normalized response. It becomes useful in combination with stronger contact and lower direct loss.

Nominal wire layout: four60 mm developed TFCP-003 copper/PFA conductors;2 mm effective hot distance to the anchor,1 mm active anchored length within the1.5 mm pad and57 mm remaining fin. Treat these as lumped effective lengths; the real bends and end transitions must be measured. The1.2 mJ/K lead-anchor node is a copper/PFA lumped capacity estimate, separate from the CAD pad capacity. Native shared stub resistance still needs assembly calibration.

**The pad is a process coupon, not an approved adhesive joint.** The PFA jacket stays intact. No dielectric credit is taken for the pad. Adhesion, wetting/contact fraction, ceramic cracking, PFA creep, weld strain and installed force are unverified at250°C. No scraping the jacket or bonding conductive wire directly to the pan-facing metal is specified. If the coupon cannot demonstrate conductance and insulation together, reject this anchor construction.

A simple ideal insulation/bond series calculation gives about0.00276 W/K at assumed PFA k0.25 W/mK and half-circumference contact over1 mm. The proposed0.003 W/K target is close to this idealized value; interface resistance could make it unattainable. `anchor_conductance_bounds.csv` therefore varies conductivity and contact fraction, and `anchor_sensitivity.csv` explicitly includes0.0003–0.006 W/K. Drawing a pad does not earn0.003 W/K.

## A concrete contact requirement

Rather than assign a finish an arbitrary2× benefit, measure the **effective conductance from the pan to the cap**, including local pan spreading. For the preferred target package:

| Conditions | Model minimum effective conductance for t90-pan≤2 s and thermal underread≤2°C |
|---|---:|
| Wire cooling h5, no added island barrier loss |0.07715 W/K|
| h5 plus0.0002 W/K barrier/seal path |0.09341 W/K|
| h15 plus0.0002 W/K barrier/seal path |0.12415 W/K|

Use **0.13 W/K as a candidate coupon screen** across the declared low-force/pan/temperature matrix. It covers those particular simulated boundaries with a small margin; it is not a general product acceptance limit or a complete uncertainty allowance. The cap-to-wire anchor must independently meet its assumed target, other direct loss must be≤0.0002 W/K, and the added seal path≤0.0002 W/K. If those bounds fail, recalculate the requirement. The existing motion detector proves neither this thermal conductance nor an unjammed island.

Inverse results also show why simply specifying more force is weak: for the same conductance requirement, low force or low effective area demands a larger material/contact coefficient. That coefficient must be measured, not inferred from cap appearance. No main spring preload is increased in this revision.

The macro-gap model tests pan bowl±25/100µm, cap crown0/10/25µm and relative tilt0/0.1/0.25/0.5°. It integrates a gas film with an assumed10µm roughness floor. This is a geometric screening model, not a solid-contact or deformation solution. Its `near_area_fraction` is **not** the pressure-law contact fraction. It shows why a fixed crown is not universally beneficial. Two optical heads still provide one differential motion signal; a0.5° tilt at0.8 mm offset contributes about7µm, so self-alignment cannot be added without revisiting the detector error budget.

## Alloy-wire comparison remains separate

Omega's [single-wire sheet](https://assets.dwyeromega.com/spec/OE_DS-TFIR-CH-CI-CC-CY-AL.pdf) lists TFCC-003,Ø0.08 mm constantan/PFA, unlike the thicker0.13 mm comparison in R2. At the inherited h5 wire-fin assumptions, four60 mm wires give0.0000745 W/K versus copper's0.0003268 W/K. This enables1.71 s /1.82°C with doubled contact and without the lower-direct-loss target. Those numbers exclude electrical offset errors.

Constantan is a **bench coupon alternative**, not a substitution into the current frontend. Dissimilar-junction temperatures can create offsets. For example, an assumed40µV/K mismatch coefficient and3 K unequal junction temperatures produce120µV, equivalent to about1.09°C at200°C and0.3 mA. A four-wire connection does not cancel that. Current reversal can cancel a stable offset; drift between samples, switching settling and RF rectification remain. [Keithley's handbook](https://www.tek.com/en/documents/product-article/keithley-low-level-measurements-handbook---7th-edition) describes those constraints. Use an external qualified bipolar measurement setup for this comparison; none has been designed into the firmware or PCB here.

## Model scope and evidence

The six-node network uses cap disc, bond, M222, ceramic island, retention hooks and lead anchor. The last node is decoupled in unanchored cases. It reuses the pinned historical Rust linear-network solver. CAD exports cap volumes, opposing area and anchor-pad volume directly into the model; series-spring force is consumed from R2's CSV. All heat capacities, material properties, gas-film behavior and contact laws retain their stated uncertainty. Contact/stress FEA, weld fatigue, sealed-fluid behavior, actual induction fields and spatial temperature gradients are not solved.

The new tests check the R2 DC limit, hook series-resistance reduction, independent facing area, wire-fin reference and no-loss limit, time-step convergence, uniform anchor temperature, anchor-gradient benefit, gas quadrature and current-reversal algebra. These are software checks, not hardware measurements.

[Coupon and inspection plan](TEST_PREPARATION.md) contains the next physical evidence. [Sources and assumptions](SOURCES.md) separates supplier facts from hypotheses. [Verification](verification.md) records executed checks. R1/R2 files and firmware remain unchanged; R3 is a separate local engineering package.
