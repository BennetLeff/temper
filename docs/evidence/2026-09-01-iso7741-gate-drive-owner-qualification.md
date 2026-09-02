---
provenance: commit=373688e337f8df75b1d3dfa05a7f9ec2fcb6b00d dirty=true

title: ISO7741 gate-drive owner qualification — representative construction
date: 2026-09-01
status: rejected
candidate_id: iso7741-baseline
---

# ISO7741 gate-drive owner qualification

This record is the U5 representative-layout package for the ISO7741
gate-drive candidate. It is candidate-only evidence and is not a production
board change or an architecture approval. The representative fixture is
`elec/qualification/iso7741_gate_drive/layout/iso7741_gate_drive_fixture.kicad_pcb`;
its SHA-256 is
`2c947eb2215980062cdf2bd438616c96d451ef99c84a1e6cfa1e6f992263af3f`.

## Scope and construction identity

The fixture contains both complete high-side and low-side domains, two exact
`ISO7741FQDWWRQ1` DWW-16 barrier instances, two exact
`UCC27517AQDBVRQ1` DBV-5 driver instances, gate resistors, bootstrap parts,
test labels, and an explicit board-level isolation corridor. The reusable
construction identity is not the absolute fixture coordinate system. It is
the Rust-extracted local projection described by
`power_pcb_dataset/qualification/iso7741_gate_drive/construction_projection.json`.
Only translation and the declared quarter-turn rotations are eligible for
projection reuse; mirroring, layer flips, scaling, local-copper changes,
boundary-port changes, and undeclared transforms invalidate that identity.

The exact footprint bytes are digest-bound in the projection. Manufacturer
pin maps, controlled land-pattern authority, and the 3D conductor/mechanical
path report remain pending. The 14.5 mm DWW package headline is therefore not
used as a corridor result; complete installed geometry must demonstrate the
12.6 mm straight path and all loop limits together.

## Geometry and loop evidence

`geometry_evidence.json` records the acceptance limits and row IDs. The
straight corridor limit is 12.6 mm, each gate-loop limit is 200 mm², each
gate trace is at most 30 mm with its resistor within 5 mm of the driver, and
each bootstrap loop is at most 100 mm². The record remains pending because a
live pcbnew oracle, controlled footprint facts, and the signed mechanical
authority report are unavailable. No favorable geometry measurement is
claimed here.

The intended computation uses the existing Rust geometry kernels and the
sanctioned `temper_placer.geometry.kicad_transform` bridge. An asymmetric
non-orthogonal probe is required before accepting the transform: a
round-trip or a symmetric 90-degree probe is insufficient to distinguish
KiCad's R(-theta) placement convention from the wrong R(+theta) convention.

## Thermal and calibrated bench evidence

`thermal_evidence.json` freezes the 70 °C ambient corner and lists all active
ICs and support networks as pending until controlled derating limits and a
calibrated board thermal result exist. `bench_evidence.json` declares the
four required waveform channels and the short/open, domain-power-loss,
UVLO-ramp, stuck-PWM, stale-health, precharge, dead-time, and shutdown
latency challenges. It intentionally contains no captures, instrument
identity, or raw-data digest: the low-energy fixture and calibration record
do not exist in this run.

## Reproduction and blockers

From the repository root, the focused contract is:

```text
./.venv/bin/python -m pytest -q packages/temper-placer/tests/physics/test_iso7741_gate_drive.py
```

The U4 model tests pass. U5's artifact-contract tests are designed to pass
only for the candidate-local, pending records in this package. Live pcbnew
projection/oracle execution, manufacturer-controlled pin/land-pattern facts,
the signed mechanical report, and calibrated 70 °C/low-energy bench captures
are external blockers. Existing U4 rejection and the pending candidate facts
remain unchanged; this package must not be read as a favorable result.

Protected production paths, including `pcb/temper.kicad_pcb`, remain out of
scope and are not modified by U5.

## U6 internal decision package

U6 adds the immutable evidence index and owner-signoff index under
`power_pcb_dataset/qualification/iso7741_gate_drive/`. The evidence index is
a content-addressed DAG: the replay runner captures each referenced byte once,
then the Rust evaluator verifies object digests, the evidence root, named
scope-node digests, and the closed `iso.*` owner-role registry. The
`owner_signoffs.json` layer records all seven required internal roles as
pending; no A1-A7 signature bytes or favorable disposition are fabricated.

The canonical Rust replay result is `internal_decision.json`. The current
candidate is `rejected` because the existing U4/U5 evidence explicitly fails
`timing.non_overlap` and `power.gate_network_and_bias`; pending evidence and
pending owner rows cannot override those failures. If those failures are
removed while pending rows remain, the same evaluator deterministically emits
`stopped-indeterminate`. A clean replay of `evidence_index.json` reproduces
the committed decision byte-for-byte.

## U7 preliminary-authority packet

U7 adds a provider-neutral submission index at
`power_pcb_dataset/qualification/iso7741_gate_drive/authority/submission_index.json`
and a schema-valid placeholder input at
`authority/preliminary_ruling.json`. The placeholder is intentionally
unresolved and has no provider identity or signed artifact; it is not an A8
ruling. `scripts/check_iso7741_gate_drive_qualification.py --preliminary`
attaches these immutable inputs to the U6 evidence index and delegates
validation/classification to the Rust kernel, writing
`preliminary_decision.json` only when replay succeeds.

The U7 kernel preserves internal-result precedence: the current U6
`rejected` result remains `rejected` even if a synthetic or malformed
favorable response is supplied. A valid future receipt must match the
submission, envelope, construction projection, and allowed-transform-policy
digests and must carry an independently captured `iso.external_compliance`
artifact. Ambiguous or evidence-only responses stop for review; construction
or transform-policy changes reject this identity and require renewed U3-U6
qualification. No final routed-board approval field exists in the preliminary
decision schema.
