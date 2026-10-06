# D-33 — HOT-side F6 bias and isolated mains zero crossing

**Native-21 source is implemented on the revised TCO-switched architecture;
the rail/switching qualification is split as the owner directed.** The final
machine-readable campaign summary and refinement results accompany this
report. This is source for owner layout, not a routed or bench-qualified board.

**Final modeled rail minimum margin: 78.6 mV**, with the least-negative
partner-edge voltage **−1.678614 V** against −1.6 V. All **7,972** rail cases
complete and pass. The six worst-case timestep refinements also pass.
See [qualification-summary.json](qualification-summary.json) for case names,
limits and complete evidence hashes.

| Rail campaign | Pass / total | Least-negative partner-window VSS |
|---|---:|---:|
| Full waveform screen at nominal components | 1,008 / 1,008 | −1.844578 V |
| Selected waveforms × 128 corners | 3,328 / 3,328 | −1.678912 V |
| −2.4 V current extraction, nominal screen | 52 / 52 | −1.844417 V |
| −2.4 V selected waveforms × 128 corners | 3,200 / 3,200 | −1.678614 V |
| Repeated 740 nC pulses, 33/80 kHz | 256 / 256 | −1.888341 V |
| Repeated pulses + 30 mA HOT load, 18 V span | 128 / 128 | −1.915819 V |

The branch is rebased onto `fada4c13c`, which contains the owner's split-F6
qualification decision and isolated LINE_ZC requirement. D-32, D-34 and D-35
are already merged by the owner; this change does not alter those tools or
firmware. In particular, it does not enable bursts or revert the B4
comparator-to-driver-output timing correction.

## Deliverables

- [Circuit source](../../../../../elec/src/power_stage_120v.ato), `f6_bias.ato`
  and `f6_parts.ato`: IRM-20-24 on TCO_L, direct low-side split, one SN6507,
  two HOT↔HOT transformers, shunt-regulated negative rails, damped local
  reservoirs, all-rail monitor → DIS, F6 gate networks and TPS709 HOT5.
- [Native-21 ECO](../../../../../native-21/ECO.md), exact part/footprint and
  net-delta inventory, plus identical compiler outputs in both `frozen/`
  and `native-21/frozen/`. No board file is added or changed.
- Reinforced VOL628A AC-input detector from L_FILT/N_FILT to **LINE_ZC at
  J4.16**, with a Schmitt output. The ECO records the three-return D-20
  allocation and its still-open harness/ground-offset qualification.
- Standalone Rust safety audit, including each gate's Cgs/negative bias/
  discharge orientation, three local references, all rail monitors through
  DIS, HOT-only bias power and the line detector's exclusive optocoupler
  boundary. Mutations exercise the actual exported netlist.

## Qualification method

The owner demonstrated 504/504 switching cases with a fixed −1.6 V rail,
worst off gate 1.741 V against 1.9 V. That run establishes the switching side
of the decomposition in DECISIONS.md. This branch additionally reruns all
504 decision/startup cases on both native-19 matrices at 27/100/150°C with
**the physical 1 Ω** discharge resistor and PMEG6030EP, still at fixed
−1.6 V: 504 pass, worst off gate **1.589109 V**. The old deck's 1.344827 Ω
compensation is not the circuit's 1 Ω resistor.

`edge_currents.py` observes both signed driver-output branch currents without
loading the switching circuit. Its 0.2 ns samples cover turn-off, the partner
edge and 0.75 µs afterward. The largest positive-only negative-rail charge
integral is 654.4 nC and the largest current is 7.057 A. This exceeds the
original 417 nC sizing estimate. A second run at −2.4 V on the 26 selected
stress cases finds 661.3 nC; all 26 switching cases pass. The implemented
power/repeated-pulse allowance is therefore **740 nC and 8 A**, and signed
waveform replays carry a further 10% current multiplier. The selection is the
union of worst rail response, current, charge and slew; all 1,008 original
case/rail combinations are first screened at nominal component values.

`rail_qualification.py` applies those waveforms to a standalone full TI
TLVH431 nonlinear macro, a finite source resistance and the actual reservoir
network. It crosses 128 component/model corners with the selected waveforms.
The source span is **15.5 V** for negative-rail droop, below the monitor's
normal enable window; **18 V** checks the upper shunt-current case with
30 mA of HOT protection load returning through the shared LS midpoint.
This brackets regulator tolerance/dropout effects more widely than treating
25°C nominal accuracy as a full-temperature specification.

The corner grid includes:

- polymer 140.8–316.8 µF, total damping resistance 0.67–1.1 Ω, 10 nH;
- local ceramic 10–24 µF, ESR up to 40 mΩ and ESL up to 0.5 nH;
- middle ceramic 1–2.4 µF, ESR up to 100 mΩ and ESL up to 0.5 nH;
- HF bank ≥320 nF, ESR up to 50 mΩ and **aggregate ESL ≤0.1 nH**;
- shared/single bank configurations, polymer leakage, gate hold-off and
  monitor loads; worst 0.1% feedback-resistor directions;
- shunt reference 1.2188 V, including the BQ full-temperature minimum and
  cathode-voltage coefficient allowance;
- macro gm ×0.5/2 and each pole ×0.5/2 sensitivity. These factors are
  **engineering sensitivities, not TI temperature/process limits**.

The nominal source is approximately −2.0 V. Stability comes from the
220 µF polymer **through 0.68 Ω**, per driver, in parallel with the fast
ceramic branches. The computed minimum phase margin is **51.62°**, versus
4–14° in the superseded candidate. Every unity crossing is considered.
Actual loop gain, effective capacitance and mounted ESL remain bench/layout
acceptance conditions. The source is not certified over unmeasured parasitics.

The rail verdict measures VSS relative to its MOSFET source over the partner
edge window, not only at a sampled instant. Periodic 740 nC pulses at
33/80 kHz exercise recharge and shared-LS loading over 4 ms. A positive
current-source DC operating point incorrectly holds an instantaneous Miller
pulse forever; the replay instead starts from the energized idle rail and
introduces the signed waveform after 50 ns. No waveform clipping or
smoothing is applied.

Some transients briefly reduce the shunt current essentially to zero; the
reservoir then supports the rail. The small-signal phase margin describes
the regulating operating point, not that cutoff interval. The nonlinear
transient model supplies the edge-voltage verdict. Maximum shunt current
across the final campaigns is **64.062 mA**, below the 70 mA design limit.

## Numerical checks and historical diagnostics

The final edge step is **50 ps**. `refine_rail.py` checks the three
least-negative corners of each final waveform campaign at 25 ps and rejects
differences above 5 mV. `qualification_summary.py` checks distinct case
counts, completion, finite rail measurements, rail/shunt limits and timestep
agreement before writing the final summary. That summary gives the actual
worst cases, completed counts and shunt currents.
The six 50-to-25 ps comparisons change the reported worst rail voltage by
at most **1 µV** at the simulator's printed precision; this is a numerical
agreement check, not a claim of physical voltage accuracy.

The originally coupled switching/shunt campaign remains in this directory
as diagnostic evidence: 181/504 cases were indeterminate, while every
completed case passed. Per the owner's 2026-10-06 decision, it is no longer
the source gate. `rail_campaign.py`, its old candidate decks/results and
KLU/iteration experiments describe that **superseded candidate**, not the
new damped reservoir. Their old source-hold verdict is superseded by the
separate qualification here.

## Supply sizing and physical limits

`native-21/bias_sizing.py` derives gate power from the Infineon datasheet's
234 nC typical reference at 10 V, then budgets the larger extracted charge.
It includes driver, bleed, monitor, HOT5 and operating-current allocations.
Transformer efficiency is budgeted at 70%; that is an allowance, not a
manufacturer minimum. The 21.6 W IRM-20-24 has adequate calculated capacity,
with a **9.592 W** allocation at 80 kHz, but enclosure-temperature derating
and LDO cooling must be verified.

`transformer_check.py` evaluates both transformers together at 23.3/24.7 V,
500/700 kHz and 85 mA per secondary, including rectifier models, hot winding
DCR, minimum filter L and maximum switch RON. Its committed results contain
output headroom, switch current, drain voltage, rectifier reverse voltage and
input power. The model does not include SN6507 startup control, magnetic
saturation/core loss or a manufacturer maximum leakage capacitance.
The four completed cases give ≥17.279 V rectified output, ≤0.46675 A switch
current, ≤50.429 V drain voltage and ≤89.478 V diode reverse voltage.

The ECO names the remaining physical checks: effective MLCC capacitance and
ESL; loop margin; high-side headroom and clock range; transformer startup,
flux and snubbers; current/temperature derating; monitor enable/brownout/
recovery behavior; the added DIS-OR timing; changed-loop FEM; D5 isolation;
and D-20 harness returns. These are not waived by a source/netlist audit.
The three new custom land patterns remain explicitly ReviewOnly pending
manufacturer-drawing review.

LINE_ZC's raw optocoupler edges are not guaranteed within ±250 µs of voltage
zero. The controller must infer phase from the continuous pulse train and
qualify timing on the bench. Bursts remain disabled until that firmware and
harness integration is complete.

## Reproduction

Use Miniforge Python 3.12 with NumPy/SciPy and ngspice 45.2. From repo root:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
PATH=/opt/homebrew/bin:$PATH /Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
cd zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33
/Users/bennet/Miniforge3/bin/python3 edge_currents.py --workers 8
/Users/bennet/Miniforge3/bin/python3 rail_qualification.py --loop --edges --workers 8
/Users/bennet/Miniforge3/bin/python3 edge_currents.py --bias=-2.4 --selected --workers 4
/Users/bennet/Miniforge3/bin/python3 rail_qualification.py --edges --waveforms edge-current-2.4V --output rail-deep-bias --workers 8
/Users/bennet/Miniforge3/bin/python3 rail_qualification.py --periodic --workers 4
/Users/bennet/Miniforge3/bin/python3 rail_qualification.py --hot-load --span 18 --output rail-hot-18V --workers 4
/Users/bennet/Miniforge3/bin/python3 refine_rail.py
/Users/bennet/Miniforge3/bin/python3 transformer_check.py
```

Then run `native-21/bias_sizing.py` from repo root and
`qualification_summary.py` from this directory. The full sampled waveform
archives and vendor models are ignored; regenerate them with the commands
above. The model fetchers verify their hashes. No licensed models are in Git.
The default extraction remains numerically identical after adding the
`--bias`/`--selected` CLI options; the original 504-case result records the
script hash used at measurement time.

From `zapote/power-stage-120v`:

```sh
uv tool run --offline --from atopile==0.2.69 ato build
uv tool run --offline --from atopile==0.2.69 python tools/circuit_export.py . build/resolved-components.json --entry-file elec/src/power_stage_120v.ato --entry PowerStage120V
rustc --edition=2021 --test audit.rs -o /tmp/d33-audit
/tmp/d33-audit
/Users/bennet/Miniforge3/bin/python3 native-21/verification/verify_source.py
```

Compiler outputs were copied into both frozen directories; source hashes
are checked in `native-21/verification/source-check.json`. Full project Rust
builds, PCB DRC and routing are outside this source-only task.

Manufacturer document revisions, pin contracts and footprint references are
collected in [ECO.md](../../../../../native-21/ECO.md). The shunt macro is TI
SLVM672 and the PMEG models are Nexperia; their download hashes are recorded
by the fetchers/results. Model accuracy and all engineering assumptions
remain explicit; none of these simulations is a measured PCB result.
