# D17 conditional commutation experiment

**Partial engineering evidence, not a complete fault-shutdown or survival model.** Source: `ps-oracle` commit `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, native-18 electrical configuration with the qualified native-17 leg-A copper matrix. No board, trip resistor, firmware or operating limit changes are made here.

## Baseline and model

`leg_matrix_baseline.cir` and `legA-h0-best.matrix.txt` are verbatim copies of round17/d2. The historical S1 170 V /37 A /348 ns /1.06 nH case reproduces VDS=203.6704 V and off-gate VGS=2.234341 V exactly in ngspice 45.2. **348 ns is an instrument check, not the selected operating dead time.** Native-18's 49.9 kΩ resistors remain selected; their estimated 396.6–488 ns dead-time range belongs to complementary switching tests.

`conditional_turnoff.cir` changes the stimulus: low-side initially on, high-side held off, and both commanded off at `2 µs + TD`. An imposed current reaches `ITRIP` at 1 µs, holds until 2 µs, then rises at 10 A/µs, including after the command. The driver is the inherited typical-resistance approximation. This is a **forced-current commutation sensitivity**, not a physical coil/tank, shoot-through, shorted-load, complete detector, or interlock model. The stiff bus source cannot predict returned-energy bus rise.

`TD` is the **whole external threshold-reference-to-driver-command delay**, swept at 0/1/5 µs as hypotheses. It is neither an interlock guarantee nor the dead-time resistor value. The 443 ns DT parameter is recorded but is inactive in this all-off experiment: no partner turn-on occurs. Do not add either 443 ns or the old 150 ns assumed gate discharge to these results.

## Executed matrix

72 nominal-temperature cases: four static threshold reference values (CT 50.558/60.014 A; shunt 38.438184/85.551033 A), three buses (170/198/280 V), two local-capacitor ESL values (1.06/10 nH), and three external delays. Applying the same forced waveform to these reference values does not assert that R5 and the CT see the same actual fault waveform. Primary cases use 0.2 ns maximum time step, nominal vendor FET model at 27 °C, and inherited Gear settings with `itl4=100000`.

Three observed extrema are repeated at 0.1 ns. Those same three receive separate 100 °C and 150 °C FET-temperature probes at 0.1 ns; these are not temperature/process coverage of all 72 cases. The vendor model imposes temperature without self-heating; no hot driver/passive bounds are invented.

| Nominal-temperature observation | Result | Interpretation |
| --- | ---: | --- |
| Driver command to **first** die-VGS fall through 1.9 V | 352.66–393.49 ns | The old assumed 150 ns is not a supported substitute for these modeled cases |
| Maximum modeled die VDS | 365.0461 V | Limited imposed-current cases; not a physical fault upper bound or SOA verdict |
| Maximum off high-side gate voltage | 2.185808 V | Exceeds the conservative 1.9 V screen; not proof of a measured hot-device turn-on |
| Maximum low-side gate in command+0.4…0.75 µs window | 2.735260 V | In the 27 °C matrix all first crossings precede +0.4 µs; some crossings therefore rebound and are not persistent turn-off |
| High shunt-reference, 198 V, 1.06 nH, 1 µs external delay | 99.3919 A imposed current at first 1.9 V crossing | 85.551033 A reference plus imposed ramp during external delay and modeled gate discharge; not actual trip current |

The 0.1 ns refinements move VDS by at most 0.718 V, gate metrics by at most 2.771 mV, and first crossing by at most 0.19 ns across the three selected cases. This supports those reported features against time-step artifacts; it does not qualify omitted physical paths. At 100/150 °C a first crossing can occur after +0.4 µs, so the fixed late-window metric must not automatically be called rebound.

T1's 88 A catalogue figure is a thermal reference, not an instantaneous destruction boundary. Neither an imposed current above 88 A nor VDS below 650 V establishes pass/fail survival. No device overlap-energy, avalanche, physical current-extinction or returned-energy verdict is supplied by this model. R34/R35 retuning remains on hold.

## Files and reproduction

- `conditional-results.csv`: the 72-case numerical matrix.
- `experiment-summary.json`: baseline, counts, refinements, temperature probes, and qualification exclusions.
- `raw-evidence.tar.gz`: ngspice logs, parameters, result records and derived thermal decks; **no vendor model or datasheet**.
- `evidence-manifest.json`: full member hashes, model/source hashes and provenance.

From the repository root, with ngspice, Python standard library and jq available:

```sh
bash zapote/power-stage-120v/prototype-closure/power/run-conditional.sh \
  /absolute/path/to/ps-oracle
```

The second optional argument selects an isolated output directory. The runner writes only there, and uses `PYTHONDONTWRITEBYTECODE=1` for the frozen runner. Its existing licensed Infineon model must be present in the read-only source checkout. Before executing that runner, `preflight.sh` checks the deck/matrix and harness hashes, the three external runner/model/options hashes, and ngspice 45.2. Changed inputs or another simulator version stop the run; they require separately qualified evidence. External pins were recovered from the archived original `source-hashes.txt`, not remeasured from a potentially changed checkout.

The script rejects aborts or missing measurements and requires exact historical-baseline reproduction before the sweep. `accept-conditional.jq` also requires the first falling 1.9 V crossing to occur after `TCMD`: the raw `FALL=1` measurement has no start-time restriction, so an earlier crossing during the initial current ramp invalidates the result. All 81 archived cases pass this check (crossings 352.66–407.81 ns after command, including the selected hot cases). This confirms the observed cases; it is not a guarantee for an unsimulated stimulus. No safety-pass flag is emitted.

See [power closure](../../../../docs/research/mit-product-design/readiness/power/closure-2026-10-04.md) for the actual chain, component delay authority, physical inputs and interlock ECO proposal.
