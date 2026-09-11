# Circuit simulation scenarios

The scenario types are `startup`, `input_variation`, and `load_variation`.
The adopted protocol requires at least thirteen cases, as detailed below.
Their limits belong to the versioned requirements
receipt; this directory does not invent engineering limits. Switching ripple,
efficiency, thermal, EMI, and protection behavior remain unsupported until a
model and independent evidence justify them.

## Reviewed model manifest

Artifact paths must be relative to and resolve inside the repository. The host accepts a local
operator-selected JSON manifest; it never discovers or substitutes a model.
Required model fields are `mpn`, `reference_voltage`, `frequency_hz`, `mode`,
`path`, `sha256`, `circuit_sha256`, `requirements_sha256`, `qualification`, and
`scenarios`. The circuit identity is the hash of the current source identity
and circuit result; the requirements identity is the retained requirements file
hash. See the raw simulation input in an engineering run for both.

`qualification` requires `model_sha256`, `evidence_path`, `evidence_sha256`,
`source`, `license`, `reviewed_by`, `status: "pass"`, and `coverage` listing all
three scenarios. The host retains and hashes the qualification artifact. These
fields record a reviewed external decision; they do not themselves prove that a
model reproduces the physical device.

The collector carries the exact UTF-8 requirements file as `requirements_manifest`.
Rust verifies its SHA-256 against `requirements_sha256` and extracts the unique
`requirements[]` entry with `id: "load_step_endpoints"`. Its `profiles` array
must contain exactly these two IDs, with the
requirements-owned current endpoints: `continuous_50mA_to_500mA` (`low_a: 0.05`,
`high_a: 0.5`) and `pulse_50mA_to_1A` (`low_a: 0.05`, `high_a: 1.0`). The Rust
judge checks that each `load_variation` spec names one required profile and
that its low/high currents exactly match this array. A model-owned copy of the
profiles is not authoritative. Missing,
duplicate VIN/profile pairs, unknown profiles, or mismatched endpoints block closed. Under this revised contract,
legacy three-scenario reports remain readable as historical artifacts but
cannot claim the two-profile coverage. Under the adopted closure-wave
requirements, the reviewed manifest expands this to six startup cases (three
VIN corners × zero/500 mA), six load cases (three VIN corners × two profiles),
and at least one input-variation case. Every case has a unique `case_id`; the
collector uses a hash of that ID for its output directory.

Each scenario object requires:

- `name`: `startup`, `input_variation`, or `load_variation`; load variation occurs
  once per VIN corner and required load profile.
- `deck`, `deck_sha256`: exact reviewed deck, referring to `../model.lib`.
- `window_start_s`, `window_end_s`, `max_step_s`, `event_s`: finite timing values.
- `target_v`, `settling_band_v`: positive voltage values.
- `limits`: numeric `{min, max}` for every acceptance metric.

Mandatory metrics are `vout_avg`, `vout_pp`, `overshoot_v`, and `settling_s`.
Input variation currently uses these generic windowed metrics and a reviewed
VIN-span limit. It does not independently enforce a particular rising/falling
line sequence, plateau duration, slew, or per-edge recovery protocol. The
requirements manifest has no adopted line-transient protocol. A passing input
case must therefore not be described as line-transient qualification; that
would require an adopted protocol and measured stimulus/recovery checks.
Input variation also requires positive minimum `vin_span`; load variation
requires positive minimum `load_span` and these fields directly on the flat
scenario object: `profile_id`, `load_low_a`, `load_high_a`, and
`load_tolerance_fraction` in the inclusive range 0–0.02 (the adopted 2% maximum).
Collection wraps this object under `spec` in the judge input.
The measured waveform's actual minimum and maximum must each be within the
declared fraction of the corresponding required endpoint. This checks endpoint
values only; it does not establish
that both rising and falling transitions occurred. For the adopted closure-wave
protocol, each load scenario also carries an explicit `vin_corner_v`,
`capture_end_s`, and six `edges`. The edges alternate three rising and three
falling transitions, each declaring `start_s`, `end_s`, `direction`, `from_a`,
and `to_a`. Rust measures the waveform at those times; labels alone cannot
satisfy the protocol. It requires 0.1 A/us ±10%, 2% plateau endpoint agreement,
10 ms pulse width, at least 100 ms between rising starts, stable 1 ms pre-edge
and final windows, absolute 3.135–3.465 V bounds, and at most 100 mV departure
from the pre-edge mean. Recovery must remain within 1% of the final window
mean from 1 ms after edge completion until the next edge. The measured load
must hold its declared plateau, including 100 ms before the first rise and
100 ms after the final falling edge completes. A
`reviewed_scenarios_sha256` manifest field, when present, must equal the
canonical hash of the ordered scenario specs.

Startup closure-wave specs declare `en_tied_to_vin: true`, a 1 ms
`vin_ramp_start_s`/`vin_ramp_end_s` interval, `vin_corner_v`, the expected
13.5 V crossing, `load_a`, and a 20 ms `capture_end_s`. Rust measures actual
VIN and VOUT, then checks 10–90% rise ≤8 ms, ≤100 mV overshoot and ≤3.465 V,
and ±1% settling from 10 ms through 20 ms after the crossing. Additional metrics are `vout_min`,
`vout_max`, `undershoot_v`, `duration_s`, `vin_avg`, and `iin_avg`. Windows and
limits require review against the frozen product requirements; no default
acceptance numbers are invented here.

For a positive startup load, the stimulus contract accounts for a discharged
output: at every sample from ramp start through capture end, measured `i(load)`
must be within 2% of `load_a * max(0, min(1, v(out) / 0.1 V))`. Once VOUT reaches
0.1 V, this requires the full declared load; it cannot be satisfied by removing
or reducing the load after regulation. The 0.1 V value is fixed fixture
semantics recorded by the `startup_load_compliance_voltage` requirement, not a
claim about the regulator IC. Zero-load startup remains strict under the same
measurement check.

Retain raw real-valued signals named `time`, `v(out)`, `v(in)`, `i(vin)`, and
`i(load)` for startup and load variation. Units come from the ngspice rawfile (`time`,
`voltage`, `current`); malformed/unsupported signals fail closed. The input-source
current retains SPICE's signed convention. This does not measure efficiency.

Malformed stimuli, incomplete observation windows and unstable reference
windows block measurement. Valid waveforms that violate startup or transient
acceptance limits produce failed scenario results. Synthetic test waveforms
exercise these decisions but never qualify a device model.

Each run uses a new directory. The default ASCII path keeps a 30 second
per-scenario timeout, a 32 MiB rawfile ceiling and a one-million-row limit.
Reviewed scenarios can opt into `raw_format: "ngspice-binary-le64"` with
`timeout_seconds` in the range (0, 3600], defaulting to 3600 seconds for that
format. The binary path allows up to 8 GiB and 100 million rows. It streams
and hashes the rawfile while retaining only the evaluator signals, using
checked allocations; it does not decimate data. At the row ceiling the five
retained columns alone can occupy about 4 GB, plus measurement working memory.
Process logs remain separate artifacts.

The trusted engineering host sets `TEMPER_SIMULATION_RAW_ROOT` to its owned
simulation output directory. Each binary scenario carries a relative
`raw_file` and `artifact_sha256`, not embedded raw bytes. Direct development
replays must supply that root explicitly. Absolute paths, traversal, symlink
escapes, unknown/mismatched formats and dual waveform inputs are rejected.
The collector must retain ownership of the directory while the judge runs;
this path validation is not a sandbox against concurrent filesystem changes.

The host also includes exact `settings_manifest` text and its SHA-256. Rust
checks both the text digest and equality of its parsed values with the scenario
specs. This avoids false identity mismatches caused by Python and Rust encoding
exponents differently. This transport change grants no model approval.

Qualification receipts require `id`, `synthetic: false`, and an exact pin in
`engineering/approved-evidence.json` before ngspice is invoked.

Requirements-stage list validation checks syntax, uniqueness and numerical
ordering; simulation admission additionally enforces the two profile IDs.
Named thermal limits distinguish U3 junction from L2 hotspot temperatures in
the requirements manifest. Their `conditions` require nonnegative finite
`iout_a` and finite `ambient_max_degC` above absolute zero; each component limit
must be at least that ambient temperature for this passively cooled design.
This does not implement physical thermal measurement.
