# Operating matrix 07 execution scope

User approved working through clamp correction, normal startup/regulation,
line/load coverage, faults from accepted operating points, and hardware
correlation, with Luna subagents. Hardware is unavailable: only the correlation
specification can be completed for that final step.

Canonical checkout /private/tmp/temper-pkgs-1-4, feature branch
codex/power-entry-pkgs-1-4, base5dde29ab3e2f1223c2d33c129ced2cf647238307.
Experiment06 is read-only and hash-verified before dispatch. Inputs include
uncommitted historical evidence; this run does not commit/publish inherited work.
Native Luna subagents are explicitly user-selected; no external CLI engine.

Independent first units use isolated no-checkout worktrees and own only output/:
- matrix07_clamp: /private/tmp/temper07-clamp — corrected source and clamp tests.
- matrix07_normal: /private/tmp/temper07-normal — startup, settled operation,
  then nine line/load points if the baseline is valid.
- matrix07_checker: /private/tmp/temper07-checker — independent Rust waveform
  checks and hardware-correlation/fault acceptance specifications.

Host owns source-to-model integration, physical standby interface checks,
independent reruns, fault execution after normal-state acceptance, review,
frozen-input verification and final receipt. Worker outputs are proposals until
host integration and verification. No overlapping writes or worker Git mutations.

Acceptance order: corrected clamp and valid model → stable nominal operating
point → line/load endpoints → faults from accepted states. Do not fill a missing
operating point with hand-picked initial conditions, tune a limit to make a run
pass, or credit a gate shutdown with interrupting a shorted switch. Averaged
models, if needed for runtime, must be distinguished from switching models and
cross-checked; decimated current cannot silently become switching RMS evidence.

Every attempt has a bounded runtime, retained source/log/trace and explicit
pass/fail/indeterminate outcome. Missing physical data remain separate from
implementation defects. New engineering calculations/checks use Rust; shell and
Python may transport files/commands/hashes only.
