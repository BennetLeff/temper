# Glass sensor R4 — close model gaps before freezing the cartridge

**Simulation and test preparation only. Hardware NOT_RUN.** R4 adds cap radial heat spreading, contact-location sensitivity, a finite-capacity seal screen, cavity-pressure force and unequal retention-load sharing. R3 CAD remains the dry coupon geometry; no newly sealed CAD, physical qualification or firmware enablement is claimed.

[Closure package](CLOSURE.md) · [Results](results/spatial.csv) · [Reproduction](run.sh) · [Verification](verification.md)

## What changed the decision

The previous R3 target was 1.78 s to the sensor endpoint, 1.89 s to the pan-step threshold, and 1.92°C underread. It treated the entire thin steel cap as one temperature. Resolving radial conduction, while preserving R3 capacities and total conductance, changes the nominal uniform-contact result to **2.610 s / 2.785 s / 2.287°C underread**. This is a model refinement, not an observed degradation of hardware.

At the same total pan-to-cap conductance (0.080832726 W/K), contact location matters:

| Assumed contact distribution | t90 of pan step | Underread at 200°C |
|---|---:|---:|
| Uniform across Ø8 mm |2.785 s|2.287°C|
| Center disk Ø4 mm |1.845 s|1.543°C|
| Outer annulus r3–4 mm |6.760 s|5.348°C|

These are deliberately controlled spatial hypotheses. They do not predict how a real pan develops contact or how much conductance a center land can achieve. Holding total conductance equal isolates cap spreading; it does not hold force, local pressure or pan spreading resistance equal.

**Withdraw 0.13 W/K as a sufficient general coupon screen.** With the R3 high-wire-cooling and added-seal-loss assumptions, even uniform contact at that value yields 2.110 s and 2.372°C underread. A scalar conductance measurement cannot qualify an unknown contact map.

The inverse uniform-contact case needs about0.1684 W/K for the same2 s /2°C thermal-only limits; center contact about0.0928 W/K. Rim contact finds no solution up to0.5 W/K. These are conditional thresholds with a zero-capacity seal and fixed properties, not production requirements. No-solution means within the searched interval, not a mathematical impossibility for all designs.

Reducing cap thickness0.15→0.10 mm barely helps the uniform case and worsens the rim-contact case to8.505 s /6.842°C. Keep0.15 mm until spatial coupons support changing it. A hypothetical doubled in-plane conductivity improves spreading but is not a selected material or a demonstrated manufacturable laminate.

## What is now analyzed

- A32-annulus cap replaces the single cap node, with inherited bond, RTD, island, hooks and copper anchor nodes. Cap mass and total conductances are preserved. The high-conductivity limit recovers the frozen R3 result.
- A centered equivalent circular RTD footprint has area4.83 mm². The off-center anchor is smeared over r1.25–2.75 mm, posts over r2.95–3.25 mm and hooks over r3.7–4 mm. The solid-post link is0.00030748 W/K from threeØ0.3×2 mm zirconia posts at k2.9; the remainder of the inherited0.00065 W/K support link is distributed uniformly as an uncalibrated gas/radiation surrogate. Those axisymmetric approximations cannot resolve the three posts/hooks or azimuthal pan tilt; a2D/3D field remains a later check.
- Adjacent annuli use `G = 2πkt / ln(r_outer_center/r_inner_center)`, symmetry at the center and an insulated radial rim. Face contact and losses are distributed by exact overlap areas. No Dirichlet condition is displaced into an outer cell.
- CAD hook and anchor-pad capacities are read from pinned R3 scalar exports. R3 material proxies, wire-fin equations and link resistances are inherited. In-plane k is varied independently; the k30 case intentionally keeps cross-plane k15, so it is an anisotropy sensitivity, not a material substitution.
- The barrier-capacity sweep inserts one lumped node with two conductances2G in series and C0.001–0.1 J/K. It produces a small step-time penalty at the assumed tiny G, plus a slower ramp tail. Actual seals may have much larger conductance; this sweep is not evidence that sealing is thermally free.
- The long-ramp column is an exact linear-network particular solution: `K s = g_pan`, `K lag = C s × 5°C/s`. It reports **additional lag relative to instantaneous steady state**, after ramp transients die out. It is not a finite35-second heating simulation or controller overshoot prediction. Uniform R3-target additional lag is8.16°C at5°C/s; a short t90 does not establish dynamic±2°C tracking.
- Grid16/32/64 and dt10/5 ms convergence, cylindrical-resistance identity, energy balance and inherited-lumped-limit checks constrain numerical error. They do not establish physical correspondence.

## Seal and force consequence

For a rigid sealed gas volume initially at25°C and atmospheric pressure, `Δp = p0 ΔT / T0`. A5 K average-gas rise across50 mm² effective diaphragm area gives **84.96 mN**. The entire R2 local parasitic budget is10 mN. Real cavity compliance changes pressure; its absence from the old design is exactly the gap this screen exposes.

A proposed3 mN pressure allocation over50 mm² permits only60 Pa differential. This is an allocation within the existing10 mN total, not a measured seal capability. A nominally sealed shell, static optical window and feedthrough are insufficient without pressure balance or qualified pressure equalization. An unrestricted vent is not a liquid barrier. See the full acceptance contract in [CLOSURE.md](CLOSURE.md).

## Evidence boundary

No newly manufactured cap, bond, lead weld, membrane or optical assembly exists from this task. No induction test has run. The jammed-island and credible-frozen-signal counterexamples remain unresolved; firmware remains unavailable. R4 closes omitted *analysis* and defines discriminating experiments; it cannot close physical qualification by changing a status label.
