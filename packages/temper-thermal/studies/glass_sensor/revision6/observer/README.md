# R6 offline estimator comparison

**SYNTHETIC_ESTIMATOR_STUDY — hardware NOT_RUN.** This is a reproducible comparison of estimator failure modes, not an improved R5 thermal score, a validated controller, or firmware. It issues no heating commands. R5's physical sensor response is unchanged by processing its output.

The result favors carrying a simple, bandlimited correction into later calibration experiments before adopting a model bank. The untuned bank performs worse on held-out pans, and its wide range is not an accuracy guarantee. All methods fail badly when contact disappears while the independent contact input incorrectly remains valid.

## Results

Maximum absolute temperature error over the full 120 s trajectory, including startup; °C. Every method uses the same 2,400 output times at 50 ms intervals. All rows below are synthetic; neither the numerical targets nor the errors are hardware measurements.

| Scenario | Raw RTD | Steady correction | Bandlimited lead | Bank midpoint |
|---|---:|---:|---:|---:|
| Nominal power pulses | 5.476 | 2.520 | 1.112 | 2.144 |
| Held-out light pan, different waveform | 6.325 | 4.489 | 2.030 | 8.560 |
| Held-out heavy pan, deterministic noise | 3.120 | 1.204 | 1.598 | 15.440 |
| Contact conductance falls fivefold | 21.072 | 18.353 | 15.895 | 12.389 |
| Hot restart with unknown initial pan | 106.039 | 104.397 | 104.604 | 109.873 |
| Measured body/glass boundary change | 4.271 | 3.329 | 1.896 | 1.263 |
| Fresh timestamp but frozen reading | 96.552 | 95.565 | 95.565 | 91.238 |
| Warm detach, contact input incorrectly true | 136.007 | 135.959 | 135.991 | 130.540 |

The stale-timestamp case has the same all-sample errors as the fresh-frozen case, but the independent freshness condition rejects later samples. Only 802 of 2,400 samples remain authorized by that **study Boolean**. Maximum error over those samples is 3.256/1.986/0.902/0.681°C respectively. These are different metrics: filtering rejected samples does not repair the trajectory or prove physical cutoff timing.

The bank's nominal range contains truth at all sampled times but can be **26.80°C wide**. For the held-out light pan coverage falls to **40.875%**. The noisy heavy-pan range can be **33.40°C wide**, while its midpoint errs by 15.44°C. Coverage is a deterministic fraction of this trace, not a confidence level. Calling that range a safety bound would be wrong.

`results/comparison.csv` also reports maximum underread, RMSE, allowed-sample error and bank range width/coverage. `results/traces.csv` saves every fifth output (250 ms) for plotting; aggregate metrics still use every 50 ms output. Trace rows repeat the same bank bounds on all methods solely to simplify paired plotting.

## Plant, hypotheses and separation from R5

The synthetic plant has four energy-conserving nodes: pan, cap, RTD and a hidden support. Its balances are:

```
Cp dTp/dt = P - Gpc(Tp-Tc) - Gpa(Tp-Ta)
Cc dTc/dt = Gpc(Tp-Tc) - Gcr(Tc-Tr) - Gcs(Tc-Ts) - Gcg(Tc-Tg)
Cr dTr/dt = Gcr(Tc-Tr) - Grs(Tr-Ts)
Cs dTs/dt = Gcs(Tc-Ts) + Grs(Tr-Ts) - Gsb(Ts-Tb)
```

Nominal capacities are Cp=400, Cc=0.045, Cr=0.015, Cs=0.15 J/K. Nominal conductances in W/K are Gpc=0.08, Gcr=0.10, Gcs=0.0007, Grs=0.0005, Gsb=0.02, Gcg=0.0003 and Gpa=0.5. `plant_parameters.csv` records every scenario's constants. Contact degradation sets Gpc=0.016 at t=40 s; detach sets it to zero. All other physical parameters are positive.

These coefficients are **declared synthetic choices**. The topology follows R5's contact/bond/support/loss paths, and sensor-capacity order of magnitude is compatible with R5. No coefficient is fitted to R5's 2.94 s / 2.47°C score; no full-capacity or geometric equivalence to R5 is claimed. R5 remains the CAD-linked spatial model. This simplified plant omits radial contact location, individual covers/leads/seal, pan temperature gradients, food load dynamics, induction pickup and nonlinear material properties.

Body/glass temperatures are assumed independently measured perfectly and delivered without delay. Heating power means **absorbed pan power**, also known perfectly; commanded electrical power is not interchangeable with it. Those assumptions favor the observer. Power calibration, body-sensor offsets/delay and spatial measurement placement need a further measured study before production use.

Forward Euler runs at 1 ms. Sample/forcing discontinuities occur on the numerical grid. The test suite reruns all scenarios at 0.5 ms and requires each method's RMSE to change by less than 0.02°C. This demonstrates numerical stability of these results, not validation of the plant.

## Methods

1. **Raw RTD:** current reported RTD sample.
2. **Steady loss correction:** invert the declared reduced cap/RTD network at DC, using nominal Gpc=0.08, Gcr=0.10, Gcs=0.0007, Grs=0.0005 and Gcg=0.0003. The hidden support is approximated by measured body temperature. This supplies a varying boundary correction rather than a constant offset.
3. **Bandlimited lead:** low-pass the RTD with a 0.20 s time constant, calculate a causal backward derivative and low-pass it at 0.25 s. Add 1.15 s times that derivative to the steady-corrected filtered temperature. The 1.15 s lead is a declared trial setting, not an identified time constant or optimized design. It has no contact-detection authority.
4. **Bounded bank midpoint:** nine continuous, fixed-gain, three-state pan/cap/RTD observers with pan capacities 300/500/800 J/K and contact conductances 0.04/0.08/0.16 W/K. Each has the same nominal remaining reduced coefficients. RTD innovation gains are 0.7/3/8 s⁻¹ for pan/cap/RTD; integration is 5 ms. State coordinates are clamped to −20…400°C as an explicit numerical range. Report the midpoint of the minimum and maximum estimated pan temperatures. No candidate selection, learned tuning, reset observer or probabilistic inference is implemented. The min/max of these hypotheses cannot cover unmodeled physics by construction.

The plant has a dynamic support state absent from every observer. Neither held-out parameter combination appears in the bank, and the light/heavy scenarios use different power waveforms. The light pan lies outside the bank's capacity grid; that is an intentional extrapolation test. There is no training stage or fit on these outputs. The fixed trial settings were not retuned after these results.

## Inputs and fault meaning

Nominal heating is 900 W for 0–30 s, zero for 30–50 s, 1,200 W for 50–80 s, then 180 W. The light-pan forcing is 450+350 sin(t/7) W until 55 s, then 250 W; the heavy pan uses 1,250 W until 70 s then zero. Hot restart begins at pan/cap/RTD/support = 200/100/90/60°C and supplies zero power for 20 s then 300 W. All estimators initialize from the first RTD temperature, not hidden truth.

Ordinary body/glass trajectories are 25+0.15t and 25+0.4t °C. In the boundary-change case they step to 95/125°C at 45 s, with weaker support/body conductance. Deterministic RTD disturbance is A[sin(1.618k)+0.5cos(0.719k)]; the CSV's amplitude is A, so peak absolute disturbance can approach 1.5A. This is not a random or statistically representative noise model.

At 40 s the frozen cases hold the reported RTD value. One holds its timestamp too; the other increments timestamps correctly. In detach, the physical RTD remains initially warm but loses its pan path and subsequently cools. The independent contact input is deliberately wrong in that case. An electrical RTD window could remain normal.

The study's authorization predicate consumes independent contact/electrical inputs plus finite, nonfuture data with age ≤150 ms. It is not a production detector and is not an implemented hardware inhibit. There is no model-residual route that can turn an invalid contact input back on. Hot restart is purposely not hidden by a warmup exclusion: independent contact plus fresh data is insufficient to establish the initial temperature estimate.

An analytic test holds local cap temperature and required heat flow fixed: at cap180°C and heat flow0.65W, Gpc=0.05 gives pan193°C whereas Gpc=0.015 gives pan223.33°C. The same local rate does not determine pan temperature without contact knowledge. This is an instantaneous ambiguity, not a claim that all future plant trajectories are identical.

## Engineering decision

Carry raw, boundary-corrected and bandlimited-lead outputs into future calibration logs. Do not advance this particular untuned bank to firmware. First measure contact variation, support/body coupling, input power and startup behavior, then identify a small model on one cookware set and evaluate on a separate set. Retain physically plausible estimate ranges and a clear “estimate unavailable” condition; do not discard startup outliers to manufacture an accuracy claim.

The independent electrical fault/inhibit path and contact qualification remain separate. The existing dual-path RTD architecture detects electrical faults; it does not prove useful heat flow from the pan. Fresh-frozen, mechanically detached and conductive-debris cases need independent evidence, and no estimator here closes them. No physical response-time improvement, controller overshoot result or cooking release follows from this study.

## Reproduce

From this directory run `./run.sh`, then `./check_fault_mutations.sh`. They require only standalone Rust tools and POSIX utilities. No Cargo, installed extension, hardware or network is used. `run.sh` runs warning-denying compilation, tests, rustfmt and clippy before regenerating CSVs. It captures tests directly before formatting/copying; a failing test stops the runner. Its post-run receipt hashes source, runner and primary result files.

## Primary reference and local evidence

[Paesa et al., Adaptive Simmering Control for Domestic Induction Cookers (2011), author-hosted paper](https://webdiis.unizar.es/~glopez/papers/PaesaTIA2011.pdf) supports studying multiple thermal models and adaptive estimation. Its actual sensing architecture uses external infrared pan-wall measurements, and its control targets are simmering. It does not validate a through-glass PT100 cartridge or these gains. Our simple fixed bank is not a reproduction of its Multiple-Model Reset Observer.

Local documents consulted: R5 thermal `main.rs`/README and safety model/README, plus `docs/solutions/architecture-patterns/dual-path-rtd-fault-containment-2026-07-13.md`. Their identities are recorded in `references.sha256`; they are background evidence rather than executable inputs. No R5 source is imported or changed.
