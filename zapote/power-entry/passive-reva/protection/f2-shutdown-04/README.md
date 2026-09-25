# F2 shutdown: steps1–3 implemented and evaluated

This revision implements a default-off driver boundary with real supply
supervisors, replaces ineffective fault tests with running-fault/supply cases,
and corrects the power-device model and measurements. The work was delegated
to Luna circuit, simulation and review agents, then integrated and verified by
the host. All three requested simulation-work steps are complete.

The accepted circuit is `PowerEntryF2ShutdownRevB`,79 components, compiled in
`source-07/`. It retains the four-channel detector and fault latch, adds defined
rail qualification and a fast auxiliary-loss path, and uses UCC27511A IN− with
an external1kΩ pullup for default disable. No retained power-board change is
included in this experiment.

| Check | Observed result |
|---|---|
| Compiled physical-pin/source checks |15 passed, including retained-board regressions |
| Independent running-fault/supply cases |13 passed; bypass and slow-detector controls failed as intended |
| Unfiltered OV threshold → loaded gate off |0.749µs |
| Unfiltered mismatch threshold → loaded gate off |1.536µs |
| Official TI driver-model checks |All five states and both startup ramps passed; RUN-to-gate off0.212µs |
| Power-stage cases |12 passed; deliberately slow driver failed at5.074µs |
| Actual F2-opening currents / inductance |41.658A/100µH;46.228A/180µH;51.095A/216µH |
| Power-stage controlled turnoff |About0.505µs baseline;0.870µs with doubled gate load |
| Bus-voltage screen |All accepted cases below478V against provisional500V |
| Timestep refinement2ns→1ns |Largest delay change1.768ns; largest peak change3.743mV |
| Earlier evidence preservation |193 prior receipt artifacts and input hashes unchanged |

Two circuit changes followed direct test failures:100pF detector filtering
was too slow for the near-threshold mismatch case, so it is now47pF; a10kΩ
disable pullup allowed a startup gate pulse in the TI model, so it is now1kΩ.
The power model now has finite MOS conduction, one body-diode path, separate
channel/terminal current measurements and an explicit post-opening energy
boundary. The earlier apparent25µs shutdown was caused by counting passive
reverse current as continued channel operation.

The standard architecture is now concrete and reproducible. These results
support continuing with this candidate **under its stated simulation
assumptions**. They do not establish an assembled circuit's protection rating.
The exact ST transient model remains unavailable; the power model is a
source-bound surrogate with checked DC anchors and declared charge assumptions.
Arbitrary partial-power logic behavior, hot device limits, L(I,T), fuse arcing,
layout parasitics and the physical maximum fault current remain unqualified.
Passive terminal ringing continues after channel shutdown and is reported
separately; a null settling time is not converted to a pass claim.

## Evidence and reproduction

- `circuit/README.md` and `device-contract.md`: actual parts, physical boundary and supply thresholds.
- `source-model-binding.md`: source/export identity and model limitations.
- `fault-tests/README.md`, `traces/summary.csv`, `run_cases.sh`: four detector channels and supply/rearm behavior.
- `vendor/`: unchanged TI driver model and strict independent fixtures.
- `device-checks/`: actual ngspice DC anchor and body-path checks.
- `plant/README.md`, `traces/summary.csv`, `run_cases.sh`: current, timing, voltage and energy evidence.
- `review-resolution.md` and `circuit/*review.md`: independent findings and resolutions.
- `claims.json`, `claims-check.txt`, `receipt.json`: bounded claims and final artifact hashes.

The latest exports and final generated netlists are the accepted inputs.
Earlier source builds and explicitly marked model attempts remain diagnostic
history. Final raw waveforms are losslessly compressed; extracted TSV traces
remain directly readable by the Rust extractors. No commits or publication
were requested or performed in this pass.
