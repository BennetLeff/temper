<!-- provenance: commit=85b4e400572a77d18f0ee6c644a532ab0a55dd8e dirty=true (decision package generated and replayed in this worktree; commit is the campaign base) -->
# Isolation component-architecture qualification — 2026-09-01

## Decision

This is a bounded qualification result for the current single-board PD3
refloorplan. It evaluates seven declared architectures across the three
families in scope: retain-with-slot, component/package replacement, and
hybrid. The governing straight-corridor requirement remains 12.6 mm. No
candidate qualifies both required domains in this campaign: five are
`rejected` and two are `stopped-indeterminate`. This is a decision-quality
negative/stopped result, not a market-wide absence claim and not permission to
weaken PD3, protection coverage, or the production board.

The Rust `temper-quality-oracle` evaluator owns schema validation, required
axis completeness, fail-closed aggregation, and stable ordering. Every
non-pending straight-corridor result is bound to a `source.path` and
`source.sha256` that exactly matches one of that candidate's immutable
repository evidence references. The Python runner verifies the current bytes
and, when present in the campaign base commit, the base-tree bytes too. A
new/replacement geometry source therefore cannot establish a pass in the same
campaign; it must remain pending. The Python runner otherwise owns only
offline manifest loading, protected-input hashing, and output I/O. A failed
axis has precedence over a pending axis; with no failures, any pending
mandatory axis produces `stopped-indeterminate`; only all-pass candidates can
qualify.

## Candidate results

| candidate | family / domain | verdict | exact geometry result | decision blockers (stable reason codes) |
|---|---|---|---|---|
| `sensing-retain-slot-t1-cst3015` | retain-with-slot / sensing | **rejected** | T1 straight gap 9.1 mm < 12.6 mm | `geometry.straight_gap_below_pd3`; `lifecycle.current_confirmation_missing`; `sourcing.approved_distributor_unconfirmed`; `slot.certification_ruling_missing`; `slot.pd3_credit_pending_lab`; `slot.structural_mounting_authority_missing`; `sensing.hf_and_thermal_rederivation_missing` |
| `sensing-retain-slot-t2-cst3015-dnf` | retain-with-slot / sensing | **rejected** | T2 straight gap 9.1 mm if placed < 12.6 mm | `geometry.straight_gap_below_pd3`; `lifecycle.current_confirmation_missing`; `sourcing.approved_distributor_unconfirmed`; `slot.certification_ruling_missing`; `slot.pd3_credit_pending_lab`; `slot.structural_mounting_authority_missing`; `sensing.ocp02_rederivation_missing`; `sensing.t2_dnf_owner_decision_required` |
| `sensing-replacement-lem-lpsr15` | replacement / sensing | **rejected** | measured primary-secondary creepage 8.26 mm < 12.6 mm | `geometry.straight_gap_below_pd3`; `lifecycle.current_confirmation_missing`; `sourcing.approved_distributor_unconfirmed`; `package.approved_footprint_missing`; `mechanical.approved_land_pattern_missing`; `certification.board_pd3_applicability_missing`; `sensing.hall_interface_redesign_required`; `sensing.hall_thermal_rederivation_missing`; `sensing.ocp02_dnf_owner_decision_required` |
| `sensing-hybrid-aperture-ct07-t2` | hybrid / sensing | **stopped-indeterminate** | no approved land pattern for a straight measurement; 13.2655 mm is only a modeled aperture path | `lifecycle.current_confirmation_missing`; `sourcing.approved_distributor_unconfirmed`; `package.approved_aperture_footprint_missing`; `geometry.approved_aperture_footprint_missing`; `aperture.certification_ruling_missing`; `certification.aperture_pd3_credit_missing`; `aperture.conductor_retention_authority_missing`; `sensing.aperture_burden_redesign_required`; `sensing.aperture_thermal_rederivation_missing`; `sensing.t2_dnf_owner_decision_required` |
| `gate-retain-slot-u6-ucc21550` | retain-with-slot / gate drive | **rejected** | U6 straight gap 8.1 mm < 12.6 mm | `geometry.straight_gap_below_pd3`; `lifecycle.current_confirmation_missing`; `sourcing.current_orderability_missing`; `slot.certification_ruling_missing`; `slot.pd3_credit_pending_lab`; `slot.routing_and_mechanical_review_missing` |
| `gate-replacement-iso7741fqdwwrq1` | replacement / gate drive | **stopped-indeterminate** | straight geometry **pending**: 14.5 mm is contextual package-study information, not an accepted complete-footprint measurement | `geometry.approved_replacement_footprint_missing`; `lifecycle.current_confirmation_missing`; `package.local_driver_footprints_missing`; `gate.two_local_drivers_redesign_required`; `gate.timing_shutdown_uvlo_reverification_required`; `gate.integration_bom_looparea_thermal_missing` |
| `gate-hybrid-ucc21550-edge-slot` | hybrid / gate drive | **rejected** | U6 straight gap 8.1 mm < 12.6 mm; 14.85 mm slot path is not straight evidence | `geometry.straight_gap_below_pd3`; `lifecycle.current_confirmation_missing`; `sourcing.current_orderability_missing`; `slot.certification_ruling_missing`; `slot.pd3_credit_pending_lab`; `slot.routing_and_mechanical_review_missing` |

The package contains every mandatory axis for every candidate. In particular,
the staged T2/OCP-02 state is represented explicitly: reinstating T2 or
replacing it changes independent fault coverage and requires the board owner's
approval. The two pending candidates are not silently promoted by their
promising package or modeled-path geometry. The five rejected candidates have
at least one hard failure, even where additional pending work is also listed.

## Protected inputs

The runner pins and verifies these bytes before and after evaluation. Geometry
sources are separately digest-bound to candidate evidence references and to
the provenance base tree before evaluation. The
following SHA-256 values are the campaign-base identities copied into both the
manifest and the canonical package:

| path | SHA-256 |
|---|---|
| `docs/ENVIRONMENTAL_SPEC.md` | `afa367890d4872cce0033455ded49ea9b5826b9ba3a25229f4ec336d34cbaccf` |
| `elec/domain_manifest.yaml` | `f1899c87a61f579e2a92dbd673c1ad29036aed463b2f3fcc4ff7cca7f034bae3` |
| `packages/temper-placer/src/temper_placer/core/isolation_constants.py` | `486d54267087b467b4148e7eb3c91106f3950fc3784e527d786cf3f346aeae21` |
| `pcb/temper.kicad_pcb` | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| `power_pcb_dataset/drc_ceiling.json` | `c6b2198e62ca5b15878884b1e2822a8b3bbd7372ace8f6198aeccffe83189fb2` |

No production PCB, DRC ceiling, electrical domain manifest, environmental
specification, or isolation-constant baseline was changed by this campaign.

## Reproduction

From the repository root, with the supported extension already rebuilt and
freshness checked:

```bash
env -u CONDA_PREFIX make extensions-check
env -u CONDA_PREFIX uv run python scripts/check_isolation_architecture_qualification.py \
  --manifest power_pcb_dataset/isolation_architecture_candidates.json \
  --output /tmp/isolation-qualification.json
cmp --silent /tmp/isolation-qualification.json \
  docs/evidence/2026-09-01-isolation-component-architecture-qualification.json
```

The runner is offline: URLs in the manifest are immutable citations and are
not fetched during replay. The output is canonical Rust-owned JSON, ordered by
candidate ID and evidence-axis/reason code. A cold reviewer can reproduce it
without an agent transcript or temporary evidence.

## Next external authorities

Before a new floorplan solve, the board owner and the relevant authorities
need to close the following bounded items:

- certification/mechanical authority: decide whether the CST3015 closed-end
  slot, UCC21550 edge slot, or CT07 aperture earns the claimed PD3 insulation
  path credit, and provide conductor retention, vibration, strain-relief,
  thermal, assembly, and service evidence;
- electrical owner: re-derive the CT07/LPSR transfer, burden, saturation,
  thermal, and high-frequency behavior, and decide whether OCP-02 remains DNF
  or gains approved independent coverage;
- gate-drive owner: produce approved local-driver footprints and re-verify
  the ISO7741 two-package channel, timing/dead-time, shutdown, UVLO, loop-area,
  BOM, thermal, and failure-mode contracts;
- sourcing/manufacturer authority: refresh lifecycle and approved-source
  evidence for any candidate that survives the technical reviews.

Only after those authorities produce complete evidence can a candidate move
from pending to qualified. Any selected architecture must hand off its
approved electrical and footprint contracts to a separate refloorplan unit;
this qualification package does not mutate the production board.
