---
title: CT07/T2 owner qualification — canonical owner result
date: 2026-09-01
status: stopped-indeterminate
candidate: ct07-t2-u4-candidate
---

# CT07/T2 owner qualification

The adjacent JSON is the machine truth for the complete U1-U9 owner workflow.
Rust evaluates the committed evidence index as `stopped-indeterminate`; all 20
requirements are explicitly owned, and none is inferred complete from design
files or simulations. OCP-02 remains DNF. This record does not authorize a
production board, T2 population, a refloorplan, or a production release.

## Canonical result and requirement trace

The construction identity is deliberately `pending-u6-freeze`. All 16 internal
axes are pending, there are no signed dispositions or raw representative records,
and no preliminary limitation is active. The exact next authorities are:

| Requirements | Implementation owner | Exact next authority |
|---|---|---|
| R1, R4, R6 | `ct07.board_product_safety` | CT07 board/product safety owner |
| R2, R3, R5, R7-R10 | `ct07.electrical` | CT07 electrical owner |
| R11, R13 | `ct07.mechanical_assembly` | CT07 mechanical/assembly owner |
| R12 | `ct07.pcb_insulation_layout` | CT07 PCB/insulation/layout owner |
| R14-R15 | `ct07.sourcing_manufacturing` | CT07 sourcing/manufacturing owner |
| R16 | `ct07.external_certification` | A7 external certification authority |
| R17 | `ct07.verification` | CT07 verification owner, then A7 for any larger sample requirement |
| R18 | `ct07.verification` | CT07 verification owner |
| R19 | joint campaign owner | ISO U9 joint-campaign evaluator |
| R20 | downstream production approval | final A7 review and separate A1 board-safety authorization |

The canonical JSON enumerates R1-R20 individually; the table groups only rows
with identical ownership and next-authority semantics.

## Owner-floor protocol and record provenance

The owner-floor protocol is an **engineering screen**, not a reliability or
certification claim: at least five complete assemblies, at least two
independently built lots, three valid repetitions per electrical corner, and
zero false trips, missed trips, geometry failures, or post-stress failures.
Any larger A7 sample requirement is pending A7's protocol ruling. No invalid or
excluded records currently exist; the canonical JSON retains an explicit empty
`invalid_or_excluded_records` array so future invalid records must be retained
with their predeclared reason instead of disappearing from the evidence set.

## Bound candidate

The selected candidate is `ct07-t2-u4-candidate`, backed by the canonical
U4-B generated manifest at
`power_pcb_dataset/qualification/ct07_t2/generated/manifest.json` with SHA-256
`05cdd8c8f88a89298fe9a3a72e839250df922d8179eec37040c6049914e292c6`.
That manifest is currently `stopped-indeterminate` and explicitly publishes
candidate exports only; it is not a qualification verdict.

The proposed exact part identity is ICE Components `CT07-1000`. The authority
request packet reports an official manufacturer PDF dated 2024-10-31, but its
bytes are not a controlled project attachment and no controlled mechanical
drawing is available. The packet is a request for evidence, not an approval or
source record.

## U7-A result

`identity_eligibility.json` binds the candidate source bytes, part identity,
document references, lifecycle record, approved-source record, dated sourcing
record, and delivered-marking record under identity digest
`9600fad8ef01fe81811657b7b56c82671f9d82537b318c3ebea5a4b76e4d4284`.

The Rust-owned U7-A evaluator returns `stopped-indeterminate` because the
following required records are pending:

- U4-B candidate identity is not eligible; its current status is
  `stopped-indeterminate`.
- Current controlled datasheet bytes and a controlled drawing revision are
  unavailable.
- Lifecycle status and approved-source evidence are unavailable.
- Dated sourcing evidence and delivered sample marking are unavailable.

No mismatch or failed technical result is being converted into an approval.
The corresponding `construction_manifest.json` entry sets
`construction_release_eligible` to `false`; therefore U6 two-lot fabrication
cannot be released from this checkpoint. OCP-02 remains DNF.

## U7-B final closure

The U7-B package is bound by `evidence_index.json` to the pending U6
construction identity, the U5 electrical protocol, the U9 mechanical protocol,
the 30-row `single_fault_analysis.json` matrix, and the 16-axis
`authority/internal_dispositions.json` projection. Rust validates exact
coverage, the OCP-02 DNF baseline, construction/projection/policy digests,
raw-byte evidence hashes, and the owner/verifier role separation. The replay
result is `stopped-indeterminate`: U7-A remains pending, U5/U6/U9 evidence is
pending, every fault outcome is a placeholder rather than a favorable result,
and no owner signature or manual verification digest is present. This is a
controlled stop; it is not an approval and cannot release fabrication.

## Reproduction

After rebuilding the pyo3 extension using the repository-supported extension
workflow and checking freshness immediately before replay:

```bash
python3 scripts/check_ct07_u7_a_identity.py
```

The script reads the package and selected U4-B source once, verifies the
source digest, and calls `temper_quality_oracle`'s
`evaluate_ct07_u7_a_identity_json` registration. Missing controlled evidence
must remain `stopped-indeterminate`; no signer, approval, or fabrication
authorization is inferred from automation.

U7-B can be replayed with:

```bash
python3 scripts/check_ct07_u7_b_closure.py
```

The helper computes byte digests for the evidence index and both controlled
closure files, injects the runtime evidence-index binding into the disposition
projection, and delegates completeness and verdict policy to the Rust
evaluator. It must continue to stop when controlled evidence is missing; it
does not synthesize samples, approvals, signatures, or favorable axes.

The full canonical owner replay is:

```bash
make extensions-check
python3 scripts/check_ct07_t2_qualification.py \
  --output docs/evidence/2026-09-01-ct07-t2-owner-qualification.json
cmp power_pcb_dataset/qualification/ct07_t2/internal_decision.json \
  docs/evidence/2026-09-01-ct07-t2-owner-qualification.json
```

Replay is offline. The runner permits this one named documentation artifact and
the qualification namespace only, snapshots the full R18 protected set, reads
each evidence byte sequence once, and delegates identity, completeness, and
verdict policy to Rust. Missing U6/U5/U9 records, owner signatures, controlled
source evidence, a second lot, A5 verification, and A7 disposition remain
pending; the named owners above must supply them in dependency order.
