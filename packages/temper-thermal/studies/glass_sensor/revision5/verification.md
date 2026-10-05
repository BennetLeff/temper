# R5 executed verification

Date: 2026-10-04. Scope: simulation, nominal CAD and test preparation only. Physical tests: **NOT_RUN**.

## Executed checks

| Check | Result | Scope |
| :-- | :-- | :-- |
| Thermal Rust suite | 25 passed | 14 inherited kernel tests plus 11 R5 tests |
| Pressure/detector Rust suite | 9 passed | Analytical and transient screens, explicit detector counterexamples |
| Validation Rust suite | 11 passed | Conservative budgets, CAD roof/pickup checks and invalid-evidence rejection |
| Compiler/style | Passed | rustfmt, rustc warnings denied, direct clippy-driver warnings denied; Python Ruff lint/format |
| Nominal cartridge geometry | 12 poses passed | D8/D6 × rest, loaded, local stop, full stroke, upper capture, cap capture |
| STEP exports | 15 files | 12 pose assemblies, 2 caps and 1 separate unconnected pressure apparatus |
| Rigid interference | Zero above 1e-5 mm³ | Defined rigid census; seal envelopes/witnesses excluded from that census |
| Full-wire checks | Zero interference above 1e-6 mm³ | Wire/rigid and wire/wire across all poses; 48 developed-length/volume checks |
| Separate witness clearance | Zero intersections above 1e-6 mm³ | Four wires against both rods and both flags in all 12 integrated CAD poses |
| Weld topology | Four intended joins passed | Finite intersection with Cu and correct Ni terminal; none with opposite terminal; process envelopes only |
| Exported cap parity | Passed | Independently reimported STEP volume and top-face area match scalar model input within relative 1e-8 |
| Runner failure injection | Passed | Thermal and safety test executables forced to exit 7; both runners exited 7 without physics CSVs or receipts |
| Evidence gate | Passed | Four exact thermal receipt paths and hashes verified; blank physical acquisition template rejected |

Total: **45 passing Rust test executions**. A passing analytical regression suite does not calibrate contact coefficients or establish physical performance.

The final installed thermal and safety runners were executed successfully. The validation runner was then executed against their final receipt and results. Eight thermal CSVs contain 784 rows. Validation consumes 36 current comparison cases, all of which fail the joint proposed whole-system bound below 2°C and t90-pan below 2 s. All nine gap records retain physical_result=NOT_RUN.

The independent review found an omitted axial resistance for the 1 mm anchored copper segment. Each adjacent link now includes half that segment, and the assembled full-wire network matches an independent total-length resistance calculation. A mutation restoring the omission fails the new test. The same review found test-output pipelines could mask a failed test; sequential log capture now preserves failure, independently checked with exit-7 injection.

Cap STEP parity:

- D8: area 50.265482457436676 mm²; volume 9.105822368620078 mm³.
- D6: area 28.274333882308138 mm²; volume 6.250400082347788 mm³.

Geometry contract SHA-256: `420fdbe70bef0dbaf73cb7b03821721cec9e9065e2e85f774eff2d2a9d0219e3`.
Thermal source SHA-256: `8141e9b402ae9c3e4c291a802d3a5915c3890c100590f029dd035e1d6ee49a49`.
Comparison CSV SHA-256: `9207152def0c378de1f5b503d3d7ff89eb73d93f0419ea5ec8e0e4962cc65e9a`.

## Review limits

The STEP-derived CAD image and generated thermal comparison PNG were visually inspected. The HTML's local links and embedded file references were checked; the HTML was not browser-rendered in this verification. Section SVGs parse as XML. Provenance checks cover historical R3/R4 records and all new issued files; earlier study revisions remain unchanged.

The rigid screen excludes unqualified seal envelopes and does not solve elastic deformation, manufacturing variation or hot clearances. The witness check is geometric; optical line of sight, rod deflection and thermal growth remain unresolved. The pressure apparatus is separate and unconnected. Hot gas volume and effective diaphragm area are assumptions, not measured CAD assembly properties.

No cartridge was built. No material/part availability, vendor acceptance, forming, weld, bond cure, insulation, seal, force, fatigue, induction, leakage, cleaning, temperature accuracy or control-inhibition hardware test was performed. Production firmware remains unchanged.

Packaging correction: the CAD scalar CSV used CRLF record separators. These were normalized to LF, with parsed fields verified identical, and the generator now emits LF explicitly. The prior byte hash was `40b2d36f739fadb419956d744d209cf3268d9370a8ab8dbfc39568048738f37e`; the new hash is `420fdbe70bef0dbaf73cb7b03821721cec9e9065e2e85f774eff2d2a9d0219e3`. Thermal and validation runners were rerun against the new pin; numerical comparison output remained byte-identical.
