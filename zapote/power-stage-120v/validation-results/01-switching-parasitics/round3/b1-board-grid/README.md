# B1 — exploratory switching grid from A2 heuristic scenarios

**Result:** The first prescribed S1 case fails the model stress criteria, so the B1 grid stopped after one of 1,512 selected rows. The A2 inductances are heuristic sensitivity scenarios, not physical bounds; this is **not a board qualification or a predicted measured peak**. No board or source circuit was changed.

The completed case was leg A, A2 `min` scenario with C38, 170 V bus, 37 A signed load magnitude, low-side turn-off (`DIR=0`), 348 ns command dead time and the actual A2 gate-loop values for Q2/Q3. The [fine-run record](outputs/runs/A_min_v170_i37_d0_s0.1/case.json), [waveform](outputs/runs/A_min_v170_i37_d0_s0.1/commutation.csv.gz), [plot](outputs/first-failure-waveform.png), [diagnostics](outputs/first-failure-diagnostics.json), and [grid stop record](outputs/grid-results.json) retain the result. The [0.2 ns run](outputs/runs/A_min_v170_i37_d0_s0.2/case.json) is the required peak-resolution check. Each run directory also retains the deck, exact parameters, `.spiceinit`, measurement log, and raw-run log; only the large rawfile and licensed vendor-library copy were removed after extracting the waveform.

| Criterion | Completed case |
| --- | --- |
| S1 normal die VDS ≤520 V | **Failed in the model:** low-side die VDS first crossed 520 V at 2.359061 µs, while still below the part's 650 V rating, then peaked at 723.918 V at 2.492115 µs, 141.615 ns after the high-side on command. The over-rating peak is a stress flag rather than a calibrated physical peak prediction. |
| Off-device die VGS <3.0 V | **Failed in the model:** low-side die VGS reached 7.365 V with its command at 0 V; it repeatedly crossed 3.0 V during partner operation. The 3.0 V criterion is the [Infineon datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf) Table 4 minimum VGS(th) of 3.5 V minus the task's 0.5 V margin. |
| Die VGS within transient limits | **Passed in this one model case:** LS −9.718 to 14.967 V and HS −1.690 to 15.604 V, within the datasheet Table 2 dynamic ±30 V rating. Other corners are untested. |
| S1 ZVS at nominal dead time | **Model proxy passed in this case:** incoming die VDS stayed within 5% of bus voltage for the 20 ns before its on command. This does not override the VDS and off-gate failures. |
| S2 61/71 A at 280 V ≤585 V; S3 light load; S4 20 A hard event; corner sensitivity | **Not run** after the first failed criterion. No fault or whole-grid verdict follows. |

The 0.2→0.1 ns rerun changed the low-side VDS peak by 0.0000513% and high-side peak by 0.0002744%, each below the required 2%. The 348.000 ns command gap, complementary command states, complete transient, raw-versus-`.meas` peaks, and both ngspice exit codes were checked. A control using A1's **reference** inductances (4 nH for each LD/LS, 1 nH LCS, 3 nH LCAP, 30 nH LBULK, 20 nH each LG) reproduced A1's 170 V/37 A/DIR0 result: LS 216.0887 V and HS 171.3263 V. Its [control log and parameters](outputs/control_reference/) establish that splitting the deck's single `LG` knob did not change the reference topology. The much larger heuristic-scenario excursion is not source-deck drift.

## Gate-off and edge handback for B2 and A7

The low-side command crossed 7.5 V on its falling edge at 2.002500 µs. Die VGS first fell below 3.5 V at 2.306421 µs, **303.921 ns after that command**, and below the 3.0 V off-gate margin at 2.308656 µs. High-side on command followed at 2.350500 µs. Low-side die VGS re-crossed 3.0 V at 2.367973 µs and kept ringing above it until 3.112098 µs in the saved window. Thus the first 3.5 V crossing is a **conditional model timing observation, not a sustained gate-off bound**; B2 cannot use a single guaranteed gate-off time from this case.

The first switch-node crossing gives 20–80% edge time **20.700 ns**, 10–90% edge time **31.731 ns**, and peak 1 ns secant in the 10–90% voltage region **94.280 V/ns**. These are A7 model-input observations for this one scenario and edge. The waveform rings strongly and repeatedly after partner turn-on, so a single first-crossing edge time is not a whole-operation EMI envelope. The 280 V and other inductance, capacitor, gate and dead-time corners were not run.

## Inputs, limits, and stopped rows

The [A2 handback](../a2-inductance/README.md) supplies this exact scenario in nH: `LD_HS=10.8234`, `LS_HS=LD_LS=5.2022`, `LCS=11.5117`, `LS_LS=1.9893`, assumed `LCAP=5`, and `LBULK=21.5190` **copper only**. Separate deck knobs apply `LG_HS=16.9367` to Q2 and `LG_LS=33.8167` to Q3. The opposite A2 scenario has the assumed 20 nH local capacitor ESL; neither end is a physical lower or upper bound. `LBULK` omits unknown bulk-capacitor internal ESL. A2's two FastHenry builds failed; qualified deck parameters are all `null`. Its 0.25 mm connected routes are complete, but the Q3 source-return route did not converge at 0.5 mm. The upper scenarios may double-count shared magnetic returns. These limits apply to every number here.

The selected but stopped grid comprises buses 170/198/280 V; S1 37 A, S2 61/71 A, S3 2/5/10 A, S4 20 A; both complementary directions; legs A/B; A2 min/max scenarios (including assumed local-cap ESL 5/20 nH); dead times 348/250/450 ns; and gate-inductance scales 1/0.5/2 applied separately to each device's A2 value. That is 1,512 rows. **One row completed, 1,511 were not run.** The `min`/`max` and gate scaling are sensitivity probes, not worst-case guarantees.

The copied [complementary deck](complementary_leg.cir) differs from round 2 only by separate `LG_HS`/`LG_LS` parameters and explicit saved vectors. It retains the ideal ramped constant-current load, 27 °C Infineon L1 model, 1 nF per-device snubbers, 1 mΩ shunt, 5 ns command ramps, and approximate driver outputs: 5 Ω pull-up, 0.55 Ω pull-down, 3.9 Ω external gate resistor, 10 kΩ hold-off. The L1 model already contains per-device package `Ld=1.88 nH`, `Ls=2.82 nH`, `Lg=8.32 nH`, and 2.7 Ω internal gate resistance; these were not added to the A2 board values. The driver is an output-resistance approximation, not a TI transistor/propagation model; neither load-current trajectory nor capacitor ESL uncertainty is physically bounded. The [Infineon datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf) supplies the threshold and dynamic gate limits quoted above.

## Provenance and reproduction

- Source revision: `44417ae1489fd00e2d652fd3b2c1582b76d17630`; native-15 board SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Frozen A2 JSON SHA-256 `4365536d40dfdc2580e01ac10657874f72f4ce873e331d0248581c061bf49b35`; exact Infineon library SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`.
- B1 deck SHA-256 `bc3c4e72d174694c9637906c7af18f010cdd5da938054f84a3196a842a5d830c`; ngspice 45.2 at `/opt/homebrew/bin/ngspice`, Miniforge Python 3.12. The existing kit's PSpice mode (`ngbehavior=psa`) and `method=gear`, `reltol=1e-3` options were used. The local kit smoke test passed all checks before the B1 run.
- Local checkout was otherwise at the source revision; B1 result files are uncommitted. No native build, board edit, commit or push was performed.

From this checkout root, after placing the hash-verified vendor library in the kit's ignored `models/vendor/` directory:

```sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/b1-board-grid/run_b1.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/b1-board-grid/plot_first_failure.py
```

The runner verifies the A2, board and model hashes before a sweep. It writes one coarse/fine case pair, checks the first failed criterion, and leaves all subsequent rows unrun.
