# R5 integration plan — approved scope

The user approved the R5 prototype-development plan, all R4 open-gap rows, Astra parallel work, and CAD updates matching the modeled geometry. Scope remains simulation and test preparation; physical testing is NOT_RUN.

1. Compare 8 mm and package-feasible smaller sensing head, preserving realistic contact-area/force tradeoffs. Geometry owner exports actual mass, interfaces, lead routing and motion states.
2. Select a prototype pressure/liquid-boundary and contact-diagnostic concept from quantified alternatives. Do not equate a material rating or motion reading with qualification.
3. Complete cap-moving joins/covers/lead routes, retention and build/inspection evidence. Candidate geometry and thermal model consume one scalar contract.
4. Address every R4 gate with a simulation result, an explicit design decision, or a prepared physical acceptance test. Preserve evidence origin and unresolved use requirements.
5. Integrate source/CAD/result hashes; rerun model groups against final CAD, verify links and geometry parity, publish a local versioned current-CAD index and report. Preserve R1–R4 as historical evidence.

Files are developed under `/private/tmp/temper-r5/{mechanical,thermal,safety,validation}` then integrated into the existing isolated worktree under `packages/temper-thermal/studies/glass_sensor/revision5/`. No unrelated primary-checkout edits, push, external publication or hardware enablement.

Current decisions: 6 mm smaller face is packaging candidate; 4 mm rejected by RTD/bond/join envelopes. Seal and detector are feasibility decisions until supplier/physical evidence exists. Old under-glass requirements are not silently transferred to this through-glass candidate.
