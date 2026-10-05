# Cartridge bench validation preparation

**Physical status: NOT_RUN.** This package prepares acquisition, reduction, calibration and failure checks. It neither controls equipment nor demonstrates a physical cartridge. It is based on study commit `767f2fbae7a842e58afb288c5966453f10ab3d7a`. Work is confined to `bench_validation/`.

At inspection on 2026-10-04, `/Users/bennet/Desktop/temper/output/temper-engineering-validation/sensor/{runs,samples,results,uncertainty}.csv` each contained one header and no measurements. The only local serial device names exposed were Bluetooth-Incoming-Port and debug-console; no DAQ or assembled cartridge was evidenced. This is not a claim that no instruments exist elsewhere. The fixture STEP and parts list in `fixture_snapshot/` are copies of the existing untracked preparation artifacts, hashed in `evidence/source-inputs.sha256`. They are CAD evidence, not fabricated or qualified hardware.

## Run offline

```sh
bash run.sh                          # unit tests + synthetic import/calibration controls
rustc --edition 2021 -D warnings -O bench.rs -o /tmp/temper-bench
/tmp/temper-bench thermal samples.csv run.txt
/tmp/temper-bench mechanical cycle.csv cycle.txt
/tmp/temper-bench calibrate fit.csv fit.txt holdout.csv holdout.txt
/tmp/temper-bench budget uncertainty.csv
```

Rust is the sole owner of analysis and fixture physics. `run.sh` uses `rustc`, `rustfmt`, `shasum`, `rg`, `awk`, `sed` and Bash; no Python, pyo3 rebuild, Cargo cache, network or instrument API is involved. Generated evidence is explicitly SYNTHETIC. Do not put real files in `evidence/SYNTHETIC-*`; the runner overwrites those software fixtures. Physical templates stay empty/NOT_RUN and deliberately fail import.

## What is implemented

The importer requires the exact CSV header, finite values, strictly increasing nonnegative time, adequate sample count, known phases and binary independent contact; it rejects acquisition gaps, exceeded reviewed temperatures, missing provenance/reference/uncertainty, mixed evidence classes, and fitting without a distinct holdout. No CSV quoting is supported; a single measurement per file keeps schemas inspectable. Mandatory quantities are measured or explicitly synthetic; do not fill missing channels with zeros. The companion acquisition log can contain additional channels, which must be exported through an identified transformation into this exact schema.

Mechanical reduction uses one load/unload cycle per file: total tip force, peak compression, maximum same-stroke load/unload hysteresis, residual stroke, peak opposed-indicator differential, and settled return within 0.02 mm for at least the final 1 second. The 0.02 mm window is a reporting convention, not an approved return tolerance. It reports characterization only. The two opposed indicators capture one tilt axis; repeat after rotating the pan/indicator axis by 90 degrees. Differential displacement alone cannot detect uniform pan lift. Record a third absolute indicator or four corner heights in the acquisition sidecar and evaluate uniform lift against the glass datum. The fixture and protocol below explicitly require that check.

Thermal reduction requires five baseline samples and a stable plateau lasting at least 60 seconds. Both pan and sensor plateau ranges must be ≤0.5°C (proposed stability gate). It reports signed sensor-minus-local-pan error, expanded uncertainty with k=2, t90 of actual sensor final rise, and t90 of imposed pan rise. A biased fast sensor can reach the first and never reach the second. Step timing comes from independently observed contact/input change, not the DUT response. Reference transition plus independently bounded reference lag must be ≤0.3 seconds before the proposed ≤3 second response screen can pass. Otherwise response is INDETERMINATE; do not subtract an assumed reference time constant.

Existing proposed screens remain proposals: |error|+U ≤2°C at 40–100°C, ≤5°C above 100–250°C, and t90+U_time ≤3 seconds. A point estimate inside a limit with uncertainty overlapping it is INDETERMINATE. The requested temperature is always bounded by the reviewed complete assembly; the selected R401/30S silicone material candidate has a 210°C material limit, so no 250°C assembly permission follows. No seal hotspot bound has been measured. Synthetic 250°C metadata is not a physical authorization.

## Calibration: what the data can identify

The effective surrogate is `dTs/dt = [gain*Tpan + (1-gain)*Tbody + offset - Ts]/tau`. A log grid searches tau from 0.05 to 60 seconds; bounded least squares fits gain and offset. Integration is exact for piecewise-constant measured inputs. A search-boundary fit rejects transfer. Fit requires ≥20°C pan-minus-body excitation. Holdout requires separate raw bytes, origin, run ID, declared role, baseline, excitation and ≥5 tau recorded after the step; a long unchanged tail cannot supply dynamic validation. In addition to global RMSE it reports dynamic RMSE and peak residual over the first max(5*tau,3 seconds); both global RMSE and dynamic maximum must fit within 2*u_error. This is a declared engineering model screen, not a probabilistic coverage theorem.

This deliberately does **not** identify cap heat capacity, bond conductivity, contact conductance, and lead losses independently. One PT100 and one pan reference cannot uniquely determine all of them. Mathematically, scaling every G and C by the same factor preserves a linear network's transient; serial bond/contact resistances are also confounded without internal node temperatures. Retain the existing three-node model ranges until extra experiments constrain them. To tighten it: weigh cap and chip separately; measure bond area/thickness on sacrificial cross sections; measure contact force; measure cap back, glass rim and body temperature without materially changing conduction; change only bond thickness or applied force between known builds. Treat fitted tau/gain as per-condition observed envelopes, not permanent firmware compensation. Do not tune firmware from synthetic fits.

Before any real acquisition, declare fit/holdout assignment in the run ledger. Suggested initial allocation: two separately assembled cartridges for fit, a third for holdout; the current CLI compares same-cartridge run pairs, so each cartridge also needs its own independently acquired holdout run, and cross-cartridge comparison remains a separate review. Vary heating rate, repeat placement and cookware on holdout. A held-out timestamp window from the same acquisition is not accepted as an independent run. Repeated-measure uncertainty and between-build variation cannot be inferred from the synthetic fixtures.

## Schema and uncertainty

All times use a shared monotonic DAQ clock in seconds; record UTC acquisition start in metadata. CSV `stroke_mm` increases when the tip compresses from the unloaded glass-relative datum. `force_n` is calibrated total force at the cap, not nominal spring force. `rock_a_mm` and `rock_b_mm` are absolute pan underside heights relative to glass at known opposed radii. `contact_reference` is a separate reference observation (e.g. instrumented force/displacement/contact-view combination); it must not be copied from firmware's proposed contact detector.

Metadata `.txt` contains key=value lines. See `templates/run.txt`. `u_*` are **combined standard uncertainties** (k=1), not manufacturer accuracy headlines. The `budget` command consumes `templates/uncertainty.csv`: enter already converted standard uncertainties and sensitivities in common output units. Independent group names combine by root-sum-square; terms sharing a correlation group add absolute contributions conservatively. Keep calibration-certificate coverage factors, distribution divisors and conversion work in the raw budget attachment. A certificate's U(k=2) becomes u=U/2; a justified rectangular bound a becomes a/sqrt(3); repeatability of one installation is not automatically divided by sqrt(N) for a future individual reading.

Required error components: calibrated reference and logger, reference placement/spatial gradient, attachment heat sinking, DUT readout, repeat placement, reference/DUT clock skew times measured dT/dt, and calibration drift. Keep shared logger/CJC errors correlated. Time uncertainty includes sample interval, channel multiplex offset, contact event alignment, reference response bound and crossing interpolation/noise. Force includes weight standard/local gravity where used, alignment, tare, thermal drift and wire force. Displacement includes gauge calibration, fixture/glass deflection, thermal expansion and setup repeatability. Do not claim a useful ±2°C comparison if the reference/placement budget already consumes it. Missing budgets are rejected; a positive arbitrary number is not a valid uncertainty assessment and requires human review.

The shared induction package uses the same `time_s`, `pan_ref_c`, `sensor_c` meanings and explicit MEASURED/SYNTHETIC provenance. Its extra field-on/off, independent optical reference and acquisition validity channels stay in its own schema. Preserve a common `run_id`, hardware revision and original raw-origin ledger when exporting both views. No resampling may conceal gaps or create extra independent observations.

## Evidence and limits

`synthetic.rs` uses closed-form one/two-pole responses independent of the fit integrator. The holdout has a different temperature and deterministic noise. Positive recovery tests prove harness behavior only. A weaker-contact negative holdout, an unmodeled fast pole hidden by a long steady tail, a fast-but-biased sensor and corrupted/empty imports must be rejected or marked indeterminate. Tests include analytical t90, hot contact loss, invalid gaps, cooling, bounce recovery and conservative correlated uncertainty. Generated hashes identify raw and metadata bytes; they do not authenticate a physical experiment or verify certificate truth.

Read [PROTOCOL.md](PROTOCOL.md) for the complete fixture, instrument, acquisition and matrix preparation. The next human action is review and assemble the field-free fixture, choose calibrated instruments, and acquire the predeclared runs. All physical rows remain NOT_RUN.
