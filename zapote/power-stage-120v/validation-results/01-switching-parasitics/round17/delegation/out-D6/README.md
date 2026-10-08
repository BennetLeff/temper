**The preferred tested proposal is a ≈1 Ω discharge path plus 1 nF external Cgs and −2 V turn-off bias: across both matrices its off-gate peak is 0.512 V and die VDS is 483.77 V, with nominal ZVS retained and overlap energy down 2.9–51.2%, at the cost of a 17 V drive span and added diode/resistor/capacitor; the 1.9 V hot screen still needs qualification.**

## Method

D-6 is a simulation-only proposal. No board, netlist, original deck, or existing round-17 result was edited. The exact D2 driver approximation, L1 MOSFET model, solver options and 10 nH capacitor ESL remain in use. [run.py](run.py) copies the original deck and changes only the remedy; additional `.meas` statements measure energy without changing circuit topology. The existing `run_d2.matrix_params` and sim-kit `run_ngspice.run` are reused unchanged.

Each proposal covers both directions for S1 at 170/198/280 V, 37 A, 307/348 ns; S2 at 280 V, 71 A, 348 ns; and S4 at 198 V, −20 A, 348 ns. Both the crop-corrected linear and curved-extrapolation matrices are exercised. Default transient temperature is ngspice's 27 °C, matching grid v2; the hot study below is a separate DC threshold exercise, not a hot switching campaign.

The grid-v2 baseline uses its original **uncorrected** linear matrix; the proposed remedies use the **corrected** matrices required by the brief. Do not compare a corrected baseline to grid v2 as if their matrices were identical. [baseline-comparison.json](baseline-comparison.json) checks all sixteen same-case original-matrix rows: maximum off-gate difference 0.000001 V and VDS difference 0.0001 V; all ZVS classifications agree. The differences are last-digit measurement rounding. Provenance files record input/deck/model hashes, source revision, Python and ngspice versions, and invocation. The licensed vendor library is excluded.

## Criterion at hot junction

[Infineon IPW65R018CFD7, Rev. 2.0, 2021-04-19](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf), p. 5 Table 4, specifies VGS(th) = 3.5 V minimum at **25 °C**, VDS = VGS and ID = 2.91 mA. Page 3 Table 2 permits junction temperature up to 150 °C. Page 9 Diagram 9 shows typical transfer curves at 25/150 °C; it supplies neither a guaranteed hot minimum nor a guaranteed threshold temperature coefficient. Thus **3.0 V is optimistic as a hot acceptance rule**: its claimed 0.5 V margin cannot be carried from 25 °C to hot junction.

The unmodified vendor L1 model, tested with the same threshold test condition, gives 4.062434 V at 25 °C and 2.987940 V at 150 °C: a −1.074494 V change, averaging −8.595952 mV/°C. The recommended provisional screen is **off-gate peak < 1.9 V**: 3.5 V minus the model's 1.074494 V thermal change minus the existing 0.5 V allowance gives 1.925506 V, rounded downward. This extrapolation is an **engineering screen, not a production minimum or guaranteed bound**. A guaranteed limit needs vendor minimum-hot-threshold data or a validated process/temperature characterization plus measurement uncertainty. Threshold is itself a milliampere test, not the onset of destructive shoot-through.

[threshold.py](threshold.py), [threshold.cir](threshold.cir), [threshold.json](threshold.json) and [criterion.json](criterion.json) reproduce that estimate. Extra `dVth=-0.5` probes are retained solely as a model-parameter sensitivity: the model parameter does **not** shift the measured threshold volt-for-volt and those rows are not a minimum-spec device.

## Proposals and supply feasibility

- **Split off1 / off2:** retain the existing 3.9 Ω path and add a parallel discharge-only diode plus resistor. Resistor values 1.344827586 Ω / 4.105263158 Ω give asymptotic parallel targets of 1 Ω / 2 Ω. A generic Schottky (`Is=1 µA, N=1, Rs=0.05 Ω, Cjo=20 pF, Tt=0`) is included, so diode forward drop makes the actual off resistance higher than the target at low current. The diode conducts from the gate-side resistor node toward the driver. These are **topology candidates, not selected/orderable diode parts**; diode tolerance, recovery, package inductance and new routing need verification. Existing Rg_on stays 3.9 Ω.
- **Cgs:** ideal 1 / 2.2 / 4.7 nF across each MOSFET's external gate/source pins. Package leads remain inside the vendor model. Capacitance adds charge to both edges; no new capacitor/routing ESL or ESR is claimed. At 15 V swing, added gate charge is 15 / 33 / 70.5 nC per gate and drive energy is 0.225 / 0.495 / 1.0575 µJ per complete charge/discharge cycle (`C ΔV²`), before driver losses.
- **Negative bias:** the low output level is −2 / −4 V relative to the MOSFET source, with the high level held at +15 V; the driver command, on resistance and other circuit elements stay unchanged. This models ideal 17 / 19 V output supply spans. The frozen netlist ties U1 VSSA (pin 14) to `sw_a`, VSSB (pin 9) to `leg_ret`, VDDA (pin 16) to the bootstrap rail, and VDDB (pin 11) to `v15_ls`: the board has no independent negative rail. Implementing this result requires a bias/gate-network redesign, not a firmware setting.

[TI UCC21550, SLUSE89C, August 2024](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), pp. 34–36 Figures 8-2/8-3/8-4, supports negative bias using split isolated bias, separate positive/negative supplies, or a single-supply Zener gate network. The latter can retain bootstrap operation but has duty-cycle/startup limitations; it is not represented by our stiff negative source. Separate regulated negative supplies are one implementation, **not the only one**. Holding +15 V while adding −2/−4 V needs 17/19 V total swing; a split of the existing 15 V supply reduces the positive level. Page 38 §8.3 gives 25 V recommended maximum output supply span.

**Active Miller clamp: skipped.** The UCC21550BDWKR has no active Miller-clamp terminal/function (TI Rev. C pp. 3–4 Table 4-1 and p. 24 §7.3.4). Its UVLO pull-down clamp is not an active gate Miller clamp during normal switching. Adding an external clamp would exceed the brief's permitted clamp variant.

## Results and costs

[Per-remedy decision tables](TABLES.md) contain a table for every individual remedy and combination, with separate linear/curved values and both-direction envelopes. Every row reports off-gate, die VDS, outgoing/incoming overlap energy, whole-event energy, and ZVS. Full direction-specific measurements and ngspice logs are in [raw/](raw/); machine-readable aggregate results are in [summary.json](summary.json).

| Variant | Off-gate max V | Die VDS max V | <1.9 V cases | VDS pass | ΔEΣ vs matched baseline |
|---|---:|---:|---:|---:|---:|
| baseline | 4.399 | 531.37 | 0/32 | 31/32 | 0.0% … 0.0% |
| off1 | 2.245 | 531.91 | 28/32 | 31/32 | -39.6% … -0.2% |
| off2 | 3.050 | 531.61 | 28/32 | 31/32 | -32.8% … -0.2% |
| c1 | 5.015 | 483.32 | 0/32 | 32/32 | -23.1% … 11.8% |
| c2p2 | 4.850 | 464.79 | 0/31 | 31/31 | -30.4% … 18.4% |
| c4p7 | 4.996 | 437.02 | 0/32 | 32/32 | -30.6% … 28.8% |
| neg2 | 1.540 | 529.23 | 32/32 | 31/32 | -38.7% … -0.4% |
| neg4 | -0.978 | 529.24 | 32/32 | 31/32 | -40.8% … -0.6% |
| off1_neg2 | -0.327 | 530.08 | 32/32 | 31/32 | -47.3% … -0.6% |
| off1_neg4 | -2.560 | 529.56 | 32/32 | 31/32 | -67.1% … -0.8% |
| off1_c1 | 3.013 | 486.13 | 28/32 | 32/32 | -39.3% … -2.6% |
| off1_c1_neg2 | 0.512 | 483.77 | 32/32 | 32/32 | -51.2% … -2.9% |
| c1_neg2 | 2.224 | 480.74 | 30/32 | 32/32 | -36.2% … -2.9% |
| c1_neg4 | -0.295 | 479.17 | 32/32 | 32/32 | -45.8% … -3.2% |

Envelopes above include both matrices and both directions; VDS acceptance is 520 V except S2's 585 V. The 2.2 nF-only variant has one aborted case, so its 31 completed cases are not full coverage. All completed variants preserve 12/12 nominal S1 ZVS checks. All successful transient runs remain within the ±30 V dynamic gate rating.

The preferred candidate's EΣ proxy falls by **2.9–51.2%** across matched cases; its added capacitor costs **17 nC and 0.289 µJ per gate per full 17 V charge/discharge cycle**, plus diode/resistor and bias-supply losses not included in EΣ. A simpler **1 nF + −4 V** proposal also passes all 32 cases: max off-gate −0.295 V, max die VDS 479.17 V, EΣ down 3.2–45.8%. It avoids the split resistor but needs 19 V total drive span. The preferred proposal limits the negative rail to −2 V and gives stronger discharge; the owner can choose between those hardware costs. **1 nF + −2 V without fast discharge fails the hot screen** at 2.224 V. No globally optimal parts/supply implementation is claimed.

The curved-matrix S4 case also exposes the danger of judging only the linear matrix: off2 rises past the old 3 V screen to 3.050 V, and off1+Cgs1 nF reaches 3.013 V.

Energy is `∫ max(0, VDS_die × ID_die-terminal) dt`. Die terminal current is the voltage across the model's drain resistor divided by its 74.4 µΩ value. Eoff integrates the outgoing device from T1 to T1+DT; Eon integrates the incoming device from T1+DT to T1+DT+0.75 µs. EΣ sums both devices over both windows. This includes capacitive/diode energy and finite conduction tails; it is a consistent **overlap proxy**, not pure channel heat or measured switching loss. Signed recovered energy is deliberately not subtracted. No extrapolation to full-bridge average watts is made.

The combined −2 V / 1 Ω / 1 nF candidate retains ZVS at all nominal 348 ns decision points and gives **1.388 V simulated margin to the provisional 1.9 V screen**. Its largest VDS is 36.23 V below the 520 V S1/S4 screening limit. Neither is a guaranteed hardware margin.

The individual remedies separate two problems. Fast discharge or negative bias suppresses off-gate excursions but leaves the linear-matrix S4 VDS violation. Cgs reduces S4 VDS but prolongs gate discharge and worsens the 307 ns peak. Cgs alone still achieves nominal 348 ns ZVS in these cases; that does not make its off-gate failures acceptable. The curved matrix can move a marginal result across a criterion; both matrices must remain in the decision.

## Verification and numerical limits

The canonical records contain **448 decision runs** (14 variants × 16 cases × 2 matrices), **16 baseline-reproduction runs**, and **32 timestep-refinement runs**, plus four DC threshold probes. The 0.2 ns decision sweep has one abort: `lin_c2p2_S2_v280_i71_d1_dt348_step0.2`, timestep too small at 2 µs. It is indeterminate, not a pass. No solver option or model edit was used to hide it.

Halving the maximum timestep to 0.1 ns for baseline and the preferred candidate at high-bus S1, S2 and S4 yields **21 completed / 11 aborted** cases. On the 21 completed pairs, maximum differences are 0.009501 V off-gate, 2.2284 V VDS and 0.313% EΣ; all screen/ZVS classifications agree. All S4 refinement runs complete, including the preferred candidate on both matrices. The remaining aborts occur at 2 µs and are retained in [refinement-comparison.json](refinement-comparison.json) and raw logs. **Full timestep convergence is not established**. This is a promising proposal with explicit numerical limitations, not qualification.

[smoke-test.log](smoke-test.log): sim-kit smoke PASS after the prescribed hash-checked vendor restore. [import-linter.log](import-linter.log): import gate PASS, 5 contracts kept / 0 broken using isolated audit tooling, no project dependency synchronization. [regen-check.log](regen-check.log): all derived artifacts consistent. The report-only regeneration check was used because the requested output boundary forbids rewriting other repository artifacts. No Rust workspace or native bridge was built.

## Reproduce

From the repository root, restore the model and verify the environment before any simulation:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
cd zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D6
/Users/bennet/Miniforge3/bin/python3 run.py
/Users/bennet/Miniforge3/bin/python3 run.py --variants baseline --matrices v2 --workers 2
/Users/bennet/Miniforge3/bin/python3 combinations.py --workers 2
/Users/bennet/Miniforge3/bin/python3 supply_combinations.py --workers 2
/Users/bennet/Miniforge3/bin/python3 threshold.py
/Users/bennet/Miniforge3/bin/python3 refine.py --step .1 --workers 2
/Users/bennet/Miniforge3/bin/python3 analyze.py
```

The scripts do not reuse cached results; each requested invocation runs fresh. Every ngspice abort is retained as a failed/indeterminate case. The original matrix values, generic remedy assumptions and deck settings are fixed by committed inputs. `run.py` removes licensed model copies from output directories immediately after each run; the original vendor library remains ignored in the sim-kit model folder.

## Limits and owner decisions

- Select the negative-bias implementation and real discharge diode; no modification is authorized by this simulation report. Confirm +15 V on level, startup/disabling behavior, duty-cycle range and supply UVLO before accepting the proposed bias.
- Obtain a guaranteed hot VGS(th) minimum or measured device-population evidence. The 1.9 V screen uses a typical model thermal trend and does not certify hot false-turn-on immunity. The transient sweep itself uses the grid's nominal temperature.
- Validate the S4 recovery waveform and gate excursions in D-8 before a board decision. Gate-drive proposals do not establish that the L1 recovery snap-off matches hardware.
- The stiff supplies, generic diode, ideal Cgs, fixed 5 Ω/0.55 Ω driver approximation, leg-A-only extraction, capacitor ESL assumption, crop/extrapolation uncertainty and omitted bulk-to-gate mutuals remain limits. All cases here use ESL 10 nH; the report does not supersede the wider D2 grid or the pending D-7 capacitor evidence.
- Dead time here is the D2 command separation, not an independently qualified firmware-to-gate interval; D-5 owns the actual timing determination. There is no claim that the firmware's ≥500 ns comment makes the 307 ns case irrelevant.
