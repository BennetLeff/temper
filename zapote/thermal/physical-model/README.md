# Bridge physical model

This directory owns the reviewed v1 input contract and diode-loss source
record. Rust (`zapote-thermal::physical_model`) is the authority for parsing,
network evaluation and replay.

The model is intentionally shared across the four GBU2510A terminals. It has
one package heat source, four explicit lead/barrel/solder paths, and one global
energy balance. The package node is connected to the cooled sink while each
lead node also connects to the separate board reservoir; package-to-sink,
package-to-lead, lead-to-board and per-lead residuals are retained. The current
bridge allowance is 40 W; waveform-derived diode-pair loss is reported inside
that allowance rather than added four times.

The baseline contract is created from a saved native extraction with
`baseline_contract()`. This keeps trace and pad UUIDs tied to the actual board
variant. The connections workstream has supplied baseline, 3 mm and 6 mm
candidate bundles; the 3 mm bundle is the reviewed constrained candidate for
the next comparison. A retained solver assessment is intentionally not claimed
until that candidate is integrated and its PFC waveform is captured through the
production runner.

Applicability stays `indeterminate` while GBU2510A package internals and
assembly heat paths are not byte-sourced. Numerical balance and stale-evidence
rejection are still enforced.

The standard replay does not claim manufacturer-source verification. A future
manifest can provide the archived source bytes and use
`evaluate_with_source_bytes`/`replay_with_source_bytes`; the hash and identity
markers are checked against the bytes, but `source_bytes_verified` stays false
until the exact digest is admitted by a reviewed source registry.
