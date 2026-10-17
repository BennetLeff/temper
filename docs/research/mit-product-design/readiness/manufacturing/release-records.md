# Build records and production handoff

These are blank templates; no measured result or approval is implied. Keep records next to raw files under one physical build serial. Fill every required field, or mark HOLD with owner and next action. A spreadsheet is optional; the evidence relationships are required.

## Build identity

| Field | Value to complete |
| --- | --- |
| Build serial / stage / date / responsible builder | NOT_ASSIGNED |
| Repository commit and dirty-state/diff identity | NOT_RECORDED |
| Electrical source / native PCB / netlist / BOM / CPL / fab package hashes | NOT_RECORDED; must be mutually reconciled |
| Enclosure/assembly STEP and drawing revisions/hashes | NOT_RECORDED; historical PCB import excluded from current-board fit proof |
| Firmware binary + configuration + calibration identities | NOT_RECORDED |
| PCBA serial/lot, critical MPNs/lots, coil/pans, sink/fan/insulator, harness | NOT_RECORDED |
| Enclosure/glass/finish, adhesive/primer/seal batch/cure, membrane, switches | NOT_RECORDED |
| Deviations/rework and restricted-use marking | NOT_RECORDED |
| Test-plan revision; permitted operating conditions; qualification sample allocation | NOT_APPROVED |
| Gate decision; electrical/mechanical/test/quality/compliance signoffs | HOLD |

## One record per measured characteristic/test

`record_id | CTQ_id | sample_serial/revision/lot | requirement_source/version | acceptance_rule/limit/units | procedure/fixture_version | conditions/stimulus | instrument_serial/calibration/zero_check | raw_data_path/hash | measured_value/units | uncertainty | result(PASS/FAIL/NOT_RUN/HOLD) | operator/date | reviewer | deviation_or_retest`

Write the rule before observing the result. Include screenshots only as supporting evidence; retain numeric/raw instrument files, acquisition settings, probe identity/attenuation, timing alignment and environmental conditions for electrical/thermal claims. Failed or damaged samples keep their original serial and history.

## One record per defect/change

`issue_id | build_serial | observed_failure/raw_evidence | immediate_containment | root_cause_evidence | disposition(rework/scrap/use-restricted) | authorized_by | design_or_process_revision | affected_CTQs | retests_required | retest_evidence | closed_by/date`

Examples of invalidation: new coil/bank or current threshold requires power/protection/thermal review; new copper or EMI/harness route requires electrical/EMC/insulation review; new sink/pad/clamp requires fit/thermal/bond review; changed finish/adhesive/cure requires bond/seal/cleaner aging; firmware affecting power/faults requires safety-function retest. A cosmetic-only change may have a smaller scope, but record the reasoning.

## G2/G3 manufacturing pack checklist

Before pilot, archive one accepted package containing the matched engineering drawings/BOM/fab/assembly/programming files, approved vendors and substitutes, material/critical-component records, shop exceptions, fixture drawings/calibration, assembly traveler with torque/cure settings, CTQ/control plan and validated EOL procedure. Define serial/lot trace, nonconforming-material handling and authorized rework.

Before production, add completed qualification reports with configuration identities and outstanding-issue disposition; selected-market conformity/certification records and factory follow-up requirements where applicable; actual pilot distributions/defects/yield/rework and corrective action; approved packaging/transport validation; final rating/traceability labels, English/Spanish user/service information as required by chosen markets; change-control and field-return traceability owner. A manufacturing release authorizes only the named revision, suppliers, materials, process and markets. No checklist signature can replace missing test results.

## Source and market scope check

Reviewed primary public pages on 2026-10-04. The proposed workflow is an engineering application, not a claim that MIT prescribes appliance limits. The [manufacturing skill evidence](../../../../../skills/temper-manufacturing-review/references/evidence.md) supplies assembly-sequence, variation and measurable-quality methods. Actual design inputs are [resolution](../../resolution/README.md), [supplier brief](../../resolution/integration/supplier-inspection.md), [thermal allocations](../../resolution/integration/thermal-budget.md), [market basis](../../resolution/integration/market-safety.md), and R4 `make-buy-review.csv`; their open conditions remain open.

| Primary source | Verified fact and scope limit |
| --- | --- |
| [Mexico Ministry of Economy NOM-003-SCFI-2014 record](https://platiica.economia.gob.mx/normalizacion/nom-003-scfi-2014/) | Listed vigente; last systematic review14August2025 reports confirmation. This supports keeping NOM-003 in the market review. It does not decide the exact product standard, conformity procedure, labeling or Temper construction limits. Have the Mexican conformity body confirm those before market release |
| [Official NOM text](https://dof.gob.mx/normasOficiales/5700/seeco2a11_C/seeco2a11_C.html) | Covers safety of electrical products imported or commercialized in Mexico, with product-specific referenced standards. Read applicable full requirements through the qualified reviewer rather than borrowing numeric limits from another product |
| [UL1026 scope, edition6](https://www.shopulstandards.com/ProductDetail.aspx?UniqueKey=23847) | Official page lists household cooking/food-serving appliances <=250V with exclusions and a June9,2026 revision. Candidate scope only; portable/installed and consumer/professional decisions remain unresolved. Ask certification body to identify applicable standard/edition instead of declaring UL1026 already selected |
| [Official CFR Part18 compilation](https://www.govinfo.gov/link/cfr/47/18?link-type=pdf&year=mostrecent) | Includes induction-cooking emissions provisions. Add explicit US FCC/EMC classification and authorization review alongside appliance safety. Accessed compilation is2024; verify current rules and exact product/radio configuration with lab before release. No current numeric emissions limit is adopted by this packet |
| [CDE942 catalog](https://www.cde.com/resources/catalogs/942C.pdf) | Exact component family reference for application request; catalog alone does not qualify the proposed high-frequency current/temperature/waveform envelope |

Direct current eCFR pages for18.203/18.307 were not accessible in this research session. Do not treat the older compilation as a 2026 legal-route confirmation. The current plan therefore requests written lab classification/edition/authorization confirmation rather than claiming compliance.
