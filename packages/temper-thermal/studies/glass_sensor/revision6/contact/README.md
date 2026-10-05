# R6 contact-package comparison

**Characterize the existing M222 assembly first.** A smaller, thinner element can improve the model's response, but changing the chip alone does not meet the complete accuracy target. The candidate ordering also depends on the existing element's unmeasured effective heat capacity.

This unit is simulation and test preparation. Every physical result is **NOT_RUN**. Existing D6 CAD remains the frozen reference. All modified cases are **PARAMETRIC_NOT_CAD_RELEASED**; they do not establish manufacturable joins, clearances, bond processes, electrical insulation or fatigue life.

## Reproduce

From the installed `revision6/contact` directory, run `./run.sh` and `./check_runner.sh`. In a scratch directory, set `TEMPER_GLASS_STUDY_ROOT` to the existing `glass_sensor` directory. Only standalone rustc, rustfmt, clippy-driver and ordinary shell utilities are used; no Cargo cache or installed extension changes occur.

The runner verifies full hashes of the original kernel, frozen R5 model and R5 CAD scalar export. It constructs a temporary module containing the R5 source **verbatim**, then appends `adapter.rs`. No historical physics source is edited, forked permanently or re-pinned. The adapter replaces named bond, chip-capacity and native-lead terms in the assembled network. All R5 cover, weld, complete 60 mm copper/PFA routing, support, anchor, seal and cap nodes remain. The runner only copies results after tests, warning-clean compilation, Clippy and the simulation succeed; it removes the prior success receipt before beginning. Failed runs may leave older result files for inspection, but no success receipt.

`results/run-inputs.sha256` is a receipt with two path bases: the first three inherited inputs are relative to the glass_sensor root; adapter, runner and output paths are relative to this unit. `inputs.sha256` is the executable inherited-source pin list. Source-provenance above this unit should hash the remaining authored artifacts.

## Controlled comparison

D6, spring force 0.218182 N, fixed nominal R5 cap, and the same pressure/area contact law. The 324-case grid contains three package geometries × two capacity proxies × three bond thicknesses (0.075/0.10/0.15 mm) × three patterns (uniform, central Ø4 mm, rim) × two loss bundles × three contact-law reference conductances (1000/2000/4000 W/m²K).

The nominal bundle retains R5 wire h=5 W/m²K, direct loss=0.0002 W/K and seal G=0.0002 W/K. The higher-loss bundle uses 15, 0.0005 and 0.001 respectively. Neither bundle is a probability distribution or a certified worst case. All other R5 material, interface and boundary assumptions are unchanged; see [R5 thermal model](../../revision5/thermal/README.md).

The smaller rectangular sensing footprint is represented by an equal-area circular patch. This is a thermal screening approximation: IST308's elongated 3 × 0.8 mm shape is not resolved in angle. Pan/cap contact remains an independent assumed pattern; neither CAD nor this model proves contact.

| Package | Footprint | Capacity proxies | Assumed film path from bonded surface | Native leads in main grid |
| :-- | :-- | :-- | :-- | :-- |
| M222 | 2.3 × 2.1 mm | Half-envelope 0.45 mm / full-envelope 0.9 mm | 0.45 mm, inherited R5 | Two Ø0.2 × 1 mm |
| IST308 | 3.0 × 0.8 mm | Substrate-only 0.25 mm / full-envelope 0.6 mm | 0.125 mm, half-substrate hypothesis | Two Ø0.15 × 1 mm |
| IST161 geometry only | 1.6 × 1.2 mm | Substrate-only 0.25 mm / full-envelope 0.6 mm | 0.125 mm, half-substrate hypothesis | Two Ø0.2 × 1 mm |

These are **effective-capacity sensitivity proxies, not guaranteed mass bounds**. M222's separate substrate thickness is not established by the cited sheet; its lower proxy is deliberately an assumption. IST's substrate-only proxy omits the unspecified protection/drop material. All package volumes use the same assumed 3.12 MJ/m³K. A full rectangular height envelope is not the physical volume of a contoured glass drop. Platinum and protective material distribution, exact film depth, temperature-dependent properties, contact of the overcoat and native lead gradients remain unmeasured. The half-substrate heat path is especially optimistic if the film is on the far face; characterize the actual film orientation before design selection.

The complete R5 bond-pad area **6.75 mm² is retained for bond mass** and multiplied by each thickness. Through-thickness conduction uses the actual candidate chip footprint, not the larger pad. Thus the adapter does not gain artificial capacity savings by silently deleting bond overhang, covers or wire. Bond k=2.163418635 W/mK and volumetric capacity=2 MJ/m³K remain inherited unqualified proxies. Bond resistance is `R=t/(k*A)`: at 0.10 mm it is 9.570 K/W for M222, 19.260 for IST308 and 24.075 for IST161. Cap through-thickness conductivity=15 W/mK, ceramic path conductivity=25 W/mK, both inherited assumptions.

Two native leads retain the inherited nickel conductivity 90.9 W/mK and capacity 3.95 MJ/m³K. These approximate plated nickel; plating and alloy are not resolved. The main comparison explicitly assumes **1 mm trimmed leads**, as in R5. This is not a manufacturer-approved trimming or joining process. `native_lead_sensitivity.csv` sweeps 1/3/7 mm, including the IST308 supplied length, with full native-lead capacity and resistance but the same R5 external wire/cover geometry. Longer leads are lumped at the sensor node as in R5; their detailed thermal gradients, cooling, routing and changed weld positions need a new spatial model/CAD.

## Metrics

`t90_pan_s` reaches 90% of the 25→100°C pan step, with glass/body fixed at 25°C. `t90_own_s` uses 90% of that sensor's eventual response and is reported separately. Positive `underread200_C` is actual pan 200 minus sensor, with glass80/body60°C. The finite ramp heats pan25→200°C over35s (5°C/s), glass/body25°C; error at35s includes transient lag and static loss. It is not controller overshoot. Numerical steps are 0.01s; joint mesh/time refinement is separately reported.

## Primary component sources checked 2026-10-04

- [YAGEO Nexensos M222 sheet](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN), version03,11/2024: package dimensions, Pt-clad Ni leads and application limits. Its 0.15s water response is not dry-pan response and is not used as an installed time constant.
- [IST 300°C series, DTP300 E2.4.3](https://www.ist-ag.com/sites/default/files/downloads/DTP300_E.pdf): IST308 Pt100 `P0K1.308.3K.A.007`, order101941; substrate/total heights and Ø0.15mm,7mm wires. The current sheet lists the 161-size rows as **Pt1000**, not an orderable Pt100 in this document. It is retained solely as a geometric sensitivity, with no resolved replacement BOM. Listed dimensions have tolerances; this grid uses nominal values and does not claim a tolerance stack.

## What this does not build

No production controller, new contact authorization method, manufactured cartridge, thermally qualified bond, purchasable 161 Pt100 selection or alternative manufacturing CAD. Candidate terminals/covers would need redesigned geometry and updated complete exported mass. The resulting interface changes could erase the simulated response improvement. No calibration, induction interference or durability evidence is fabricated.

`film_path_sensitivity.csv` separately varies uncertain ceramic path length (M2220.45/0.9mm; IST0.125/0.25/0.6mm) while retaining the full-envelope capacity proxy. This exposes uncertainty in the film-side and encapsulation arrangement rather than treating half the substrate as a known assembly property. See [results](RESULTS.md) for the numerical decision.
