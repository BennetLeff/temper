# Physical stackup repair — 2026-09-11

The current-sense initializer omitted dielectric thickness. KiCad persisted that as zero in the FR4 core, while `general.thickness` remained 1.6 mm. The native export omitted stackup information and the Rust acceptance path had no stackup rule. The real board therefore passed the former electrical/geometric suite despite an inconsistent physical model.

## Repair and prevention

- `DRC.BOARD.STACKUP`, owned by `zapote-drc::stackup`, inspects the complete native PCB S-expression. Its parser is copied from Temper's `temper-design-bundle`, with provenance in `zapote/ports.toml`; no donor runtime dependency or Python engineering policy was introduced.
- The normal current-sense path requires `board_file_utf8` in the native export and checks its SHA-256 against the board identity before evaluating the stackup. Missing board text, mismatched bytes, missing/zero/negative/nonfinite thicknesses, ambiguous fields, copper census/order mismatch, missing intervening dielectric, and inconsistent total fail closed.
- Total thickness includes copper + dielectric + mask. The 0.000001 mm allowance is for serialization rounding, not a fabrication tolerance. Reference: [KiCad physical stackup documentation](https://docs.kicad.org/6.0/en/pcbnew/pcbnew.pdf) and [native board format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/).
- The initializer and canonical PCB now specify a 1.44 mm FR4 core. With 0.07 mm copper and 0.01 mm mask on each side, total thickness is 1.60 mm.
- The reusable `stackup_check` Rust example accepts any native PCB. Zapote's validation contract requires it for new/changed unit acceptance. Historical RTD evidence has not been requalified or silently rewritten.

## Evidence

| Check | Receipt |
|---|---|
| Original board rejected by regression before implementation | `test-before.log` — assertion failed because the old harness omitted the rule |
| Same real-board regression after gate implementation | `test-after-gate.log` — passed before PCB repair |
| New gate on original board | `stackup-before.json` — FAIL: dielectric 1 thickness 0 |
| New gate on corrected board | `stackup-fixed.json` — PASS, total 1.600000 mm |
| Native KiCad save/reload | `native-roundtrip.kicad_pcb` — byte-identical to canonical corrected PCB; `stackup-roundtrip.json` PASS |
| Future-generation reproduction | `initializer-replay/` and `initializer-command.json` — run fixed initializer on source-generated board; `stackup-initializer.json` PASS |
| Existing copper and placement preserved | `unchanged-electrical-geometry.json` — entire native export equal except identities and added raw board bytes |
| Native ERC/DRC | `native-check-1/`, `native-check-2/`, `native-check-3/` — zero ERC, DRC, unconnected, parity on unchanged corrected board |
| Rust workspace | `workspace-tests.log` — 116 tests PASS (8 stackup unit tests and 2 new current-sense integration tests) |
| Python transport | `python-tests.log` — 13 PASS |
| Rust lint/format | `clippy.log`, `fmt.log` — PASS |
| Pinned executable replay | `verification-commands.json`; `../acceptance-stackup-v2/` — actual argv, exit status, input, report and executable copies |

The authoritative normal report is `../acceptance-stackup-v2/report.json`: 12 rule families, zero hard findings, one stackup PASS, seven prior applicability findings; overall INDETERMINATE. No physical qualification gap is closed by this repair.

## Visual scope

`before.png` and `after.png` use the same KiCad 10.0.4 CLI renderer, 1000 × 800 pixels and rotation `325,0,25`. The fixed render shows separated copper surfaces and hole barrels at the corrected thickness. The CLI renderer did not reproduce the exact translucent brown box from the user's interactive viewer screenshot; that full display symptom is not claimed as a proven consequence of the zero core. No enclosure exists. The transformer still lacks an accurate body model, so this is not a full 3D assembly-interference qualification. Reload the saved canonical PCB in the interactive viewer to inspect its updated model.

## Scope review and historical evidence

Reviewed the scoped changes for source identity bypasses, parser ambiguity, rule registration, finite-number handling, regression fidelity and preservation of unrelated geometry. Quoted parentheses cannot spoof structural paths; trailing documents, unterminated strings and excessive nesting are rejected. Explicit two- and four-layer positive controls prevent a gate that merely rejects everything. Multi-sublayer dielectric syntax is not supported and is rejected, not approximated. No unresolved defect was found within this rule's stated scope. This was a local self-review, not an external multi-agent review.

Before editing, all 442 files bound by the old acceptance manifest were verified and copied with their original paths under `zapote/artifacts/current-sense-before-stackup-fix/`. The old manifest and checksum file are preserved there too. The old live `evidence/acceptance/` packet is historical; its referenced files have a new revision. `../acceptance-stackup-v2/manifest.json` is the current acceptance identity. Unrelated pre-existing work remains uncommitted and untouched; `pre-fix-status.txt` records it.
