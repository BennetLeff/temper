# Controller integration 06 execution record

Authority: `docs/plans/2026-09-19-power-stage-operating-envelope-plan.md`, immediate slice A3–A5 and B1/B2. User authorized continuation and Luna delegation. Local simulation only; no publication, board edits or hardware qualification.

Base: `5dde29ab3e2f1223c2d33c129ced2cf647238307`, canonical dirty checkout `/private/tmp/temper-pkgs-1-4`. New evidence lives here; experiments04/05 and their bound inputs are immutable. Host verified460 experiment04 and10 experiment05 hashes before implementation.

Native workers requested `gpt-5.6-luna`, high reasoning, fresh contexts and isolated no-checkout worktrees at the same HEAD:

- `integration06_limits`: `/private/tmp/temper-integration06-limits/output`; node limits and conditional current/energy calculator.
- `integration06_supply`: `/private/tmp/temper-integration06-supply/output`; concrete15V/5V producer interface, including upstream overvoltage.
- `integration06_controller`: `/private/tmp/temper-integration06-controller/output`; manufacturer controller model and coupled plant fixture.

Workers own only their output directory. Host owns integration, source/probe audit, independent reruns, residual findings and artifact receipt. Bound each research/download attempt; preserve rejected numerical attempts. No independent worker output constitutes milestone acceptance.

## Acceptance checks

1. Voltage nodes and threshold/absolute/assumed limits remain distinct; current envelope has a mathematical oracle and invalid-input failures.
2. Actual selected supply circuit has an explicit upstream envelope, load/dropout/thermal constraints, model limitations and overvoltage cases. A behavioral regulator is not vendor dynamic qualification.
3. Controller interface uses actual negative shunt sensing and source divider/compensation values. Fixed external PWM is removed from the integrated witness. Check relevant controller behavior independently; any omitted manufacturer behavior remains a blocker to claiming full B2.
4. Numerical traces must be finite, ordered and complete, with meaningful positive and negative controls. Retain raw sources and bind accepted model/source bytes.
5. Experiments04/05 remain byte-identical. Report A5/B1/B2 completion according to observed artifacts, not planned capabilities.

Additional Luna work: `integration06_model_review` audited controller behavior;
`integration06_supply_fix` replaced the dropout-prone first supply, then compiled
and exported the corrected candidate; `integration06_clamp` traced the ISENSE
polarity/placement correction to TI and Vishay references. These were bounded
subtasks of this session. Host corrected the controller model, hardened trace
validators, reran acceptance checks and retained the remaining qualification gaps.
