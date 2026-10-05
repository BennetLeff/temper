# Revision 2 assembled thermal screening

**Uncalibrated simulation, not measured performance.** The recommendation is the retained Ø8 × 0.15 mm 316L cap, a sparse zirconia support and the existing M222. The smaller IST element is a coupon alternative. Preserve the unavailable contact backend until physical evidence closes the contact requirements.

Run `bash run.sh` here with Rust 1.92.0 or a compatible toolchain. No Cargo or Python physics implementation is used. `inputs.sha256` pins the kernel and cross-workstream inputs. If a source changes, reconcile its implications before deliberately updating the pin. Outputs are deterministic CSV sweeps; NaN means the threshold was not reached within the specified simulation horizon, not a passing value.

## Model and boundary conditions

The frozen study kernel integrates `C dT/dt = b − K T` using backward Euler. Four nodes represent cap, bond, RTD and the finite support island. Pan, glass and carrier are prescribed boundaries. The code solves DC directly and reports two distinct step times:

- `t90_final_s`: reach 90% of the RTD's own eventual 25→100°C response, with glass/carrier held at 25°C. A biased sensor can score well here.
- `t90_pan_s`: reach 92.5°C after that pan step. This accounts for error at the step endpoint; it is absent when the sensor cannot reach that temperature in 120 s.
- `error200_C`: RTD minus pan at steady pan 200°C, glass 80°C and carrier/lead surroundings 60°C. These boundaries are assumptions, not a prediction of glass temperature.

Contact area is `A = π(D/2)² × area_fraction`; pressure is `F/A`. The inherited illustrative law is `h = href × (pressure/5000 Pa)^0.7`. Contact resistance `1/(hA)` is in series with a pan half-space spreading resistance `1/(4 k_pan sqrt(A/π))`. Real roughness, curvature, oxide, pan thickness and laminated construction are not identified by this law. The nominal `href=1000 W/m²K` is unmeasured. Fractions 0.3–1 and href 250–4000 test sensitivity rather than confidence intervals. No spatial cap/RTD model, contact FEA, nonlinear radiation solve or induced current heating is hidden in this network.

## Inputs tied to the proposed assembly

| Quantity | Assembled R2 input and evidence |
|---|---|
| Cap | Mechanical CAD volume 9.0518223686 mm³ including all three hooks; 316L proxies 8000 kg/m³, 500 J/kgK and 15 W/mK. Capacity 0.0362073 J/K, versus PR1's 0.136395 J/K. |
| M222 | Nominal 2.3 × 2.1 × 0.9 mm whole-envelope solid proxy, Cv 3.12 MJ/m³K. This over-simplifies the actual substrate/coating distribution. |
| IST coupon | P0K1.161.6W.A.010: 1.6 × 1.2 × 0.25 mm substrate, same Cv proxy, plus assumed 0.00075 J/K fixdrop. Supplier order-code/class discrepancy remains open. |
| Bond | Resbond 908-1, 0.10 mm candidate; k 2.163418635 W/mK from catalog conversion, Cv 2 MJ/m³K assumed. Full bond areas 6.75/3.2 mm²; through resistance uses chip area 4.83/1.92 mm². Thin-layer cure, coverage and void fraction remain unknown. |
| Leads | Four TFCP-003-100 copper/PFA conductors, 60 mm developed each, short shared nickel stubs. Fin-model G 0.000326786 W/K at assumed distributed h=5 W/m²K and surroundings 60°C. End-conduction floor 0.000131287 is not an installed prediction. |
| Support link | Nominal 0.00065 W/K: three Ø0.30 × 2 mm zirconia posts contribute about 0.0003075; dry gas over the 12.6985 mm² projected spider contributes about 0.000254 at assumed k_air=0.04 W/mK; radiation budget about 0.00008. The last term corresponds to effective emissivity about 0.3 around 450 K, with unit view-factor bound. Constant-G approximation does not follow actual surface temperature. |
| Support capacity | 0.26 J/K rounded from CAD's 59.01086 mm³ island +1.125 clamps +3.92071 cap witness rod +1.6 flag, using zirconia Cv 3.66 MJ/m³K; plus 4.0824 mm³ blades including pads using X750 Cv about 3.57 MJ/m³K. Treating the entire rod/blades as isothermal island mass is an approximation, not a distributed solution. |
| Support to carrier | 0.001 W/K candidate including approximately 0.000864 blade conductance and witness/other paths. Unmeasured clamps and ambient gradients affect this. |
| Other direct loss | 0.0005 W/K target, 60% to glass and 40% carrier. This represents remaining free surfaces/paths, excluding the modeled facing spider region. It is a proposed isolation budget, not a measured benefit already obtained in CAD. |

Morgan's [CIM zirconia datasheet](https://www.morganthermalceramics.com/media/00td54fl/cim-zirconia.pdf) gives indicative room-temperature k=2.9 W/mK, density >6000 kg/m³ and cp=610 J/kgK. Temperature dependence, contact resistance and manufacturability of the thin posts remain unverified. Wetting the open support gap invalidates the dry-link assumption. A sealed barrier, lead cover or altered clamp can add force, thermal mass and conductance; none earns free thermal credit.

## Compare at equal force before coupling mechanics

The middle comparison fixes 0.25 N, full area, href=1000 and pan k=45 W/mK:

| Design/change | t90 to own final | Underread at 200°C |
|---|---:|---:|
| PR1 | 6.46 s | 5.92°C |
| PR1, half bond thickness only | 6.35 s | 5.73°C |
| PR1, lower loss only | 6.66 s | 1.65°C |
| Ø8 cap and hooks, same losses | 2.72 s | 6.68°C |
| R2 spider, M222, wire-fin loss | 2.81 s | 4.11°C |
| R2 spider, small IST coupon | 2.01 s | 4.83°C |

This separates the mechanisms: mass reduction improves speed; reduced leakage improves bias; a smaller contact face can worsen bias. Thinning the original bond alone has little effect. A 0.05 mm film is an ablation below the proposed process range, not a qualified recommendation. The no-support variants and ceramic-head variants are thermal comparisons, not buildable drop-in assemblies. Short alumina posts can couple the light head to the heavy carrier and destroy the expected response advantage.

## Actual spring force changes the result

`coupled_contact_thermal.csv` consumes the 36 piecewise series-spring rows from the contact model directly, including the main carrier upper stop. For the illustrative flat-pan depression of 0.60 mm, effective preload 0.12 N, main rate 0.2 N/mm and measured-target local rate 2 N/mm, force is **0.218182 N**, local motion 0.109091 mm and main motion 0.490909 mm. The CAD's loaded 0.45/0.15 positions are an envelope illustration, not this equilibrium solution.

| Coupled case, full area / href 1000 / k_pan 45 | t90 own final | t90 pan step | Underread at 200°C |
|---|---:|---:|---:|
| M222 | 3.05 s | 3.52 s | 4.42°C |
| Small IST coupon | 2.19 s | 2.60 s | 5.14°C |

The 0.12 N preload is an effective force after gravity/seal effects, not verified for this heavier cartridge. Actual net preload must be measured. At only 0.10 mm pan depression the series model gives 0.127273 N. Some low-depression corners fall below the contact detector's proposed 0.12 N minimum. Pan mass/offset/support footprint must also resist the probe reaction; additional spring force cannot be assumed free of rocking.

At 0.09 N and 30% effective area, even the new M222 yields 7.30 s to its own final value and 10.02°C underread at 200°C. Neither improved geometry nor the nominal result establishes performance across cookware.

## Ramps, tolerances and flexures

`ramps.csv` imposes 0.5, 2 and 5°C/s ramps, with glass/carrier rising linearly to 80/60°C when the pan reaches 200°C. At 2°C/s and the matched 0.25 N force, PR1 underreads 11.54°C at pan 200°C, R2 M222 7.50°C and IST 7.46°C. The small element's step-speed gain largely disappears here because leakage and the support tail matter. Pan reaches about 207.72°C before either R2 sensor reports 200°C in this imposed-ramp model. This is **not closed-loop overshoot**, and no PID or fixed offset is calibrated from it.

`flexure_screen.csv` is a separate ideal fixed-guided beam screen: `k_total=3 E w t³/L³`, `stress_peak=3 E t δ/L²`, with w=2.1 mm. E=180/200/220 GPa, L=6.8/7/7.2 mm and t=0.075/0.080/0.085 mm are sensitivity assumptions, not manufacturing tolerances accepted by a supplier. Nominal E=200 GPa gives 1.881 N/mm and 196 MPa at 0.20 mm motion, or 245 MPa at the 0.25 mm stop. No yield/fatigue safety factor is asserted. Real clamp compliance, edge stress, residual stress, hot relaxation and off-axis loads require supplier data/FEA and measurements. [Special Metals' X750 bulletin](https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-x-750.pdf) distinguishes temper, heat treatment and spring relaxation; a generic alloy label does not select a qualified foil process.

The CSV set contains 48 comparisons, 360 contact/material sensitivity cases, 432 coupled spring/thermal cases, 96 leakage-budget cases, 72 support cases, 54 dimensional cases, 48 ramps and 81 ideal beam cases. These are grid evaluations, not independent physical tests or probability estimates. The 23 tests include 14 inherited kernel tests plus nine regressions on baseline reproduction, DC invariance, support reduction, time-step refinement, ramp ordering and beam scaling.

Prioritize low head mass, low installed heat leakage and repeatable clean contact. Keep M222 for the first assembly; coupon the small RTD and alternate dielectric stack in parallel. Do not use calibration to hide uncertain contact, wetting, a seized island, time-varying lead loss or induction self-heating.
