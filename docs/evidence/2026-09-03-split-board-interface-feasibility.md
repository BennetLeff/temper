<!-- provenance: admission-scoped U7 early-terminal evidence; no production artifacts changed -->
# Split-board interface feasibility — U7 early terminal record

## Decision

The split-board feasibility campaign stops as **`stopped-indeterminate` at U1
admission**. The upstream joint qualification is not eligible for
refloorplanning: the ISO gate-drive domain is **`rejected`**, CT07/T2 sensing
is **`stopped-indeterminate`**, and the combined candidate is absent
(`not-materialized`). This is an upstream admission stop, not a candidate
rejection and not an architecture no-go.

No U2-U6 work was reached. Consequently this record contains no crossing,
electrical, connector, board, topology, DRC, route-capacity, aggregate-fit,
or spatial-feasibility evidence. It makes no spatial feasibility claim and
does not infer that a two-board architecture is feasible or infeasible.

Production authorization is explicitly **denied**. `geometry_admitted` is
false, `production_authorized` is false, and this record is not a production
schematic, PCB, routing, certification, or release approval.

## Exact input bindings

The U7 artifacts bind the current bytes of the admission package and its
upstream authorities:

| Artifact | SHA-256 |
|---|---|
| `power_pcb_dataset/qualification/split_board_feasibility/admission_decision.json` | `f5c55a33fad9d03287847b7cd2a74135f9bcc569c85d006bdc0d07425944e1af` |
| `power_pcb_dataset/qualification/split_board_feasibility/manifest.json` | `7cf4540bf0bd4f35f21a79f059cf3798f18fdca4f01edf6691c44ed6aee6ac32` |
| `power_pcb_dataset/qualification/split_board_feasibility/evidence_index.json` | `8b56c26314281ea4a65c22f7819150c61133434da6a2c8f2a980a63903edbfe2` |
| `power_pcb_dataset/qualification/split_board_feasibility/owner_signoffs.json` | `41dacd2083c3f570564ed493e5dc140c16db975628ef6162b5f4657cbb63a829` |
| `power_pcb_dataset/qualification/split_board_feasibility/decision.json` | `693da8b599538a2dda1b4ca51a1c2f27ab14f9227ae9086f92e9eb4a5c3d1aee` |
| `power_pcb_dataset/qualification/isolation_joint/decision.json` | `05de8d00f4fb1a33c4c49048b3bb82ed2c749c2496e6c6da8318203c5f03501c` |
| `power_pcb_dataset/qualification/isolation_joint/contract.json` | `68c5762c584d5abb1728e45fb34bfa22f23dc110b47b3f5fd79ee898f2f73f1f` |
| `elec/qualification/isolation_joint/interface_contract.json` | `53638e91ad0956f8ac1e1d3eef593a93ceea7a6e2f956dc4d0fcb06b4a01ce04` |
| `elec/qualification/isolation_joint/validation/fixture_contract.json` | `2e821c247346e5747a281681cd4d6a6d8533d2db0054a1ae21345be22b99b30a` |
| `power_pcb_dataset/qualification/isolation_joint/manifest.json` | `107fec540404057fd0f4bdf7dc8edab9c593fe33a504f3dc0b372358e3de13df` |
| `power_pcb_dataset/qualification/isolation_joint/combined_candidate.json` | `afd893ffb812ae0f1803f8d2ab95e0b1e4ef0e636b1535f072fd9234be0ea9ff` |

The final four bindings are the U9 evidence authorities. The combined
candidate file exists as a controlled record, but its own status is
`not-materialized`; it is therefore treated as absent for admission and
cannot contribute geometry evidence.

## Reached and not reached

U1's admission identity/limitations axis is the only upstream gate reached.
U7 records that terminal stop and freezes its scope. U2, U3, U4, U5, and U6
are explicitly **`not-reached`**, not pending evidence to be read as a
partial pass:

| Unit | Status | Boundary |
|---|---|---|
| U1 admission | `stopped-indeterminate` | Upstream joint result is not `eligible-for-refloorplan`. |
| U2 crossing inventory | `not-reached` | No live crossing or domain contract was evaluated. |
| U3 electrical/safe-state budgets | `not-reached` | No live power, timing, analog, return, or fault evidence exists. |
| U4 connector contract | `not-reached` | No connector, pinout, or mating evidence was selected. |
| U5 candidate materialization | `not-reached` | No two-board KiCad candidate was admitted or created. |
| U6 topology/geometry/DRC | `not-reached` | No spatial, barrier, aggregate, route-capacity, or DRC measurement exists. |
| U7 terminal aggregation | `stopped-indeterminate` | Early terminal record only; no candidate-level verdict. |

No human signatures are fabricated. `owner_signoffs.json` has an empty
`signoffs` list and empty `signature_artifacts`; the role matrix is only a
declaration of the reviews required if admission later succeeds.

## Required next authority

The ISO qualification owner must resolve the rejected gate-drive candidate
and its missing U7 approval. The CT07/T2 owner must resolve the
stopped-indeterminate U8 handoff. The joint owner must then materialize the
combined candidate and replay the U9 package to the exact
`eligible-for-refloorplan` verdict required by U1. Only after that succeeds
may U2-U6 derive and measure candidate-local interface and floorplan axes.

This early stop does not weaken the 12.6 mm governing target, does not reject
the two-board architecture, and does not authorize production work.

## Reproduction and checks

The five JSON artifacts are machine-readable. Validation for this record
checks JSON syntax, resolves every referenced path from the repository root,
and recomputes each bound SHA-256 over the current bytes. The checked values
are recorded in `evidence_index.json`, `owner_signoffs.json`, and
`decision.json`; no circular self-digest is introduced.

```bash
make extensions-check
uv run --no-sync python scripts/check_split_board_feasibility.py --mode admission
uv run --no-sync python scripts/check_split_board_feasibility.py --mode terminal
uv run --no-sync python scripts/check_split_board_feasibility.py
```
