# Task 01 round 2 — complementary-drive model check

- Board reference: `native-13/section.kicad_pcb`, SHA-256 `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.
- Vendor model: Infineon `IPW65R018CFD7_L1`, library SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`. The library is fetched by the existing kit and is not committed here.
- Tool: ngspice 45.2 with the kit's PSpice mode and solver options; [smoke output](outputs/smoke-test.txt) confirms 16/16 checks passed.
- Evidence class: **simulation/model-based reference cases**. The circuit uses the starter kit's example inductances, not extracted native-13 loop values.
- Verdict: **complementary timing mechanics checked; native-13 switching verdict still BLOCKED** by the missing board parasitics and capacitor ESL described in the [first-round report](../README.md).

## What changed in the model

The [new deck](complementary_leg.cir) has two MOSFETs driven in opposite states. `DIR=0` turns the low side off at 2 µs and the high side on after `DT`; `DIR=1` reverses the sequence and load-current sign. Each 15 V output stage uses the runbook's 5 Ω source and 0.55 Ω sink values, with a 5 ns command ramp. A continuous behavioral current source blends those conductances during that ramp; an ideal switched-resistor version stalled ngspice at 2.00253 µs, so this is an output-stage approximation rather than a TI driver transistor model. Both gates have a 10 kΩ gate-to-source hold-off. The low-side driver returns after board `LCS`, and the high-side driver returns to its own source pin. The Infineon model already contains the TO-247 package inductances.

The other kit defaults remain explicit **reference inputs**: VBUS 198 V; LD_HS, LS_HS, LD_LS and LS_LS each 4 nH; LCAP 3 nH; LBULK 30 nH; LCS 1 nH; LG 20 nH; 1 nF per-device snubbers. The load is an ideal current source ramped from zero, at 27 °C model temperature. The tank waveform, gate-driver propagation and actual board inductances are absent.

## Results

All ten runs, comprising six direction/current/deadtime configurations and four half-timestep repeats, returned zero from the measurement and raw-waveform ngspice processes. Every required measure was present, the raw waveform reached the requested stop time, and the full logs and [compressed commutation waveforms](outputs/runs/) are retained. The [checker](run_reference_cases.py) verifies complementary command states, no simultaneously high commands, the exact measured command gap, raw-versus-`.meas` peaks and waveform duration. [Machine-readable results](outputs/reference_cases.json) contain the inputs, source hashes and each case's measurements.

| Reference case | Direction | Command gap | Incoming die VDS 1 ns before command | Incoming die VDS at its gate's 3 V crossing | Low VDS for 20 ns before command? | Die-gate overlap above 3 V |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 37 A, 348 ns | LS → HS | 348 ns | −0.85 V | −0.87 V | yes | 0 ns |
| 37 A, 348 ns | HS → LS | 348 ns | −0.87 V | −0.88 V | yes | 0 ns |
| 2 A, 348 ns | LS → HS | 348 ns | 195.5 V | 195.0 V | no | 0 ns |
| 2 A, 348 ns | HS → LS | 348 ns | 195.5 V | 195.1 V | no | 0 ns |
| 37 A, 250 ns | LS → HS | 250 ns | 177.6 V | 14.6 V | no | 19.6 ns |
| 37 A, 250 ns | HS → LS | 250 ns | 177.3 V | 16.2 V | no | 23.4 ns |

“Low VDS” means **absolute incoming die VDS ≤5% of the 198 V bus at every saved point for 20 ns before its command**. The 3 V gate and 5% bus thresholds are model diagnostics, not validated MOSFET conduction thresholds or a project ZVS acceptance rule. Gate voltage above 3 V on both devices does not by itself prove simultaneous channel conduction. The 250 ns cases show why commanded deadtime and die-gate overlap must be examined separately. These reference results establish that the deck can distinguish a completed commutation at 37 A/348 ns from an unfinished one at 2 A/348 ns; they do not establish the minimum ZVS current on native-13.

The 0.2 ns versus 0.1 ns runs check both device VDS peaks for the 2 A/348 ns and 37 A/250 ns cases in both directions. The [script's eight checks](outputs/reference_cases.json) require each change to be below 2%; the largest observed relative change is about 0.24%. The 37 A/348 ns cases have no half-step peak check, so this report draws no peak-voltage conclusion from them. No board-level 520 V/585 V stress or false-turn-on verdict follows from any of these reference runs.

## Limits and next input

Obtain the actual native-13 commutation and gate-loop inductances, capacitor ESL, and driver timing tolerances, then run the specified board-bound corner grid with this complementary deck. A full-tank waveform check is also needed before treating a constant-current edge as the operating envelope. Real VDS, gate/source-pin and switch-node waveforms remain the physical confirmation at staged bring-up; die voltage is internal to the simulation and cannot be probed directly.

## Reproduce

From this worktree's repository root, after `validation-plan/sim-kit/models/fetch_models.sh` verifies the licensed library hash:

```sh
python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round2/run_reference_cases.py
```

The runner recreates each raw run, checks it, keeps the full measurement/raw logs, deck copy and parameters, and saves the switching interval as `commutation.csv.gz`. It removes the large full rawfile and the vendor-library copy after extraction; both are reproducible from the committed deck, parameters and hash-verified model fetch.
