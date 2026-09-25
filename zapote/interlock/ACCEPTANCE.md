# Interlock Rev A construction acceptance

Accepted for the separate-unit digital construction milestone, 2026-09-12 UTC.
Full qualification remains **INDETERMINATE**; powered tests are **NOT RUN**.

| Evidence | Result |
| --- | --- |
| Atopile 0.2.69, source-build-02 | Compiled; authored interlock source matches captured input |
| Native board | 100 × 65 mm, two copper layers, 1.6 mm total stackup; 25 components |
| Source/schematic oracle | 110 physical pin assignments; 28 connected nets agree |
| Complete Rust topology | 32 nets including four intentional singleton NC nets |
| KiCad 10.0.4 final-native-02/03/04 | Each: ERC 0, DRC 0, unconnected 0, schematic-parity 0 |
| Rust interlock report | 75 PASS, 0 FAIL, 5 INDETERMINATE; CLI exit 1 as required |
| Actual compiled graph | 4,096 state/input/clock vectors match independent requirement oracle |
| Zapote workspace | 176 tests passed, including 18 interlock mutation/state tests; all five registered saved-board checks passed |
| Static checks | Cargo fmt and Clippy with warnings denied; new native adapters pass Ruff |
| Render inspection | Schematic package pin names, connector legends, component labels and exposed board reviewed |

Local coordinator and Luna review found no remaining actionable construction
defect. No independent cross-model corroboration was obtained; see
`evidence/code-review-closeout.json` for the exact review coverage and limitation.
Captured tool output and copied source inputs retain their original whitespace
and CSV line endings. Authored source passes the Git whitespace check.

The canonical PCB is `candidate/section.kicad_pcb`. `evidence/native-final.json`
contains its native extraction and embedded saved bytes. `freeze-manifest.json`
binds construction inputs and evidence by full SHA-256. Historical source/native
skeleton manifests describe their own generation stage, not the final stackup.

The schematic oracle excludes singleton NC nets from partition comparison; the
Rust validator independently requires their exact physical pads and singleton
native clusters. Neither a zero-unconnected count nor schematic parity alone
proves the circuit's intended behavior.

## Rejected evidence retained

Routes 04–07 show construction failures and their correction. `final-native-01`
has 25 off-grid ERC warnings and is **rejected**. The misleading zero came from
reading a nonexistent root-level `violations` field: KiCad ERC findings are in
`sheets[].violations`. The schematic was placed on its native grid and rerun;
no warnings were suppressed. `final-native-summary.json` explicitly records
the correct field and the three accepted runs.

## Remaining qualification

- SENSOR_LIVE and AUX producers, remote unpowered-output injection, and the
  downstream actively driven PERMIT receiver are integration obligations.
- Actual watchdog timing, power ramps, propagation, and clock/clear
  recovery/removal are not established by Boolean simulation.
- HC30 input-threshold applicability at the actual 3.3 V rail, harness
  transients and component failures remain unresolved qualification items.
- The selected fabricator must support the declared 0.15 mm clearance and
  assembly requirements. No stock, purchasing or fabrication claim is made.
- No physical fault test, powered board, heater or whole-cooker result exists.

The next separate unit is isolated gate drive. It must consume this interface
contract explicitly; it must not assume that an undriven signal or a cleared
fault grants permission.
