# Active-rectifier Rust integration

2026-09-18. Scope: the existing unit validators now evaluate this circuit and
its actual saved copper. This is construction screening, not protection or
hardware qualification. The generic campaign/evidence harness remains frozen.

## What changed in the checks

- `zapote-erc::power_entry_active` names the distinct active entry and pins all
  66 component identities/values and all 49 compiled net memberships. The
  boost, sensing, relay, EMI and bleeder networks remain part of the contract.
- The four reviewed TEA no-connects remain in the source census. Native
  binding requires each physical pad, its multiplicity and its unassigned
  net; it rejects missing, duplicated or connected NC pads. The transport
  manifest cannot nominate extra exceptions.
- The existing CCM current model supplies the waveform. Positive and negative
  half-cycles use HL/LR and HR/LL respectively. At the nominal 15 A RMS input,
  each ideal bridge channel has 15/sqrt(2) A RMS over the full line cycle.
  This does not validate controller timing or body-diode commutation.
- F2 current follows the physical capacitor split: C40 is diode-side, the
  bulk bank is fuse-side. The sharing vertices include boost-diode pulses
  through F2 and the local-capacitor extreme; average output current is not
  used as a fuse-current rating. Startup/fault current is outside this model.
- The existing copper/contact/via checks consume those injections. P3 retains
  the boost gate path and adds four active gate paths with their actual source
  returns. Power-loop checks use MOSFET power terminals, not TEA sense taps.
- Spacing uses the retained construction floors: 0.2 mm functional, 2 mm to
  elevated-voltage domains and 6 mm to PE. High-side gate/bootstrap nets share
  their source's floating domain, but still receive the functional check.
  The bleeder midpoint is included as elevated voltage. This is a copper
  clearance screen; surface creepage and insulation qualification remain open.
- The passive GBJ/GBU loss and thermal models are not applied to the active
  devices. Their required rule IDs report explicit indeterminate coverage;
  supplying those model inputs to this active path is rejected.

## Findings and repair scope

The first active scan found 12 spacing failures. Three are intrinsic to the
standard TEA footprint: U1 pads 3–5, 10–12 and 14–16 have
2 × 1.27 − 0.60 = **1.94 mm** copper spacing against the **2 mm** construction
floor. Moving traces cannot change those gaps. The standard pads and floor
are retained, so these remain failures pending an engineering disposition.

The nominal branch-current screen also found eight 3 mm trace segments
carrying 15 A RMS against an 11.893 A screen at 70 µm copper and an assumed
20 °C rise. The repair widens the affected paths to 4.3 mm and adjusts nearby routing.
Passing that screen does not qualify hot copper, pad/barrel bottlenecks,
parallel current sharing or installed cooling.

Initial board/source bytes and findings are retained under
[`evidence/rust-integration-01/`](evidence/rust-integration-01/).
The first complete run (`common-suite/`) stopped on a RECTIFIER_L current-graph
split: a finite-width copper contact was connected in KiCad but unresolved by
the Rust current model. The narrower clearance check did not establish a
complete current result. That failed run is retained; its output must not be
reported as zero current failures. The explicit route-junction repair makes both endpoints meet at (5, 127.0).
A second run (`common-suite-final/`, despite its intermediate name) completed
current analysis but exposed a loop-adapter omission: intentional NC pads were
being treated as conductors. The adapter now excludes only the four reviewed
NC endpoints after full source/native binding, with a real-board regression
that also rejects an accidentally connected NC pad. Neither failed/intermediate
run is relabelled as a final pass.

## Final verification

Current PCB SHA-256:
`b0e5d537b0a827eac693b1b0373c650e6b2ef14637c3caf7d7c0a042695cb36b`.
The source manifest, fresh native export, manufacturing extraction and native
execution receipts bind these bytes. See
[the final seven-unit summary](evidence/rust-integration-01/common-suite-03/summary.json)
and [power-entry report](evidence/rust-integration-01/common-suite-03/power-entry.json).

- Full active runner completes without a runner error; all 70 required rule IDs
  are represented. `suite_changed_during_run` is false. Power entry remains
  **FAIL** for the three TEA package gaps; the six other units are indeterminate.
- Nine route-spacing findings and eight determined nominal branch-current
  findings are cleared. The current report is **INDETERMINATE**, not a current
  capacity qualification: local pad/via sharing, unsupported copper-area
  contacts and excluded currents retain explicit coverage gaps.
- Loop topology: 13 pass findings, with geometry/inductance obligations still
  indeterminate. The intentional NC pads do not become conductors or vanish
  from the physical/source census.
- KiCad 10.0.4 ERC and DRC: zero violations, unconnected items or parity issues.
  Stackup and saved-board/native binding pass. Manufacturing checks execute
  but retain unresolved geometry/assembly coverage.
- Passive loss/candidate reports are null for this active unit; the corresponding
  obligations remain indeterminate, not silently omitted or qualified.
- Focused verification: 99 ERC library tests, 5 active ERC integration tests,
  11 active harness tests and 6 native-binding tests pass. Import-boundary,
  regeneration and source diff-whitespace checks pass. Raw Cargo output
  retains terminal blank lines, which the full diff-whitespace check reports.
- The optional full workspace run was interrupted after 28 minutes in the
  unchanged retained shunt-assembly thermal replay; no complete workspace pass
  is claimed. The separate maintained GBJ suite was interrupted after 20 minutes
  in its thermal replay. Completed output is retained. The default legacy
  manifest also has a pre-existing GBU-versus-GBJ loss-data mismatch; this change
  does not claim to repair or pass that obsolete comparison path.

The updated full-board copper PDF and 3D image were visually inspected. They
show the complete outline and repaired routes; absent F2/clips, heatsinks and
several custom bodies still prevent assembled-fit validation. The earlier
`geometry-repair-receipt.md` and two intermediate common runs are historical,
not the current verification authority.

Review: the part-contract uniqueness/set-equality gap and P1 adapter test gap
were fixed. Fresh current evidence closes the stale-board-identity finding.
The actual runner run confirms model suppression and complete rule coverage;
helper tests reject supplied incompatible evidence. An automated end-to-end
runner mutation test and independent cross-model review were not performed.
No additional generic evidence-harness development was undertaken.

## Remaining engineering decisions

1. Resolve the TEA package-spacing conflict against the actual functional
   insulation requirements and manufacturer layout guidance. No package-pad
   narrowing or numerical waiver is credited here.
2. Finalize F2 clip/fuse fit and application coordination; see
   [MECHANICAL.md](MECHANICAL.md) and [Q1–Q5](../CLOSEOUT.md).
3. Supply active-device loss/thermal evidence, surface-path insulation inputs,
   bootstrap/commutation/startup evidence and the required qualification work.

No procurement, fabrication, powered operation or new protection qualification
is part of this integration.
