# D6 — off-gate remedies

**A proposed 1 Ω diode discharge branch plus 2.2 nF external Cgs is the best combined option tested without changing the bias supply: it reduces worst off-gate VGS from 4.285 to 1.918 V and worst die VDS from 531.373 to 464.776 V, while the matched positive overlap-energy proxies change by −31.2% to +15.4% in the outgoing window and −57.0% to +7.6% in the incoming window.**

These are model results at 27°C, not hardware qualification or a guaranteed hot-junction margin. The component additions are proposals only. [Criterion and topology](criterion-and-topology.md) explains the finite diode model, package-terminal Cgs, missing negative rail and absence of an active Miller-clamp output. [Method](method.md) defines measurement windows, identities and model limitations. [All per-case tables](tables.md) give the requested voltage and energy values for every remedy; [summary.json](summary.json) contains the reproducible aggregate and baseline deltas.

## Criterion first

The IPW65R018CFD7 Rev.2.0 datasheet gives a 3.5 V threshold minimum at 25°C, but no guaranteed minimum or coefficient at the maximum rated 150°C. Its typical hot transfer curve is not such a guarantee. Thus the historical <3.0 V rule cannot establish a 0.5 V hot margin. Retain it for comparison only; qualify a hot gate/current acceptance limit on real devices. A ≤0 V screen is an engineering target, not a vendor threshold. The selected passive combination does **not** meet that stronger screen; −4 V bias does, at the cost of a new supply arrangement and without solving S4 VDS by itself.

## Matched results

Each row attempts the same 16 decision cases, both directions, ESL10nH. The numeric maxima exclude aborted simulations, whose count is explicit. Every variant retains ZVS in all six S1 cases at 348ns. All valid die VGS extrema remain within the historical ±30 V transient criterion. “VDS fail” uses 520 V except S2's 585 V. Energy ratios are against the matched corrected baseline, not ratios of unrelated worst cases.

| Variant | Worst off VGS V | <3 V cases /16 | ≤0 V screen /16 | Worst VDS V | VDS fail | Abort | Eoff ratio range | Eon ratio range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 4.285 | 7 | 0 | 531.373 | 1 | 0 | 1.000–1.000 | 1.000–1.000 |
| roff1 | 2.285 | 16 | 0 | 531.975 | 1 | 0 | 0.665–1.158 | 0.557–1.242 |
| roff2 | 2.677 | 16 | 0 | 531.688 | 1 | 0 | 0.688–1.093 | 0.491–1.251 |
| cgs1n | 4.904 | 7 | 0 | 483.322 | 0 | 0 | 0.822–1.007 | 0.699–1.713 |
| cgs2p2n | 4.780 | 6 | 0 | 464.789 | 0 | 1 | 0.808–1.113 | 0.588–1.461 |
| cgs4p7n | 4.974 | 0 | 0 | 437.020 | 0 | 0 | 0.836–1.188 | 0.532–1.572 |
| neg2 | 1.429 | 16 | 8 | 529.230 | 1 | 0 | 0.672–1.069 | 0.580–1.331 |
| neg4 | -1.081 | 16 | 16 | 529.236 | 1 | 0 | 0.514–1.094 | 0.583–1.135 |
| roff1_neg4 | -2.546 | 16 | 16 | 529.784 | 1 | 0 | 0.282–1.243 | 0.488–1.059 |
| roff1_cgs1n | 2.974 | 16 | 0 | 486.087 | 0 | 0 | 0.650–1.206 | 0.510–1.179 |
| roff1_cgs2p2n | 1.918 | 16 | 0 | 464.776 | 0 | 0 | 0.688–1.154 | 0.430–1.076 |

`roff1/roff2` retain the 3.9 Ω charging resistor and add the finite diode plus 1/2 Ω branch in parallel; these are branch resistances, not exact effective Rg_off. `cgs*` adds package-terminal capacitance to both devices. `neg*` retains +15 V on and supplies −2/−4 V off. Combined names add those changes together. The 2.2 nF standalone S2/DIR1 run aborted at 2µs with “Timestep too small”; it was retained, not repeatedly retried or counted as a pass.

The 1 Ω branch alone fixes the historical gate criterion with 0.715 V margin, but S4 VDS remains 531.975 V. The 1 nF combination clears both criteria with only 25.6 mV gate margin, making it a weak choice before tolerances. The 2.2 nF combination has 1.082 V margin to the historical 3 V criterion and 55.224 V to the S4 520 V criterion. Those are arithmetic margins in this model, not hot or manufacturing bounds. Combining 1 Ω with −4 V gives the strongest gate suppression tested (worst −2.546 V), but retains a 529.784 V VDS excursion and needs a different supply arrangement.

The selected 2.2 nF combination's costs are visible rather than assumed:

- S4 DIR0 positive incoming-window pair overlap falls from 792.184 to 742.467 µJ; die VDS falls from 531.373 to 464.776 V.
- S2 DIR0 die VDS **rises** from 340.303 to 427.337 V, still below its 585 V criterion; incoming-window overlap rises from 74.467 to 80.117 µJ. Faster discharge does not improve every stress.
- Extra Cgs slows the gate response, but does not lose S1 ZVS at 348ns in the tested grid. Standalone Cgs leaves or worsens off-gate failures; the 4.7 nF standalone variant fails the gate criterion in all cases.
- Gate-driver/supply dissipation, a qualified diode's reverse recovery and current rating, capacitor tolerance/ESL/ESR and added trace inductance are unmodeled costs. The 3.9 Ω path remains conducting during turn-off, so the bypass diode is not an ideal selector.

This is a choice among the tested combinations, not an exhaustive optimum. Negative bias plus capacitance, an external clamp circuit and altered turn-on slew remain outside this bounded brief. The board's UCC21550BDWKR lacks a powered active Miller-clamp output; the datasheet's UVLO clamp is not one.

## Baseline and evidence checks

Grid v2 used the uncorrected lin12 matrix, while the brief names the crop-corrected matrix. Both are preserved: 16 original baseline replays differ from grid v2 by at most 0.000100 V in peak VDS, 0.000001 V in off-gate VGS and 0.000008 V in incoming VDS. Twelve cases match all three metrics exactly; four differ in the last digits. `summarize.py` asserts a 0.00011 V replay tolerance and records every delta. On changing only to the corrected matrix, peak VDS shifts −2.5932 to +0.5824 V and off-gate peak shifts −0.035733 to +0.010188 V. Every remedy comparison uses that corrected baseline.

The sweep has 176 corrected decision attempts (one numerical abort), plus the 16 original-baseline checks. Complete raw simulator logs and parameter files are committed. The selected representative S1/S4 baseline and combination have bounded compressed waveform evidence and a 0.1ns refinement check in [waveforms](waveforms/); its [audit](waveforms/audit.json) records the actual voltage changes. For the selected S4 DIR0 combination, 0.2→0.1 ns changes die VDS 464.7763→462.5763 V and off-gate VGS 1.918047→1.913382 V; the conclusion is unchanged. Independent integration is checked against `.meas`, and the low-side terminal/die-port current discrepancy is recorded. Numerical agreement does not validate recovery physics or hot behavior.

## Reproduce

From the repository root, first fetch/hash-check the licensed model and run the kit smoke check:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
```

Then enter this output folder. The minimal independent replay preserves committed results and cleans its temporary directory:

```sh
python3 replay_one.py --case roff1_cgs2p2n_S4_v198_i-20_d0_dt348
```

Full study (sequential runs, no workspace/Rust build):

```sh
python3 run_study.py --original --variants baseline
python3 run_study.py --variants baseline,roff1,roff2,cgs1n,cgs2p2n,cgs4p7n,neg2,neg4
python3 run_combinations.py --variants roff1_cgs1n,roff1_cgs2p2n,roff1_neg4
python3 summarize.py
python3 probe_waveforms.py
```

Fresh runs write fresh execution identities; `--resume` reuses only matching matrix/model/runner/options, parameters and deck bytes. Keep the historical failed row as evidence; numerical reproducibility of that failure is not hardware evidence. Python scripts only orchestrate the existing SPICE instrument and summarize its measurements; no new production engineering rule or board change is introduced.

Import-boundary and report-only regeneration checks passed; see [import-check.log](import-check.log) and [regen-check.log](regen-check.log). Firmware tests are not applicable to this isolated evidence change, and no Rust/workspace build was run. D8 should use this as a proposal-selection result and explicitly measure hot current, terminal VGS/probe error, actual gate dead time, bias startup and S4 recovery before any acceptance claim.
