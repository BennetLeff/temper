# F2 shutdown operating-envelope plan (read-only audit)

## Scope and identity

This plan is based on immutable revision `5dde29ab3e2f1223c2d33c129ced2cf647238307` and the accepted `f2-shutdown-04` artifacts under `zapote/power-entry/passive-reva/protection/`. It does not change the schematic, rerun a simulator, or add a protection claim. The current claims file explicitly says the result is simulation-only, uses surrogate power devices, and leaves the physical/worst-case envelope unqualified (`f2-shutdown-04/claims.json:1-24`).

There are two different scopes to keep separate during integration: the standalone 79-component F2 shutdown source-07 experiment and the retained 54-component passive power-entry board. The baseline board has direct UCC28180D gate drive through 10 ohms and no F2, independent detector, or gate buffer (`../INTERFACE-DESIGN.md:18-26`; `protection/ARCHITECTURE-REDUCTION.md:16-38`). A host-side integration context also exists for the settled 108–132 Vac, 15 Arms input sweep; the maintained PFC model records those line/current points (`../loss-budget/PFC-SWITCHING-MODEL.md:42-44`; `../loss-budget/pfc-switching-model-2026-09-17.json:19-21`). A roughly 40 °C inlet/assembly observation is a host fixture datum, not a temperature qualification for the f2-shutdown surrogate. Never combine the 79- and 54-component counts into a “full-board” reduction or coverage claim.

The accepted source is `PowerEntryF2ShutdownRevB`, a 79-component `source-07` export (`f2-shutdown-04/source-model-binding.md:3-9`). The source/model boundary is explicit: exact ST MOSFET and C3D SPICE models were not obtained, controller timing is authored nominal behavior, and the plant is a level-1 MOS plus diode surrogate (`source-model-binding.md:11-23`; `plant/models.md:3-18`).

## What is actually validated today

The table below records dimensions that appear in the frozen fixtures, with the exact values exercised and what they mean. A value in this table is an observed fixture point, not an operating limit.

| Dimension | Exact validated points | Evidence and interpretation |
|---|---|---|
| DC source voltage | `VLINE=186.6761902 V`; plant local/bulk initial voltage `VD_INIT=VB_INIT=410 V` in all listed plant rows; host retained-board input context is 108/120/132 Vac at 15 Arms | `plant/f2_shutdown_template.cir:7-17,40-60`; `plant/run_cases.sh:60-75`; host PFC model `../loss-budget/pfc-switching-model-2026-09-17.json:19-21`. There is no AC source or line-phase variable in f2-shutdown; “phase” below is PWM delay. The actual host baseline must be sensed rather than assuming the plant's 410 V initial condition (the integrated observation is about 413 V). |
| AC/line phase | None | `Vline` is a DC source (`f2_shutdown_template.cir:40-42`), so mains phase, zero-crossing and source impedance are absent. Do not call PWM-delay coverage line-phase coverage. |
| Inductance and initial current | `L=100 µH, IINIT=90 A`; `180 µH, 74 A`; `216 µH, 75 A` | `plant/run_cases.sh:60-63`; actual current at the 220 µs opening is `41.658003, 46.228062, 51.095469 A` (`plant/traces/summary.csv:3-6`). The README warns that initial values are not the opening-current evidence (`plant/README.md:9-14`). |
| F2 event and bus plant | F2 opens at `220 µs`; `CLOCAL=19.8 µF`; disconnected `CBANK=2240 µF`; nominal stop `320 µs` (healthy row `220 µs`) | `f2_shutdown_template.cir:12,16-18,54-60,101`; `plant/run_cases.sh:60-75`. Post-open energy uses only local 19.8 µF headroom; the bulk bank is not credited (`plant/README.md:53-60`). |
| PWM timing/phase | `PWM_DELAY=1,2,4,5 µs` rows; `7 µs` active row; nominal duty `5.5 µs`, period `10 µs` (~100 kHz) from `Vpwm ... PULSE(... {PW_ON} 10u)` | `plant/run_cases.sh:60-74`; `f2_shutdown_template.cir:67`. Existing rows are sparse points, not a continuous phase sweep. The retained UCC28180 model context is ~129.1 kHz (`../loss-budget/pfc-switching-model-2026-09-17.json:16-20`), so the synthetic fixed-PWM fixture does not reproduce controller frequency or stop/restart behavior. |
| Gate-load / gate-charge surrogate | Normal `GATE_TAU=120 ns` → `Cgs=12 nF`; doubled `240 ns` → `24 nF`; deliberately slow `480 ns` → `48 nF`; source data anchors `Qg=120 nC`, `Qgs=27 nC`, `Qgd=58 nC` | `f2_shutdown_template.cir:26,30-38,85-87`; `plant/extract.rs:97-110`; `plant/models.md:21-27`. These are authored capacitance/load sensitivities, not an exact charge-vs-voltage curve. |
| Driver/controller timing | Plant nominal `EN_TAU=39 ns`, controller fault filter `FAULT_TAU=79.3 ns`; negatives use `EN_TAU=5 µs` and `FAULT_TAU=10 µs` | `plant/run_cases.sh:60-75`; `plant/controller.inc:3-5,39-46,59-65`; `fault-tests/run_cases.sh:55-56`. The 39 ns plant driver is slower than the isolated TI fixture's 18.75 ns, by design (`plant/README.md:16-20`). |
| Rail ramp/dropout | Plant rails are ideal DC `logic5=5 V`, `aux15=15 V` and controller is prequalified; separate fault fixture uses 20 µs nominal ramps, 20/40 µs ordering, 60 µs slow ramps, 1 µs auxiliary dip, absent rails, and drop/return at 240/300 µs | Plant DC sources: `f2_shutdown_template.cir:91-99`; prequalified-running statement: `plant/README.md:16-20`. Fault cases: `fault-tests/run_cases.sh:40-56`; source PWL rails: `fault_template.cir:18-20`; documented scope: `fault-tests/README.md:22-35`. There is no single coupled rail-ramp/power-stage run. |
| Detector thresholds | Absolute `VABS=426.469072165 V`; mismatch ratio `MISMATCH=1.0355871886`; bus filters `47 pF`; comparator input `2 pF`; 22 kΩ isolation | `plant/controller.inc:3-30`; `fault-tests/controller.inc:3-30`. These are nominal authored values; threshold/hysteresis/timing tolerance are omitted (`fault-tests/README.md:28-35`). |
| Shutdown timing and bus screen | Positive isolated fault rows: absolute threshold→loaded gate-off `0.748899 µs`; mismatch `1.535580 µs`; plant controlled turnoff about `0.500–0.505 µs`; doubled gate load `0.870361 µs`; slow driver negative `5.074 µs` | `fault-tests/traces/summary.csv:2-14`; `plant/traces/summary.csv:2-14`. Extractor screen is threshold→channel cessation ≤2 µs and peak VD ≤500 V (`plant/extract.rs:9-15,340-352`; `plant/README.md:22-38`). These are provisional experiment screens, not ratings. |
| Bus peaks and ratings | Accepted plant rows peak `439.108–477.450 V`; worst accepted refined row is about `477.45 V` | `plant/traces/summary.csv:2-12`; `circuit/plant-final-review.md:3-7`. This is only the plant's provisional VD screen. For integration, keep separate duration/temperature acceptance rows for **VD local capacitor candidate 630 V**, **VB bulk candidate 450 V**, **MOSFET/diode candidate 650 V**, and **gate VGS**. The existing 500 V number is a provisional VD experiment screen only; it does not license 500 V on VB or any device rating. |
| Numerical refinement | Two 2 ns→1 ns refinements: delay changes `0.000136 µs` and `0.001768 µs`; peak changes `0.003743 V` and `0.000347 V` | `plant/refinement.txt:1-2`; extractor thresholds are `0.02 µs` and `0.1 V` (`plant/README.md:36-38`). This supports numerical stability for those rows only. |
| Energy closure | Post-open fault-window residual is compared to `0.1%` of local 19.8 µF headroom; residuals in rows are ~`1e-7–1e-6` of that denominator | Boundary and omitted terms: `plant/README.md:53-65`; equations: `plant/extract.rs:299-333`; values: `plant/traces/summary.csv:2-12`. This is accounting closure inside the surrogate boundary, not device-model validation. |
| Temperature | None in the operating sweep | Source binding says no temperature or full tolerance sweep (`source-model-binding.md:11-18`); model limitations explicitly include temperature and hot I/V (`plant/models.md:41-44`). The 25/27 °C data-sheet anchors are point checks only (`claims.json:134-170`). |

## Missing dimensions before an envelope claim

1. A real input contract is needed for allowed source voltage, source impedance, and (if applicable) AC line frequency/phase. The current `VLINE` is one DC point, so it cannot establish line compatibility or phase coverage. The plant's 410 V initial condition is a fixture state, not the retained-board nominal bus (the maintained PFC context lists 389.615 V; the integrated host baseline is about 413 V and must be sensed).
2. The three L/I rows are useful anchors, but there is no demonstrated `L(I,T)` curve, initial-current generation rule, saturation corner, inductor winding loss, or temperature dependence. The model-boundary document names `L(I,T)` and physical maximum fault current as unknown (`source-model-binding.md:45-50`). Do not promote the ~40–51 A observed rows to a current maximum; establish the bound with a sensed actual inductor/F2 current and the per-node voltage, device, fuse, and thermal limits.
3. MOSFET `RDS(on)`, diode forward drop, capacitances, reverse/commutation behavior, and gate charge are nominal surrogate anchors. Nonlinear C(V), hot I/V, avalanche, and actual reverse recovery are explicitly absent (`plant/models.md:10-34,41-44`). Device acceptance must separately record VD, VB, MOS/diode, and gate-VGS waveform limits with duration and temperature; a single bus ceiling is not a device qualification.
4. F2 fuse arcing/restrike, opening delay, and current interruption are not modeled; the switch is an idealized controlled element with `Ron=15 mΩ` (`f2_shutdown_template.cir:58-60`).
5. Loop/source parasitic inductance and layout coupling are absent. Bus peak therefore cannot be transferred to an assembled board.
6. Rail ramp cases and plant power cases are separate. The plant holds ideal rails and prequalified supervisor state, while fault tests drive independent VD/VB and rails (`source-model-binding.md:25-29`). A coupled run is required to test rail ramp × actual switch current.
7. Temperature is not a parameter. There is no cold/room/hot device model, thermal state, sensor setup, or temperature acceptance criterion.
8. Passive terminal ringing is unresolved at the endpoint (`terminal_settled_us=null` in the fault rows); it must not be silently converted into zero current or a pass (`plant/README.md:47-51`; `plant/traces/summary.csv:2-12`).

## Small sequenced matrix

Use the stages in order. Each stage produces a bounded result that enables the next; a failure stops that branch and is retained as an indeterminate or fail result. The matrix is deliberately small and adaptive rather than a claim of exhaustive grid coverage.

### A. Instrument and nominal identity (one run + one repeat)

- Freeze source-07, netlist, controller include, device-model hashes, simulator version, and extractor revision. Record all fixture parameters and generated raw traces.
- Reproduce one plant nominal row (`normal_arm`) and one adverse power row (`f2_open_50_adverse`), plus one isolated fault nominal (`forward_mismatch`).
- Measurands: event ordering, opening current, threshold time, channel cessation, gate/Q/EN state, peak VD, source/F2/diode/channel currents, and energy terms.
- Stop if source/fixture identity is missing, trace is non-finite/truncated/gapped, causal order is absent, or the nominal result differs from the frozen summary beyond the extractor's declared tolerances.

### B. Controller regression (reuse frozen evidence; no duplicate campaign)

Do not rerun the already-authoritative isolated suite merely to populate this plan. Treat its existing 13 positive/negative rows and exact traces as regressions after any model or schematic change. The frozen points are:

- nominal 20 µs/20 µs rail ramps;
- 20/40 µs and 40/20 µs supply ordering;
- 60/60 µs slow ramps;
- logic absent, aux absent, logic dropout/return, aux dropout/return, and 1 µs aux fast dip;
- one fault in each absolute and mismatch polarity;
- negative controls: `BYPASS=1` and `FAULT_TAU=10 µs`.

These are already represented by the frozen fault fixture (`fault-tests/run_cases.sh:40-56`) and give controller evidence independent of power-stage energy. Preserve the observed positive latency values (`fault-tests/traces/summary.csv:2-14`). Do not infer a brownout transfer guarantee: the model forces input behavior off below 1.65 V by assumption (`fault-tests/controller.inc:81-84`; `fault-tests/README.md:42-46`). Add new rows only when D changes the controller/plant coupling.

### C. Power-stage anchor/corner screen (six rows)

Use the actual plant, retaining the existing anchors and adding only combinations that exercise interactions:

| Row | Required combination | Purpose |
|---|---|---|
| P0 | `L=180 µH`, `IINIT=74 A`, normal `GATE_TAU=120 ns`, `PWM_DELAY=3 µs` | Reproduce the nominal controlled path. |
| P1 | `L=100 µH`, `IINIT=90 A` | Low-L / lower opening-current anchor (`41.658 A`). |
| P2 | `L=216 µH`, `IINIT=75 A`, `PWM_DELAY=7 µs` | Highest observed opening current and PWM-on opening. |
| P3 | P2 + `GATE_TAU=240 ns` | Loaded-turnoff sensitivity (`0.870361 µs` observed). |
| P4 | P2 + `GATE_TAU=480 ns`, `EN_TAU=5 µs` | Deliberate slow-driver negative (`5.074 µs` observed). |
| P5 | P2 with 1 ns max step | Numerical convergence companion. |

Measurands and screens are the plant extractor's declared quantities: threshold→positive channel cessation, peak VD, late rearm current, terminal reverse peak/settling, and post-open energy residual. A row fails/halts on missing causal events, late positive channel current, or a voltage waveform crossing the applicable, separately sourced limit for the node/device and duration: VD local capacitor (candidate 630 V), VB bulk (candidate 450 V), MOSFET/diode (candidate 650 V), or gate VGS. The current 500 V check remains a provisional VD-only experiment screen; do not apply it to VB. Delay > provisional 2 µs, unexplained late rearm, non-finite/gapped trace, or refinement drift >0.02 µs / 0.1 V also stops the row. These are experiment screens from `plant/extract.rs:9-20,354-374`, not protection ratings.

### D. Coupled rail/control × plant runs (four rows; integration priority)

This is the minimum new evidence needed before claiming a whole-power-stage operating envelope. Couple the actual controller behavior to the plant rather than prequalifying controller states. The retained-board gap is material: current direct-drive UCC28180D uses a direct GATE path plus VSENSE standby, while the f2 fixtures use a synthetic fixed PWM and do not exercise the actual UCC stop/restart sequence (`../INTERFACE-DESIGN.md:18-26,119-143`). Stage D therefore comes before any simplification or schematic consolidation. This is the priority new campaign; C's surrogate rows are anchors, not a substitute.

1. P2 with F2 charged and rails at the measured host baseline; command an actual UCC28180 stop through VSENSE/standby at the F2 event.
2. P2 with F2 charged and 20 µs/20 µs logic/aux ramps.
3. P2 with F2 discharged/precharged from zero, then 40 µs logic-first and 40 µs aux-first ramps.
4. P2 with F2 charged, 60 µs/60 µs ramps, an auxiliary dip at the F2 event, and an explicit UCC stop/restart attempt at the retained ~129 kHz switching frequency.

Use the same event, current, bus, gate, and energy measurands as C, plus actual UCC28180 `GATE`, `VSENSE`, PWM/ENA/standby state, source current, and sensed VD/VB. Measure the actual starting bus (do not silently substitute 410 V for an observed ~413 V baseline). Require controller health/rails/Q/EN transitions to be causally tied to the rail/F2 event and restart edge. Any mismatch between isolated-control and coupled-plant behavior is a model-integration finding, not evidence to widen a limit. Keep the 79-component shutdown source and 54-component retained-board scope in separate evidence bundles.

### E. One-dimensional sweeps, then adaptive interaction points (after D)

Only after A–D pass, simplify the model where evidence permits, then run a small adaptive set around the first coupled-controller margin: source voltage/current, generated opening current, gate charge/load, rail ramp, and temperature. Do not create a large arbitrary grid. The low/high values must come from the circuit's external requirements or measured component data; they are not supplied by this audit. Include the host 108/120/132 Vac and 15 Arms points, and retain the approximately 40 °C inlet observation as fixture metadata until device temperatures are measured. The existing Rust PFC sensitivity model's 25/125 °C labels are model sensitivities, not a solved electrothermal result (`../loss-budget/pfc-switching-model-2026-09-17.json:19-27`).

Then add a small interaction set at the nearest observed margins: `(source, opening current)`, `(L, temperature)`, `(PWM phase, gate load)`, `(rail ramp, detector timing)`, and `(temperature, loop/fuse parasitic)`. Add points adaptively around the first fail or discontinuity; do not claim a rectangular envelope from a five-point-per-axis grid. Report the sampled hull and untested dimensions explicitly.

Negative controls must remain in every campaign: bypassed detector, slow detector, slow driver/large gate load, held ARM with no fresh edge, and a deliberately absent rail. They must fail the intended assertion, while an absent-event or truncated trace is `indeterminate`, never an automatic pass.

## Numerical convergence versus physical uncertainty

Treat these as separate columns in every result:

- **Numerical convergence:** timestep refinement (2 ns→1 ns, then 1 ns→0.5 ns only near a boundary), trace gap/monotonic-time checks, and energy residual closure inside the declared post-open boundary. The current evidence demonstrates only two 2 ns→1 ns rows (`plant/refinement.txt:1-2`) and the extractor rejects gaps/non-finite samples (`plant/extract.rs:113-203`).
- **Physical-model uncertainty:** exact vendor transient models, nonlinear capacitance, hot I/V, L(I,T), fuse arc/restrike, loop inductance, source impedance, noise/hysteresis, brownout analog behavior, and thermal paths. Better timestep or a smaller residual cannot resolve these omissions. The source/model binding and model notes list them explicitly (`source-model-binding.md:45-56`; `plant/models.md:21-44`).

If numerical closure fails, stop and repair the apparatus before interpreting physics. If numerical closure passes while a physical input/model is absent, report a model-limited result and stop envelope promotion at that dimension.

## Minimal fixture changes for actual power-stage coupling

Simulation fixture changes (to be designed and reviewed before implementation):

1. Replace plant's ideal `logic5=5 V`/`aux15=15 V` sources with parameterized PWL sources and the accepted supervisor/latch network. Keep the isolated fault fixture as an independent control.
2. Drive VD/VB from the actual boost/F2 plant and derive detector events from those nodes; do not use independent fault sources in the coupled run.
3. Add a voltage-sense element for F2 current and save/integrate it. Include pre-open `I²R` loss if reporting whole-interval energy; otherwise label all closure as post-open only. This omission is called out in `circuit/plant-energy-audit.md:9-14`.
4. Save `i(Vlogic5)` and `i(Vaux15)` (including divider, supervisor, BSS138 and driver loads) and include their source work in any expanded energy boundary.
5. Keep separate probes for inductor/line current, F2 current, positive MOS channel current, body/diode current, and total terminal current. Never use channel cessation as total branch-current cessation (`plant/README.md:40-51`).
6. Replace or independently correlate the functional driver surrogate with the retained board's actual UCC28180 direct-GATE/VSENSE path and the checked TI driver plus real external gate network; preserve each fixture as an oracle, not as proof of the ST switch. Add explicit UCC stop/restart, VSENSE inhibition, and first-pulse observations.
7. Add parameterized source/loop/fuse parasitic inductance and an evidenced fuse opening model. Do not invent values to obtain a pass.
8. Add temperature parameters or measured curves for MOS, diode, magnetics, fuse and gate network, with cold/room/hot trace metadata. Until that exists, temperature rows are unavailable.

Minimum bench fixture (when moving from simulation to hardware correlation): programmable isolated source with logged voltage/current and controlled ramp/dropout; real F2 and a calibrated current sensor; HV differential probes at VD/VB and gate; isolated logic5/aux15 supplies with synchronized control; low-inductance, measured switching loop with a current probe; thermocouples or a chamber for device/board temperature; and a safe dump/precharge/interlock path. The fixture must log source revision, sensor calibration, probe locations/bandwidth, ambient/device temperatures, exact part/date codes, and raw waveforms. A bench result can challenge the surrogate but cannot retroactively turn the frozen nominal simulation into a protection rating.

## Schematic consolidation gate

Consolidate only after D (actual-controller coupled startup/stop/restart) and then E produce a coupled, source-bound evidence bundle. Stage C's surrogate sensitivity rows alone are insufficient:

- retain one accepted `source-07` schematic identity and its 79-component compiled graph;
- move values/constraints into the schematic only when they are sourced requirements or measured component data, never because a surrogate simulation passed;
- preserve explicit node contracts (`health_ok`, `rails_ok`, `clear_ok`, `run`, `enable_good`, and UCC IN−) from `circuit/device-contract.md:3-23`;
- keep the isolated controller and vendor-driver fixtures as regression oracles;
- rerun source/physical-pin checks, coupled simulation extractors, and the negative controls after each consolidation; and
- publish sampled operating points, untested corners, numerical residuals, physical-model gaps, and per-node voltage/duration/temperature limits together. No step in this plan promotes `claims.json` from illustrative simulation evidence to a protection claim; it only establishes what evidence would be required for a later, separately reviewed qualification decision.

## Stop/handback rules

Stop immediately on any missing source/model hash, changed immutable artifact, unresolved trace gap/non-finite value, causal event inversion, failed negative control, unexplained regression, or disagreement between coupled and isolated control paths. Hand back the exact failed row and raw trace path, the parameter vector, the applicable source limit (or “limit unavailable”), and whether the failure is numerical, model-bound, or physical-fixture related. Do not widen the envelope, change the provisional 2 µs/500 V screens, or edit the protection schematic to make a row pass.
