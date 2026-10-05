# Staged first-build and evidence packet

**Preparation only; all hardware work NOT_RUN.** This sequence is for a qualified engineering lab after the listed stage-specific blockers are resolved. A temperature mentioned in a study is not an apparatus operating limit.

## Stage 0 — settle the process and requirement inputs

Manufacturing owns exact sensor and adhesive instructions, part/lot identity and the supplier questions in [bond-leads.md](bond-leads.md). Mechanical/electrical owners define loads, duty, cleaning, leak and shutdown criteria. The metrology owner supplies actual instrument drawings, capability and the complete fixture uncertainty budget. Do not replace an unresolved input with an unrecorded assumption.

Required records:

- Exact sensor ordering code and incoming geometry; film/bond face and lead reference datum evidence.
- Exact adhesive base/activator, received instructions, compatibility disposition, minimum bond gap and permitted cure. Resolve the generic Cotronics guidance before selecting the process.
- Native lead support/form/trim/join sequence and installed resistance datum; distinguish nominal target from a specified tolerance.
- Cap stock condition, forming/welding process, intended finish, hook/ceramic bearing geometry and manufacturing variation.
- Full seal boundary and load-path diagram, including every feedthrough, common/local travel, positive retention and pressure reference/drainage route.
- Requirement authority: which numbers are product requirements, development allocations, characterization points, or simply unknown.

**Exit:** each planned specimen has a coherent process and a reviewed operating envelope. The current CAD alone does not provide this exit evidence.

## Stage 1 — commission the dry fixture and process witnesses

Two independent activities can proceed once their own inputs are resolved:

**Dry fixture commissioning.** Use a dimensionally representative dummy for mounting, alignment and metrology work. Complete the clamp fasteners, guide, instrument supports and optical line of sight. Demonstrate that tightening does not change the moving-guide force curve. Verify pan/cap/carrier/island motion independently. Use the R7 Ø6 puck for cap-only force sweeps; the Ø36 accessory loads the glass and is a separate pan-support experiment. Select a force/displacement range that covers the approved envelope and verify uncertainty in the installed fixture.

**Bond/process witnesses.** Prepare the material/process falsification specimens defined in [bond-leads.md](bond-leads.md), including a manufacturer-directed reference thickness. A single section can reveal a blocked process; it cannot establish repeatability. Keep untouched sensor witnesses and log electrical change after each manufacturing operation. An alumina witness tests some process behavior but does not establish compatibility with the sensor's passivation/fixation glass; that requires the exact element or a representative supplier-approved witness.

**Exit:** measured process geometry and stable electrical behavior support assembling the selected coupon; metrology can resolve the quantities being judged. A failed or inconclusive witness prevents progressing that process recipe.

## Stage 2 — assemble and characterize the dry thermal coupons

Keep the M222/0.100 model as the numerical control. It becomes a fabrication control only after its thin-bond process is resolved. Compare M222/0.075 with matched sensor lot, cap, cover and join process; add IST308/0.075 after its orientation and near-element lead questions are resolved. If the qualified process requires different geometry or materials, assign a new configuration and rebuild/re-export/rerun before comparison. Do not reuse the R7 labels for changed articles.

Start with one accepted control article to commission acquisition. The existing R7 planning matrix then proposes three separately assembled articles per configuration, two fit-family pans and two different holdout pans per article, and three independent placements per pan. This is exploratory coverage, not lifetime or process-capability evidence. Stage expansion depends on the first process and fixture results.

Use the existing [R7 acquisition matrix](../revision7/calibration/TEST_MATRIX.md), [blank campaign ledger](../revision7/calibration/templates/campaign.csv) and [calibration adapter](../revision7/calibration/README.md). Proposed 50/100/150/200/250°C characterization points apply only within the separately reviewed complete assembly/fixture envelope. Log actual local pan temperature, RTD, cap/reference attachment, glass, anchor/body, force, independent positions and contact ground truth on a common clock.

Run three separable characterizations:

1. Change verified force/contact conditions at comparable pan and boundary temperatures.
2. Change body/anchor temperature with pan temperature held, to measure leakage sensitivity.
3. Measure steady error, pan-step t90, own-final t90 and finite-ramp error using a reference with a demonstrated bandwidth and uncertainty budget.

Report raw performance before fitted correction. Freeze fit parameters and build/input identities before whole-pan holdout evaluation. Keep differences between placements and builds visible. The proposed <2°C and <2 s screens are development objectives under declared conditions; one successful local reference point does not establish whole-pan uniformity or all-cookware control.

**Exit:** measured heat-path and contact envelopes explain the response with acceptable independent residuals, or identify a specific redesign. Failing the target is useful characterization; it is not a passing product gate. Keep the seal and production-contact gates separate from this unsealed dry thermal experiment.

## Stage 3 — qualify the seal concept and contact observable separately

Use the R7 separate pressure cell only for an approved membrane specimen and rated apparatus. Measure signed force/pressure loops and effective area through stroke and temperature; characterize reversal, restriction, reassembly and defined ageing. A cell result does not qualify an absent cartridge gland/feedthrough/drainage boundary. Check the complete single-boundary or two-boundary budget, including elastic force, pressure, hysteresis and harness/witness loads without allocating the same margin twice.

For contact, inject real independent separation and force-path faults while heat command remains inhibited. Include main-carrier jam, local-island jam, compliant obstruction, witness faults, plausible warm RTD, insulating load-bearing debris and conductive bridge. A fresh timestamp, electrical continuity or successful mechanical challenge is not sufficient on its own. Map every required fault to independent ground truth and a measured end-to-end output-disable trace; unresolved observationally equivalent cases remain open.

**Exit:** a specific physical observable and a complete seal architecture satisfy their declared requirements across the tested envelope. The existing host interlock tests validate software behavior only. No production backend is enabled by R8.

## Stage 4 — integrate, then test under induction and after stress

Integrate only after the selected geometry, material, process and load paths have evidence supporting their use. Repeat mechanical/contact and thermal checks on the sealed assembly, because the seal and harness can change force and heat loss. Use the load applications and evidence distinctions in [retention-induction.md](retention-induction.md).

Before induction-on work, the qualified lab must approve the actual rig, electrical isolation, independent cutoff, references, maximum energy/temperature and exposure limits. Use the existing [induction acquisition package](../induction_validation/README.md); do not create a second importer. Dummy RTD, field-off matched thermal conditions and independent cap/pan references separate pickup from physical heating. Account for reference-probe perturbation and keep both spatial pan hotspot and sensor-local error results.

Predeclare cleaning/thermal-cycle/wear conditions and count, specimens/lot/reassembly sequence and stop criteria. Recheck leakage, retention/permanent set, force/contact inhibition, electrical isolation and thermal calibration after stress. A successful survival count is only evidence for that declared exposure, not an unspecified lifetime.

**Exit:** the complete tested configuration has a reviewed qualification record. Production acceptance, certification and release remain separate decisions.

## Common evidence record

Use existing physical templates rather than synthetic result files. Archive:

- Specimen and configuration IDs; exact CAD/BOM/source hashes; RTD/cap/adhesive/wire lots; process and cure revisions; measured installed geometry.
- Requirement ID, authority/approver and frozen acceptance or characterization rule; instrument identities, calibration and in-situ uncertainty.
- Raw synchronized traces and event timing; reference placement and attachment; actual environmental and imposed-fault state, photographed where useful.
- Every failed, inconclusive and invalid run with its disposition. A fixture/gripper/reference failure is not a DUT pass.
- Pre/post stress comparisons and the explicit retest scope whenever a material, bond, route, seal, retention feature, readout or algorithm changes.

A missing requirement is recorded as **UNDEFINED**, an unexecuted measurement as **NOT_RUN**, and a result whose uncertainty overlaps the limit as **INDETERMINATE**. Neither a simulator exit code nor a complete metadata form supplies physical evidence.
