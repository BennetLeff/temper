# Circuit simulation scenarios

The mandatory scenario identities are `startup`, `input_variation`, and
`load_variation`. Their limits belong to the versioned requirements receipt;
this directory does not invent engineering limits. Switching ripple,
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

Each of the three scenario objects requires:

- `name`: `startup`, `input_variation`, or `load_variation` (once each).
- `deck`, `deck_sha256`: exact reviewed deck, referring to `../model.lib`.
- `window_start_s`, `window_end_s`, `max_step_s`, `event_s`: finite timing values.
- `target_v`, `settling_band_v`: positive voltage values.
- `limits`: numeric `{min, max}` for every acceptance metric.

Mandatory metrics are `vout_avg`, `vout_pp`, `overshoot_v`, and `settling_s`.
Input variation also requires positive minimum `vin_span`; load variation
requires positive minimum `load_span`. Additional metrics are `vout_min`,
`vout_max`, `undershoot_v`, `duration_s`, `vin_avg`, and `iin_avg`. Windows and
limits require review against the frozen product requirements; no default
acceptance numbers are invented here.

Retain raw real-valued signals named `time`, `v(out)`, `v(in)`, `i(vin)`, and
`i(load)` for load variation. Units come from the ngspice rawfile (`time`,
`voltage`, `current`); malformed/unsupported signals fail closed. The input-source
current retains SPICE's signed convention. This does not measure efficiency.

Each run uses a new directory, a 30 second per-scenario timeout, and a maximum
32 MiB waveform admitted to parsing. Process logs remain separate artifacts.

Qualification receipts require `id`, `synthetic: false`, and an exact pin in
`engineering/approved-evidence.json` before ngspice is invoked.
