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
variant. The `zapote-physical-contract` binary performs the same conversion
from retained `native.json` and `manufacturing.json` captures. Contracts for
the frozen baseline and the same-package 3 mm candidate are retained under
`variants/`; they are inputs to the FEM comparison, not qualification results.

Applicability stays `indeterminate` while GBU2510A package internals and
assembly heat paths are not byte-sourced. Numerical balance and stale-evidence
rejection are still enforced.

The production unit manifest now supplies the archived Yangjie source bytes.
Source identity passes only for the reviewed PDF digest. The 1 V at 12.5 A
point remains insufficient to establish a hot-current loss bound.

## Resolved joint FEM

`joint_fem`, `joint_mesh` and `joint_physics` represent copper, FR4, solder and
lead as four conforming materials. `joint_model` couples the four local solves
to one shared package source and an explicitly assumed sink path. The copper
conductivity depends on solved temperature; Elmer computes current and Joule
heating in the actual joint solids.

The [comparison](comparison.md) links the retained baseline and 3 mm runs.
The mandatory common harness checks their raw evidence, not just summaries.
Large meshes are stored with lossless gzip; raw-byte hashes retain their original
identity. The historical 40-case neck and 20-case cooling replays are unchanged.

The reduced `physical_model` network remains a separately labeled approximation.
Its all-series terminal resistance is not used as the resolved FEM resistance.
The resolved joint model still assumes uniform branch current through short
pad-overlap regions; exact whole-board current distribution is not established.

[Memory preparation](memory-review/) verifies selection of the new portable
validation note. It is not evidence of delivery to a later agent.
