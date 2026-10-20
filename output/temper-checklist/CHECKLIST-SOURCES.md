# Sources for CHECKLIST.md (2026-10-19)

Everything here was read-only. Path prefixes are as defined in CHECKLIST.md.

## Read directly by the author

- **Coil:** COIL/README.md, ORDER-LIST.md, HOT-LIMITS.md and BUILD-AND-MEASURE.md (all in full); cad/jig.py (header); cad/out/checks.json; .gitignore; `git ls-files` of cad/out and model/fem3d/results; `git log` of the folder.
- **Coil spec:** SPEC (PSI committed copy, rows 1–16 sampled, line 59, line 239); MAIN/docs/hardware/TANK_COIL_SPECIFICATION.md (sha256 compared).
- **Power stage:**
  - PS/DECISIONS.md: lines 50-62, 236-250, 1363-1368;
  - PS/PROTOTYPE-POWER-LOOP.md: 70-90;
  - PS/ASSEMBLY.md: 12-13, 39, 45 (grep);
  - PS/OPEN-ITEMS.md: 56 (grep).
- **Enclosure:** R43/design/r12/DECISIONS.md:10-25; R43/BOM.csv:72-73 (grep).
- **Sensor:** SR3/box/field_sweep.py:1-30.
- **Controller:**
  - CJ/evidence/fab-loose-ends/cpl-rotation/PREVIEW-2026-10-19.md:20-36;
  - CJ/DECISIONS.md: C3 lines 17-24, 145, 186-188 (grep).
- **UI board:** UIB/DECISIONS.md U1, U15, U19, U27-U32; UIB/README.md:1-30.
- **Firmware:**
  - FW/components/sensors/include/max31865.h (grep);
  - FW/components/power/include/tank_freq.h:103-106;
  - FW/config.yaml (grep for the threshold words).
- **Docs:** PSI/docs/research/mit-product-design/readiness/manufacturing/material-selection.md:26.
- **Tracking state:** `git status`, `git ls-files` and `git check-ignore` in MAIN and PSI for SR3, coil-review-2026-10-10 and temper-coil-driver-r1.

## Read by the five research passes (their citations are used in the rows)

### Power board
PS/README.md, DECISIONS.md, OPEN-ITEMS.md, ASSEMBLY.md, FAB-JLCPCB.md, DC-LINK-CLAMP.md, PROTOTYPE-POWER-LOOP.md, FAULT-INTERFACE.md and D5-BASIS.md, plus:
- **Package and fab:** NAT/README.md, PROTOTYPE-LOT.md, BRING-UP.md, fab/FAB-NOTE.md, fab/bom-jlcpcb.csv, fab/hand-assembly-extras.csv, INDEPENDENT-REVIEW-2026-10-18.md and review-packet-s53/README.md.
- **Owner items:** OI/CERTIFIER-PACKET.md, CERTIFIER-CHECKLIST.md, JLC-LAMINATE-QUESTION.md, m11/* and order/*.
- **Sourcing:** NAT/sourcing/README.md, study-2026-10-15/README.md and inquiries/*.
- **Candidates:** CAND/bench-sink-r1, bench-h-2026-10-16, c23-supply-topology, c53-astra-results, c53-stuck-on, c54-* and consign-r1.
- **Validation and verification:**
  - PS/validation-plan/00-MASTER-PLAN.md, bench-verdict.md and enclosure-fit/plan-result.json;
  - validation-results/01, 02, 07 and 10-benchmark scorecard;
  - native-21/verification/datasheet-ledger (README, ledger.json, ledger-report.json);
  - native-21/frozen.
- **Other:** PS/owner-outbox/2026-10-12.md; PSI/output/temper-aux-load-r1, temper-prototype-closure, temper-manufacture-readiness and temper-flush-front-r4.

### Controller and UI
- **Controller:** CJ/DECISIONS.md (C1–C50), ORDER.md, README.md, LAYOUT.md, ENCLOSURE-HANDOFF.md, fab/*, bom/controller-parts.json, evidence/verify.json, evidence/convergence-c49.json, evidence/order/stock-read-2026-10-18.json and evidence/fab-loose-ends/*.
- **UI board:** UIB/README.md, DECISIONS.md and bom/ui-parts.csv.

### Firmware
FW/README.md, config.yaml, transition_table.yaml, partitions.csv, plus:
- **Main:** main/state_machine.[ch], main/platform/*.
- **Components:** components/power/Kconfig, COMMISSIONING.md and include/tank_freq.h; components/sensors/*; components/control/thermal_mgmt.h; components/safety/*.
- **Build and test evidence:** build-evidence/*, test/CMakeLists.txt, tools/*.
- **Configuration and CI:** state-machine-crosscheck-allowlist.yaml; .github/workflows/firmware-tests.yml and release-artifacts.yml.
- **Other trees:** ctrl-j13/firmware (stale copy); origin/main firmware (via `git show`).

### Sensor
SR3/README.md, DECISIONS.md, HANDOFF.md, PATENTS.md, plus:
- **CAD:** cad/DECISIONS.md, cad/QUOTE-LIST.md, cad/checks.json, cad/field-screen.json, cad/thermal-axisym.json, cad/DRAWINGS.md.
- **PCB:** pcb/DECISIONS.md, pcb/REQUIREMENTS.md, pcb/CHANGE-REQUEST.md.
- **Bench:** bench/README.md, bench/DECISIONS.md, bench/PROCEDURE.md, bench/RIG.md, bench/bom.json.
- **origin/main only:** firmware/DECISIONS.md, leak-barrier/* and robustness/*.
- **Other:** R43/design/r16/BENCH-TEST-PLAN.md.

### Enclosure and compliance
- **R43:** CURRENT.json, README.md, BOM.csv, quote-package/QUOTE-REQUEST.md, design/r43/HANDOFF.md, design/r43/DECISIONS.md, design/r32/{DECISIONS, BENCH-PLAN, CERTIFICATION-QUESTIONS}.md and design/r14/parts-research.md.
- **Owned controls and airflow:** OC/STATUS.md, DECISIONS.md, SPEC.md and DELEGATION.md; AF1/README.md.
- **PSI docs:** REGULATORY_COMPLIANCE.md, ENVIRONMENTAL_SPEC.md, and research/mit-product-design/readiness/mechanical/packaging.md.

## Not used
- Web search: none (no web-sourced figure in CHECKLIST.md beyond what repo files already quote with their own sources).
- Browser, vendor accounts, email: none.
