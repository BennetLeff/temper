# R7 experimental coupons and measurement preparation

The user asked to continue in parallel after R6. Scope is simulation and test preparation; no hardware acquisition, operation, supplier outreach or production enablement.

## Required outcomes

1. Build complete D6 M222/0.10 control, M222/0.075 and IST308/0.075 experimental coupon CAD. Include bond, actual installed native leads, joins, covers, retention, anchor and full extension wires. Explicitly distinguish manufacturer dimensions, design choices and unresolved film/terminal details. Check defined motion poses and STEP validity.
2. Consume exported CAD volumes/areas/lengths in the pinned thermal network. Preserve the control, report capacity accounting, sensitivity and convergence, and never reuse an optimistic R6 score as a completed-CAD result.
3. Prepare an independent contact-force/displacement fixture and a separate pressure-cell fixture. Show mounting/reference datums, load paths, pressure connectivity and uncertainty. Do not claim the pressure fixture supplies a seal for the cartridge.
4. Reuse the existing bench calibration evaluator with stricter independent-pan/configuration checks and the proposed <2°C/<2 s guarded screen. Demonstrate rejection of empty data, leakage between fit/holdout, weak contact and hidden dynamics. Keep all physical evidence NOT_RUN.
5. Integrate a readable report, current experimental CAD index, complete source identities, executed checks and independent review. Preserve historical R5/R6 artifacts; archive the previous mutable index bytes when advancing the index.

## Decisions already settled

- R5 D6 contact cap and mechanics remain the reference architecture. These are experimental coupons, not a released cartridge.
- Installed native lead trim is a documented prototype process, not supplier-approved trimming or a validated Kelvin resistance datum. Film side, attachment and joins remain qualification inputs.
- Nominal CAD fit does not establish strength, leakage, hot friction, sensor response or control safety.
- Model fitting predicts a measured sensor from measured pan input; it is not blind pan-temperature estimation or a contact detector.
- Rust owns analysis; Python is limited to CadQuery geometry glue, presentation and artifact bookkeeping. Standalone tools avoid shared Cargo and installed-extension changes.

Completion means the geometry-to-model comparison and test package are executable and inspectable, with remaining evidence named explicitly.
