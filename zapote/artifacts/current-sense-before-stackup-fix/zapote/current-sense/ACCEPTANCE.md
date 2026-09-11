# Current-sense digital milestone

The standalone current-sensing / primary overcurrent unit is built as a source-derived, placed and routed KiCad project. Digital construction is complete with explicit qualification gaps. Physical acceptance and purchasing readiness are not complete.

| Check | Result |
|---|---|
| Atopile 0.2.69 | Source-build-04 compiled and exported |
| Strict source/native generation | 21 components, 64 pin/net assignments; replay generated a byte-identical PCB |
| Final schematic oracle | Exact source connectivity; final schematic hash matches independent replay |
| KiCad 10.0.4 ERC | 0 violations in each of three final runs |
| KiCad DRC / unconnected / parity | 0 / 0 / 0 in each of three final runs |
| Rust current-sense validation | 11 rule families, 0 hard findings; overall INDETERMINATE with 7 applicability findings |
| Rust workspace tests | 106 passed, including 15 current-sense integration/defect controls; existing RTD and memory suites retained |
| Independent standalone model | 6 tests passed; replay output matches retained model output |
| Python transport tests | 13 passed: 5 current-sense controls plus 8 existing memory transport tests |
| Formatting and lint | Rust formatting check and strict workspace Clippy passed |
| Physical measurements | All NOT RUN |

The routed PCB, schematic, compiled source manifest, local libraries, model, validator source, executable and reports are bound in `evidence/acceptance/manifest.json`. That manifest's file hashes are the authoritative identity; the dirty worktree's commit identifies context only. The source-generation manifest retains its original generated-board hash and is not presented as the final routed-board hash.

## Delivered

- `candidate/section.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, project rules and local libraries.
- [Exact interfaces](INTERFACES.md), [BOM](bom/README.md), [validation scope and replay](VALIDATION.md), native schematic and board PDFs.
- Corrected transformer land pattern and floating-burden bias topology, with independent evidence and explicit application limits.
- Rust source/model/geometry checks and retained defect controls, plus reviewed versioned memory for later units.

Luna supplied bounded circuit/model, native-tool and Rust work. The coordinator authored the placement/routes, reviewed the outputs, repaired integration defects and ran the final checks. No placer or router search algorithm was added or used. The original full-cooker circuit was not silently replaced by this standalone design.

## Remaining before hardware acceptance

Qualify CT transfer and thermal behavior, hot clamp leakage, comparator hysteresis/offset applicability, startup/brownout, primary solder/busbar construction, assembled insulation and the complete shutdown timing chain. Validate the host monitor input against its load assumptions. Confirm or replace the exact comparator/clamp procurement choices through a new electrical review; checked preferred-distributor listings lacked stock. No hardware was assembled, purchased, energized or ordered for fabrication.

The next integration owner receives a usable independent unit and its exact evidence. These gaps must remain visible when the unit joins the cooker; a clean DRC or conditional trip calculation cannot close them.
