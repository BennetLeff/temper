# D2 — gate-driver model audit

**The deck matches TI's typical DC resistances, but misses the transient pull-up boost and is not a worst-case driver model; the requested S1/S2/S4 reruns do not remove S4's hard-turn-on concern.**

## Datasheet evidence

[TI UCC21550, SLUSE89C, revised August 2024](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), including UCC21550BDWKR:

| Parameter | Min | Typ | Max | Conditions and printed page |
| --- | --- | --- | --- | --- |
| DC pull-up resistance | — | 5 Ω | — | −50 mA, §5.8 p.10 |
| Pull-down resistance | — | 0.55 Ω | — | +50 mA, §5.8 p.10 |
| Peak source/sink current | — | −4/+6 A | — | CVDD 10 µF, CL 0.22 µF, 1 kHz; §5.8 p.9 |
| Output rise | — | 8 ns | — | CL 1.8 nF, VDD 12/25 V, 20–80%; §5.9 p.10 |
| Output fall | — | 8 ns | — | Same load/supplies, 90–10%; §5.9 p.10 |
| Propagation, either edge | 26 ns | 33 ns | 45 ns | Input 100 ns/500 kHz; VIH→output 10% or VIL→90%; §5.9 p.10 |

General table conditions: VCCI 3.3/5 V, VDD 12 V for B, junction −40 to 150°C, unloaded unless overridden. Blank min/max cells are **not guarantees**.

§7.3.4 / Figure 7-2, p.24 describes a PMOS pull-up plus transient NMOS assist (approximately 1.47 Ω). The parallel equivalent is 1.136012 Ω; its timing/output dependence is not specified. Figure 5-13, p.14 shows typical resistance versus temperature, not production bounds.

## Method and model limits

This evidence starts at source revision `67aec36f8`; all scripts/decks/logs are confined to this folder. The frozen BOM identifies U1/U2 as UCC21550BDWKR and R10/R12/R18/R20 as RC1206FR-073R9L. No board/netlist/datasheet identity contradiction was found in those checked identities; this is not a complete connectivity audit.

`run_cases.py` loads the existing `round17/d2/run_d2.py`, reuses its matrix reader, parameter conversion and common ngspice runner, and points the runner at [the copied deck](leg_matrix.cir). Changes to that deck are only a parameter for the previously literal command ramp and a measurement proving the end of the measurement window was reached. The copied behavioral stage still linearly blends pull-up/pull-down conductances, without current saturation, clamps, UVLO, interlock, or internal propagation. It is not a TI transistor-level macromodel.

[Provenance](provenance.json) records source/input SHA-256 values, runtime, parameters and completed status. All main runs require a zero exit, no aborted/failed measurement, every required measurement, and completion through 3.098 µs. [Model hash verification](model-fetch.log) and [the shared kit smoke test](smoke.log) passed before simulations. Licensed models are not committed.

| Variant | ROH | ROL | Full command ramp | Interpretation |
| --- | --- | --- | --- | --- |
| baseline | 5 Ω | 0.55 Ω | 5 ns | Original D2 approximation |
| boost | 1.136012 Ω | 0.55 Ω | 5 ns | Static equivalent of TI transient parallel pull-up; **sensitivity only** |
| weak_sink | 1.136012 Ω | 0.75 Ω | 5 ns | Rounded-up hot typical-curve estimate from Figure 5-13; **not guaranteed maximum** |
| slow_edge | 1.136012 Ω | 0.75 Ω | 10 ns | Assumed doubled command ramp; **not a TI timing corner** |

The boost remains active throughout the high command, unlike TI's brief assist. Its effect on the tail of gate charging and initial bias means the comparison cannot isolate a physically exact transient boost. The peak-current table entries are typical measurements under a separate capacitive-load condition, not hard clipping specifications. Neither resistance nor edge time has a guaranteed worst-case limit; consequently **the requested guaranteed weakest pull-down / slowest turn-off case cannot be constructed from this datasheet**. These directional sensitivities keep that gap visible instead of inventing a limit.

`DT=348 ns` remains the command separation in every case; this audit does not redefine it as guaranteed hardware dead time. Propagation is not added independently to the commands, which could double-count timing studied in D1. S1=(170 V,37 A), S2=(280 V,71 A), S4=(170 V,−20 A); DIR=0, capacitor ESL=10 nH, shunt=2 nH, max step=0.2 ns. Every before/after uses the same matrix, load, external gate resistance and other deck parameters.

## Results

[Full 24-row comparison](comparison.md), [complete measurements and parameters](results.json), and `runs/*/{params.inc,run.log}` provide all S1/S2/S4 results on both requested matrices. Values below are simulations, not hardware measurements.

| Matrix / case | Baseline LS VDS peak → boost (V) | Baseline LS off VGS peak → boost (V) | Baseline residual LS VGS at partner → slow_edge (V) |
| --- | --- | --- | --- |
| 1 mm / S1 | 195.009 → 195.053 | 2.167 → 2.186 | 2.167 → 2.597 |
| 1 mm / S2 | 355.173 → 355.110 | 3.048 → 3.061 | 3.048 → 3.509 |
| 1 mm / S4 | 542.712 → 551.184 | 4.429 → 4.650 | 1.185 → 1.312 |
| lin12 / S1 | 191.897 → 191.907 | 2.202 → 2.217 | 2.202 → 2.600 |
| lin12 / S2 | 339.721 → 339.788 | 3.120 → 3.137 | 3.120 → 3.636 |
| lin12 / S4 | 536.727 → 560.064 | 4.566 → 4.851 | 1.197 → 1.323 |

S1/S2 incoming HS die VDS is near zero before its command. Their largest off-window LS gate value occurs at the start of that window and includes residual turn-off charge: it must not automatically be called a later false-turn-on rebound. S4 starts the incoming HS with roughly the bus voltage across it; the later LS gate rebound exceeds its value at the partner command. Both matrices retain that hard-turn-on condition, with higher S4 VDS/off-gate peaks under the static boost. These results support neither hardware signoff nor dismissal of the original failure; D3's recovery validation and D4's matrix interpretation remain independent dependencies.

[The timestep check](refinement.json) reruns S4/boost at 0.1 ns: LS VDS peaks are 550.0276 V (1 mm) and 558.5389 V (lin12), versus 551.1842/560.0635 V at 0.2 ns. Gate rebound is 4.649385/4.848659 V versus 4.649924/4.850633 V. This small change retains the comparison direction; it is not a proof of full convergence for every variant.

## The 5 ns command ramp is not an 8 ns output edge

[Load-only characterization](driver_load.cir) applies exactly the same behavioral output expression to 1.8 nF at 12 V, without external gate R or board L. [Measured times](load-results.json), in ns:

| Variant | Rise 20–80% | Fall 90–10% |
| --- | --- | --- |
| baseline | 12.47664 | 3.928879 |
| boost | 3.848001 | 4.269889 |
| weak_sink | 3.870858 | 4.845547 |
| slow_edge | 6.291428 | 8.146593 |

The baseline misses the stated typical load response in opposite directions. The static boost also does not reproduce it. A command ramp is an input to this surrogate, not an independently specified physical output edge; replacing it with the table's 8 ns would not constitute calibration. The doubled-ramp sensitivity happens to approach the typical fall time but does not validate the rising edge or temperature/process extremes.

## Gate resistor inductance

The [exact Yageo RC1206FR-073R9L specsheet](https://yageogroup.com/component-documentation/download/specsheet/RC1206FR-073R9L), p.1, identifies 3.9 Ω, 1%, thick-film 1206 and publishes **no parasitic inductance**. The repository's archived Yageo RC1206 V.2 (2004-09-03), `../../05-resonant-tank-envelope/sources/rc1206.pdf` relative to round17, also provides no such specification. No Yageo-specific inductance guarantee was found in these sources.

For an explicitly generic estimate, **2 nH per 1206 thick-film chip** is the typical value in Fluke, *Flexible RCL testing under actual operating conditions*, copyright 1995, publication B0296A-19U9510/NL EN, **p.2 Table 2** ([original application note hosted by UBC](https://courses.ece.ubc.ca/elec391/an_rcl.pdf)). It is not a characterization or upper bound for this Yageo ordering code. Figure 1 / p.1 treats the chip as a resistor plus series inductance with parallel capacitance and explains mounting dependence.

The requested driver comparisons leave resistor L unchanged. The FEM shorted the resistor pads at closures; a complete model should replace the artificial connection with a consistently referenced package representation, not blindly add the whole generic 2 nH on top of whatever closure inductance remains. That partition needs an extraction/port-reference check. Thus **2 nH is a package-level estimate, not a measured incremental ESL for this matrix**.

## Reproduction and validation

From the repository root, with ngspice on PATH (the measured executable was ngspice 45.2):

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
OUT=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D2
/Users/bennet/Miniforge3/bin/python3 "$OUT/run_cases.py"
/Users/bennet/Miniforge3/bin/python3 "$OUT/run_load.py"
/Users/bennet/Miniforge3/bin/python3 "$OUT/refine.py"
```

Run these sequentially. The wrappers retain parameters/logs and remove copied licensed libraries from result folders after each case. The vendor directory remains ignored. `run_cases.py` regenerates `comparison.md` and records a new source revision/hash set; source PDFs are identified by URL and SHA-256 in `sources.json`. The load and timestep probes are supplemental, not a calibrated replacement model.

Repository checks: `PYTHONPATH=packages/temper-placer/src .venv/bin/python scripts/import_linter_gate.py` passed (5 kept, 0 broken; [log](import-check.log)); `make regen-check` passed ([log](regen-check.log)). The isolated environment needed only `import-linter` and `PyYAML`; no workspace sync, firmware/Rust build, FEM rerun, or generated-artifact rewrite was performed. Firmware tests are not relevant to this evidence-only change.
