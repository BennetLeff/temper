# Construction validation — 2026-09-18

**Acceptance incomplete.** The active Rust assessment now runs. Source/native
connectivity is supported, and routing repairs clear nine spacing findings
and eight nominal-current findings. Three 1.94 mm TEA package gaps still fail
the 2 mm construction screen. See [RUST-INTEGRATION.md](RUST-INTEGRATION.md)
for current checks and [the final common run](evidence/rust-integration-01/common-suite-03/summary.json).
No fabrication or powered test is authorized by these artifacts.

## Historical construction checkpoint — 2b65c3e18

The table and unsupported-entry diagnosis below record the original checkpoint,
before Rust integration and routing repair. They are not current results.

| Check | Result | Retained evidence |
| --- | --- | --- |
| Atopile 0.2.69 compilation and strict source export | Pass, 66 components | `source-03/build-receipt.json` |
| KiCad 10.0.4 ERC, all severities | 0 violations | `evidence/erc-final.json` |
| KiCad DRC, all track errors, schematic parity, all severities | 0 violations / 0 unconnected / 0 parity issues | `evidence/drc-final.json` |
| Rust saved-board stackup | Pass: 2 copper layers, 1.600 mm total | `evidence/rust-stackup.json` |
| Existing common Rust unit suite | Fail: active source entry unsupported; six other units indeterminate | `evidence/common-suite-01/summary.json` |
| Existing direct power-entry checks | 13 fail / 6 indeterminate / 3 pass | `evidence/rust-power-entry.json` |
| Source/pad wiring review | Active bridge pin map, shunt sides and F2 split checked independently | review notes below |
| Mechanical / thermal / interruption / surge / powered operation | Not qualified; no physical tests | `MECHANICAL.md`, parent `CLOSEOUT.md` Q1–Q5 |

## Why the original Rust assessment failed

`zapote_erc::power_entry::ENTRY` accepts only
`elec/src/power_entry_unit.ato:PowerEntryUnit`. This authored variant is
`elec/src/power_entry_active_unit.ato:PowerEntryActiveUnit`. The common runner
reports `wrong entry or empty compiled circuit` before its unit assessment.
The direct runner also exposes two representation/profile problems:

- `DRC.NATIVE.DOCUMENT_BINDING`: `expected one net` on deliberately NC pads.
- `DRC.NATIVE.CLEARANCE_PROFILE`: the passive profile names old rectifier nets;
  it does not classify the active bridge's new high-voltage nets.

Those are software coverage gaps, not proof of an electrically wrong board,
and not permission to report acceptance. In particular, no new ampacity,
high-voltage spacing, manufacturing or loss/thermal qualification is claimed.
The direct runner's nominal-model pass evaluates its existing baseline model;
it does not establish active-rectifier performance. Do not rename the entry,
copy passive survival limits, suppress errors, or rebind old model evidence
just to obtain a green result. Concrete active-unit contract work was needed at that checkpoint; it is now implemented.

## Explicit NC conversion

The compiler emits 49 net records, including four singleton TEA pins:
`hvs1` U1.4, `comp` U1.9, `hvs2` U1.11 and `hvs3` U1.15. They intentionally
have no external connection. The native schematic marks them NC and the PCB
pads have no assigned net. Native extraction therefore has 45 connected
clusters. `candidate/source-manifest.json` retains the original compiler graph
and separately records `native_no_connects`; it does not rewrite the compiled
source to pretend those records never existed. `unconnected_pads` refers to
unrouted required connections, not intentional NC pins. The active Rust binding now enforces this distinction explicitly, including
physical pad presence, multiplicity and the empty native net.

## Historical bytes versus current evidence

`evidence/final-artifacts.json`, `evidence/native.json`, the original Rust stackup
receipt and `renders/` bind the original construction checkpoint, not the
repaired PCB. Their hashes are preserved; these historical receipts were not
rewritten to claim a new execution. The current source manifest and active
`units.json` instead bind `evidence/rust-integration-01/native-contact-repaired.json`; current
DRC, stackup, manufacturing and common-suite reports live in that new directory.
The schematic is unchanged.

`evidence/native-generation-manifest.json` describes the initial generated
skeleton, before the passive copper was incorporated. `evidence/routes-receipt.json`
describes route application before metadata hiding and native zone refill.
Their hashes intentionally differ from the final PCB. Neither is a final-board
acceptance receipt. Historical intermediate boards were not all retained, so
these records alone are not a complete byte-by-byte replay chain. A fresh replay
creates new receipts; do not edit old receipts to claim they measured new bytes.

## Review disposition

Two independent Luna reads checked source pins, compiled connectivity, physical
pad assignments and the final native checks. Review found the unsupported Rust
entry, NC representation difference, intermediate/final identity ambiguity,
provisional fuse land pattern, enlarged outline and separate F1 consumable.
The identity/NC distinctions are documented and the final bytes bound; BOM
includes F1 and two clips; the 310 × 210 mm outline is explicit. That review preceded Rust integration. The current package-spacing findings
and fuse mechanical fit remain release blockers. No hardware acceptance is inferred.

The schematic PDF is a source-derived pin/net projection with labelled box
symbols. It is useful for parity review, not a conventional functional circuit
sheet. The 3D preview omits F2/clips, heatsinks and inherited custom-part bodies.
Visual review checked the complete outline and readable, unclipped schematic;
it did not verify an assembled enclosure.

The memory-selection attempt rejected changed bytes in an existing catalog
entry. Its failure is retained under `memory/`; no successful memory gate or
validated campaign handback is claimed. The frozen harness was not changed.
