# R7: complete experimental coupons and test fixtures

**Simulation and test preparation; all physical tests NOT_RUN.** Open the [report](report.html), [coupon CAD](mechanical/README.md), [thermal comparison](thermal/README.md), [fixture package](fixture/README.md) and [calibration preparation](calibration/README.md).

R7 replaces the R6 package-only alternatives with complete experimental cartridge geometry and exports the changed masses, bond areas and routed lead lengths into the thermal model. Maximum supplier package envelopes exposed clashes in the inherited covers. Both M222 variants now have matched clearance corrections; the IST308 also required new wire approaches and anchor relief. The old R5 remains a separate frozen numerical baseline.

| Nominal modeled assembly | Pan-step t90 | Thermal underread at 200°C |
| :-- | --: | --: |
| Frozen historical R5 D6 | 2.94 s | 2.474°C |
| R7 clearance-corrected M222, 0.100 mm bond | 2.91 s | 2.474°C |
| R7 M222, 0.075 mm bond | 2.78 s | 2.441°C |
| R7 IST308, 0.075 mm bond | 2.05 s | 2.577°C |

The complete IST308 is faster under the nominal assumptions, but it still misses the proposed <2 s and <2°C complete-system target. Its rim-contact case is 5.47 s / 6.08°C. Using maximum-envelope mass and a full-height film-path proxy gives 3.04 s / 2.73°C even with nominal uniform contact. The apparent benefit therefore remains conditional on contact and unknown internal package properties. None of these is a measured result or a production guarantee.

## What is now concrete

- Three complete cartridge variants, four motion poses each, standalone head STEP files and section drawings. All 12 nominal pose checks and the three supplier maximum-package screens pass. Installed native leads, split joins, covers, anchor and four complete 60 mm extension routes are included.
- A pinned CAD scalar contract drives 54 thermal contact/loss cases, 27 capacity/film cases, a full node-capacity ledger and refinement checks. The frozen R5 baseline still reproduces; corrected R7 control changes are accounted for explicitly.
- A dry independent force/displacement frame and separate connected pressure-cell geometry, with uncertainty calculations and blank measurement records. The cartridge remains unsealed; the pressure cell is a different test article.
- A calibration adapter reuses the existing bench evaluator, requires distinct pan identities and matching article/process hashes, and separates successful forward-model fitting from guarded <2°C/<2 s performance. Empty, same-pan, weak-contact and hidden-dynamics cases are exercised.

The fixture metrology is demanding: at an assumed 2.4N/mm slope, 2µm paired registration uncertainty alone contributes 4.8mN, exceeding the proposed 3mN hysteresis allocation. A capability target of 0.2µm paired registration plus 0.6mN force uncertainty per reading leaves 1.32mN for the observed loop. No actual instrument has been selected or demonstrated at those bounds.

## Remaining gaps and required evidence

| Gap | R7 status | Evidence still required |
| :-- | :-- | :-- |
| Package/CAD fit | Nominal poses and supplier max envelopes checked | Received dimensions, thermal expansion, process variation, real insulation walls and reassembly |
| Bond and native leads | Complete installed geometry; trim/form/join hypotheses explicit | Film side/pad pitch, cure revision, sections/voids, forming/weld process, installed resistance calibration and ageing |
| 250°C seal | Separate connected test-cell geometry and force budgets | Actual cartridge fluid boundary, qualified membrane/gland, hot/wet force loops, leakage and flex-life evidence |
| Jam-resistant contact | Independent bench measurement and fault procedures prepared | Independent production observable, common-cause/frozen/stuck/debris coverage and verified end-to-end inhibition |
| Cap retention | Positive modeled capture and test method retained | Product-derived loads, hook/post/weld strength, unequal engagement, fatigue and hot/aged testing |
| Temperature/control | CAD-coupled sensitivity and stricter calibration checks | Measured contact/boundary parameters, whole-pan holdout, startup/ramp/overshoot validation and reviewed controller integration |
| Induction/endurance | Prior procedures remain applicable; retest triggers recorded | Interference, cap self-heating, pan hotspots, leakage, cleaning/thermal-cycle and after-stress fault tests |

## Reproduce and preserve history

`./run.sh` verifies the saved CAD receipts, reruns Rust analysis/negative checks and calibration, then regenerates the report and artifact manifest. `./run.sh --rebuild-cad` also regenerates the cartridge and fixture CAD using the existing CadQuery/plot interpreters. Interpreter overrides are documented in the unit runners. No installations, shared Cargo builds or hardware operation occur.

The thermal runner accepts only its pinned geometry digest; intentional CAD changes require reviewed new results and an explicit pin update. Never automatically accept a mismatch. STEP files can contain exporter timestamps, so their byte hashes identify each generated snapshot while the quantized scalar contract is the thermal identity.

`CURRENT.md` and `current-cad.json` advance to R7 experimental geometry. Their previous R5 bytes are preserved under `history/`, where their identities still match the original R5 manifest. R5 and R6 files/manifests are unchanged. `provenance.py verify` checks the historical records as well as the current artifacts; it does not relabel predictions as measurement.

See [verification](VERIFICATION.md) for executed checks, review coverage and the final artifact identity. The next supported stage is a controlled engineering prototype after the missing supplier/process and fixture details are resolved, not a cooking release.
