# Current-sense digital milestone

The standalone current-sensing / primary overcurrent unit is built as a source-derived, placed and routed KiCad project. Digital construction is complete with explicit qualification gaps. Physical acceptance and purchasing readiness are not complete.

| Check | Result |
|---|---|
| Atopile 0.2.69 | Source-build-04 compiled and exported |
| Strict source/native generation | 21 components, 64 pin/net assignments; replay generated a byte-identical PCB |
| Final schematic oracle | Exact source connectivity; final schematic hash matches independent replay |
| KiCad 10.0.4 ERC | 0 violations in each of three final runs |
| KiCad DRC / unconnected / parity | 0 / 0 / 0 in each of three final runs |
| Rust current-sense validation | 12 rule families, 0 hard findings; overall INDETERMINATE with 7 applicability findings |
| Rust workspace tests | 116 passed, including 17 current-sense integration/defect controls; existing RTD and memory suites retained |
| Independent standalone model | 6 tests passed; replay output matches retained model output |
| Python transport tests | 13 passed: 5 current-sense controls plus 8 existing memory transport tests |
| Formatting and lint | Rust formatting check and strict workspace Clippy passed |
| Physical measurements | All NOT RUN |

The routed PCB, schematic, compiled source manifest, local libraries, model, validator source, executable and reports are bound in `evidence/git-checkpoint/manifest.json`. That manifest's file hashes are the authoritative identity; the dirty worktree's commit identifies context only. The source-generation manifest retains its original generated-board hash and is not presented as the final routed-board hash.

## Stackup correction — 2026-09-11

The original digital acceptance omitted physical stackup validation. The current revision corrects the zero-thickness FR4 core to 1.44 mm and adds the mandatory Rust `DRC.BOARD.STACKUP` gate. Copper (2 × 0.07 mm), core (1.44 mm), and masks (2 × 0.01 mm) total 1.60 mm. KiCad save/reload is byte-identical; complete extracted placement/routing/connectivity is unchanged. Three new native checks pass. The normal Rust path has zero hard findings and seven remaining applicability findings.

The original 442-file evidence set and its manifest are preserved with original relative paths under [`../artifacts/current-sense-before-stackup-fix/`](../artifacts/current-sense-before-stackup-fix/). Its old PASS claims apply only to the earlier coverage, which did not include this rule. See [repair evidence](evidence/stackup-fix/README.md) and the new manifest for the current authority.

## Delivered

- `candidate/section.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, project rules and local libraries.
- [Exact interfaces](INTERFACES.md), [BOM](bom/README.md), [validation scope and replay](VALIDATION.md), native schematic and board PDFs.
- Corrected transformer land pattern and floating-burden bias topology, with independent evidence and explicit application limits.
- Rust source/model/geometry checks and retained defect controls, plus reviewed versioned memory for later units.

Luna supplied bounded circuit/model, native-tool and Rust work. The coordinator authored the placement/routes, reviewed the outputs, repaired integration defects and ran the final checks. No placer or router search algorithm was added or used. The original full-cooker circuit was not silently replaced by this standalone design.

## Remaining before hardware acceptance

Qualify CT transfer and thermal behavior, hot clamp leakage, comparator hysteresis/offset applicability, startup/brownout, primary solder/busbar construction, assembled insulation and the complete shutdown timing chain. Validate the host monitor input against its load assumptions. Confirm or replace the exact comparator/clamp procurement choices through a new electrical review; checked preferred-distributor listings lacked stock. No hardware was assembled, purchased, energized or ordered for fabrication.

The next integration owner receives a usable independent unit and its exact evidence. These gaps must remain visible when the unit joins the cooker; a clean DRC or conditional trip calculation cannot close them.

Git checkpoint (2026-09-11): KiCad expanded the project defaults after the stackup freeze. The current PCB bytes and authored minimum rules are unchanged; new native checks cover the saved project. The complete original stackup-v2 evidence, including its old project and UI-state bytes, is preserved under `zapote/artifacts/current-sense-stackup-v2-frozen/`. Current manifest excludes mutable `.kicad_prl` UI state.
