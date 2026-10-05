# R6: choosing the next sensor experiments

**Simulation and test preparation only. Physical tests remain NOT_RUN.** R6 compares four research directions without changing the frozen R5 CAD or production firmware. The contact comparison uses the pinned R5 network; the estimator, optics and seal studies have separate assumptions and cannot be combined into one demonstrated accuracy number.

Open [the comparison report](report.html). Detailed methods and reproducible outputs live in [contact](contact/README.md), [observer](observer/README.md), [optical](optical/README.md) and [seal](seal/README.md).

## Decision

Keep the R5 D6/M222 assembly as the control. Explore a 0.075 mm bond before a chip swap, then compare a complete IST308 assembly with actual leads and joins. Nominal full-envelope models give:

| Assembly hypothesis | Pan-step t90 | Thermal underread at 200°C |
| :-- | --: | --: |
| R5 M222, 0.10 mm bond | 2.94 s | 2.474°C |
| M222, 0.075 mm bond | 2.81 s | 2.441°C |
| IST308, 0.10 mm bond | 2.27 s | 2.576°C |
| IST308, 0.075 mm bond | 2.14 s | 2.520°C |

These are conditional predictions with identical assumed contact, not demonstrated component performance. Smaller footprint raises bond resistance. Unknown package mass makes the alternative's ranking uncertain. No case in the 324-case grid meets both 2 s and the proposed 1°C thermal allocation within a 2°C complete-system budget.

Carry simple boundary and bandlimited lead correction into future logs. In the independent synthetic plant, nominal maximum absolute error falls from 5.48°C raw to 1.11°C with lead correction, but reaches 2.03°C on the held-out light pan and fails badly with degraded contact. The untuned model bank is not a firmware candidate. None of these numbers replaces the R5 physical response/error score.

Develop seal architecture around controlled force, pressure reference, drainage and positive retention. At an assumed effective diameter of 8 mm, the proposed 3 mN pressure allowance permits only 59.68 Pa (about 6.10 mm water head). A temperature rating alone cannot qualify a moving seal. At zero pressure, after 3 mN hysteresis and 4 mN harness allowance, only 3 mN remains for elastic force: 0.012 N/mm over the local 0.25 mm stroke, or 0.00207 N/mm over the combined 1.45 mm envelope. The local-only calculation excludes the common carrier seal.

Keep 3–5 µm infrared as a parallel bench experiment. The radiation screen deliberately uses invented transmission curves, so it quantifies sensitivity to assumptions, not product accuracy. It includes glass/filter emission, can temperature and unknown emissivity. No installed optical response time is predicted. The 2025 paper's roughly 1.1°C forward-model RMSE is not blind pan-temperature accuracy; its inversion experiment reports approximately ±3°C maximum error in its own setup.

## What remains open

| Gap | What R6 supplies | Evidence still required |
| :-- | :-- | :-- |
| Bond and element | Pinned comparison, mass/film/lead sensitivity | Real film orientation, bonded area/thickness distribution, cured material properties, join process, installed calibration |
| 250°C moving seal | Pressure/stiffness budgets and cartridge precedents | Supplier-qualified compound and geometry, hot/cold force loops, flex life, cleaning/steam ageing, leakage |
| Jam-resistant contact | Synthetic examples showing estimator blindness | Independent force/contact proof under sticking, debris, lifted pan and plausible warm RTD; verified end-to-end inhibition |
| Cap retention | R5 remains the retained reference; seal is not retention | Captive load path, pull/impact testing, tolerances, hot service/reassembly evidence |
| Thermal performance | 324 conditional package cases | Calibrated contact conductance and assembled capacity across cookware; independent holdout data |
| Compensation | Reproducible normal and fault scenarios | Measured boundary/power inputs, identified parameters, startup validity and holdout cookware tests |
| Filtered IR | Radiation/error and field-of-view screens | Exact detector/filter/glass spectra versus temperature, emissivity identification, dirty-surface tests, installed transient data |
| Induction/endurance | Previous R5 preparation remains applicable | Energized EMI, cap self-heating, pan hotspots, electrical leakage, cleaning and thermal cycling |

## CAD disposition

R5 is still the canonical cartridge. Every R6 changed package is `PARAMETRIC_NOT_CAD_RELEASED`. The alternative uses an equal-area footprint and an assumed trimmed native lead; it has no complete manufacturable lead/cover geometry. Updating released CAD to those approximations would imply details this model has not established. The next CAD revision should be an explicit experimental coupon incorporating an exact IST308 part, actual film orientation and joins, complete routed lead length, bond control and both seal load paths. Re-export all mass and conductance geometry before scoring that revision.

## Reproduce

Run `./run.sh` here with rustc, rustfmt, clippy-driver, Python 3 and standard POSIX tools. Physics is Rust; Python only formats existing CSV data into the report. No Cargo cache, installed extensions, network, hardware or firmware is used. Unit runners invalidate success receipts before starting. A failed run may leave older/partial CSVs for inspection, but must not leave a current success receipt. The top-level source provenance is a snapshot; regenerate after intentional changes and reruns using `python3 provenance.py`.

The source manifest hashes all R6 artifacts except itself and explicitly pins inherited R5 inputs. Local file hashes establish reproducibility, not physical validation. Contact pins are enforced before execution. Observer reference hashes identify background documents and are not imported physics.
