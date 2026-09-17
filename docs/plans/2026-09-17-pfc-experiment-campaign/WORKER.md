# Worker packet: one bounded PFC experiment
Created: 2026-09-17

Read this entire file before acting. You are one worker in a larger campaign.
Your job is to return reproducible evidence for one question. You do not choose
the winning design, change acceptance rules, or complete neighboring tasks.

## Coordinator must supply these before dispatch

```text
campaign_id:
task_id:                    # exactly one registry ID
attempt_id:                 # new ID, even after a failed attempt
absolute_deadline_utc:
max_solver_invocations:      # <=48 for ordinary numerical workers
max_candidate_parts:         # <=3 unless task explicitly narrower
max_primary_sources:         # <=8 for ordinary research workers
checkout_path:
source_revision:
model_revision_and_sha256:
checker_revision_and_sha256:
contract_path_and_sha256:
registry_record_and_sha256:
control_inputs_and_sha256:
expected_cases_path_and_sha256:
allowed_output_directory:
exact_build_or_run_commands: # coordinator-issued, real commands; no guesses
source_bundle_paths_and_hashes:
applicable_memory_notes_and_hashes:
required_dependencies_and_accepted_receipts:
```

Source-only tasks mark model/expected cases/solver fields `not_applicable` with
reason. They still need the shared comparison contract, base revision and budget.
An empty field is not permission to choose it yourself. Ask the coordinator for
missing fields and perform only independent source reads until supplied.

The coordinator delivers this file, the task record, the frozen comparison
contract and relevant notes as actual input. A bare link or selected-memory
record does not establish delivery.

## Step 1 — Validate your workspace and task

1. Run `pwd`, `git rev-parse HEAD`, `git status --short`, and read repository
   `AGENTS.md` and `zapote/AGENTS.md`. Record outputs. If the revision differs,
   or another worker owns the directory, stop and return BLOCKED_INPUT.
2. Confirm you have exactly one task ID and its accepted dependencies. You are
   not alone in the repository: never revert another person's files. Do not
   edit outside your assigned directory. No stash, no force push, no procurement.
3. Hash the delivered inputs with SHA-256 and compare full digests. A prefix is
   not identity. If any mismatch occurs, report INVALID_INPUT and stop numerical
   work. Do not update expected hashes yourself.
4. Verify output directory is unused for this attempt. Preserve any existing data
   and request a new attempt ID. Never overwrite a failed run with a successful one.
5. Write a checkpoint containing the task question, changed design variable,
   frozen controls, source/model identities and which outputs remain unknown.

## Step 2 — Read the evidence, not just its labels

Read the prior comparison at
`zapote/power-entry/loss-budget/options/architecture-comparison/RESULTS.md` and
`zapote/power-entry/loss-budget/SWITCHING-REVIEW-LESSONS.md`.
Read your task-specific source bundle. For every numeric source input record:
exact MPN suffix/package, manufacturer, document revision, PDF hash, page/figure,
units, temperature, gate bias, voltage/current and whether typical or guaranteed.

If a source URL fails, retain the failure and try at most one other primary or
manufacturer-authored mirror. Never hash HTML and call it a datasheet. Distributor
stock/price is a timestamped procurement observation, not device performance.

Do not infer:

- actual driver output impedance from its peak-current headline;
- current-transfer charge from total Qg minus Qgd;
- 15 V switching energy from a -5/+18 V test;
- hot Rds or magnetic saturation from a room-temperature typical value;
- actual choke core loss from DCR, or guaranteed airflow from a fan label;
- exact PCB suitability from an ideal circuit model or clean KiCad DRC.

Unsupported values stay null. If a task permits a sensitivity assumption, label
it assumed and retain the source mismatch. Do not label it measured or a bound.

## Step 3 — Predeclare the case set

Do not edit the supplied expected case list. Check that it contains controls,
the task's changed variable, common 108/120/132 V contract and required stress
points. Report an inadequate list to the coordinator before running.

The default numerical design is intentionally small:

- 9 operating cases: 3 lines × 20/50/100% requested nominal input, nominal
  source-conditioned parameter set, with true-RMS solve and 15 A derating.
- 6 hot full-load cases: 3 lines × 100/125 °C, only if appropriate source curves
  exist; otherwise six explicit INDETERMINATE entries with missing-source reasons.
- 6 full-load gate-profile sensitivities: 3 lines × two alternative profiles.
  The baseline no-assist plus full-assist/DC-max profiles are hypothetical,
  not guaranteed dynamic limits. Use only when applicable to the assigned driver.
- 6 full-load magnetic corners: 3 lines × lower/upper effective L from sourced
  tolerance/bias data. Without such data record unknown rather than choosing ±20%.
- 3 full-load loop-inductance sensitivity cases: one per line, only if the
  coordinator supplies a distinct assumed or geometry-derived loop value.
- 3 frozen baseline controls, one per line at full requested load.
- Up to 6 refinements/independent-oracle cases reserved for nominal and worst
  modeled stress; reserve remaining invocation slots for diagnosed tool failure.

This is at most 39 planned solver calls; missing-domain/source entries consume
case slots but are not invented solver runs. All 48 invocation slots include
failed calls. The coordinator may issue a task-specific smaller exact grid.
Topology studies and source-only tasks use their own declared evidence table;
they must not pretend this single-boost grid applies automatically.

## Step 4 — Execute without changing the measuring instrument

1. Run the supplied baseline controls first, with the frozen binary and inputs.
   Preserve stdout, stderr and process exit codes, including exit 2. Check the
   structured status: an INDETERMINATE exit is not a crash or a physical PASS.
2. If a control cannot reproduce its expected result within the frozen numerical
   tolerance, stop. Ask the coordinator to diagnose; do not tune parameters or
   edit the expected output to recover a green result.
3. For each candidate case, retain actual applied solver inputs. A requested
   90 kHz label with 129 kHz actual input is invalid, even if the result looks good.
4. Use the existing Rust owner for calculations. Do not introduce a spreadsheet
   or Python script as a new verdict authority, and do not fork the event model.
5. When the model rejects CCM or lacks topology support, return MODEL_UNSUPPORTED
   for that case. Do not clamp negative currents or borrow another topology's
   currents. An unsupported simulation is not a rejected hardware architecture.
6. Numeric convergence is checked with the prescribed refinements and independent
   reference. It does not establish that the physical waveform model is correct.
7. Run the issued checker and preserve its output. If it fails, report the failure;
   do not modify its thresholds, schema, case count, source pins or model.
8. No more than one diagnostic rerun after a tool failure, within budget. At the
   deadline write a partial handback. Never continue until a desired result appears.

G0 is the sole exception to data-only ownership: it owns the specified Rust
adapter/checker implementation. G0 follows its implementation/review contract
and does not qualify candidates with its own new unchecked code.

## Step 5 — Complete the accounting

Use the result template. Copy actual identities/statuses; never populate example
nulls with guessed zeroes. Every loss term needs source conditions, units,
evidence class and overlap boundaries. Retain both failed and favorable cases.

- `I_rms² * R` uses the RMS of the component's waveform, not mean or event current.
- `P/V` is not true RMS when ripple or distortion exists. Never add ripple twice.
- Diode conduction and switching depend on different moments and test conditions.
- An event-energy table measured at one current cannot be multiplied by frequency
  and claimed as the line-cycle average without a justified phase-current model.
- Eoss, recovery, overlap and gate-network loss must each be counted exactly once
  within declared boundaries. If boundaries cannot be separated, total is null.
- Keep wall Pin, bus Pout, losses and derived efficiency consistent. Power at the
  pan is not supplied by the PFC model. Do not claim 1800 W output from 1800 W input.
- In a source-only partial result, unknowns stay unknown and no assembly rank is
  emitted. Identify the single missing observation most likely to change the decision.

Write result status on four independent axes. FINISHED means you completed the
assignment; it is not PASS, SELECTED, VALIDATED or QUALIFIED. The checker status
is supplied by its receipt, not your own prose. Physical qualification stays
NOT_PERFORMED for this campaign unless a separate authorized hardware record is
provided and independently reviewed.

## Step 6 — Hand back files, not promises

Produce the artifacts in the main plan. REPORT.md must contain:

1. Task ID, attempt ID, hypothesis and actual changed variable.
2. Exact baseline and candidate identities; which controls reproduced.
3. Complete case counts: expected, attempted, valid, failed, unsupported, unrun.
4. Supported result/subtotal, uncertainty and missing assembly terms.
5. Evidence supporting or refuting the hypothesis, with file/record pointers.
6. Checker result and every unresolved finding.
7. One recommended next observation, or why this branch can be pruned.
8. Actual wall time, invocation count, touched files and deadline outcome.

Preserve files before sending your final message. Send their paths and hashes,
not just a success summary. Do not commit or push unless the coordinator explicitly
assigns that responsibility. After handback, stop; do not start another task.
