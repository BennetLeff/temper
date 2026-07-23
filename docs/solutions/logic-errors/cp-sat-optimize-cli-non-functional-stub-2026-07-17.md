---
title: "temper-placer optimize's CP-SAT branch never calls the solver — prints status text and exits, regardless of config or board"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: cli
symptoms:
  - "temper-placer optimize <board> -c <config> -o <output> --all-gates exits 1 with 'Place->route loop did not converge: gate_unmeasured', all five gates report 'No PCB available for placement DRC' / 'No routed PCB available'"
  - "temper-placer optimize <board> -c <config> -o <output> --no-loop exits 0 but writes no output file at all -- no placement, no error, no artifact"
  - "CLI prints 'CP-SAT placer selected (default)... Full CP-SAT pipeline integration is in progress... Use `temper pipeline` for router-based placement flows' -- but `temper-placer pipeline` is not a real subcommand (temper-placer --help lists no `pipeline` command)"
root_cause: logic_error
resolution_type: workaround
severity: medium
tags:
  - temper-placer
  - cp-sat
  - cli
  - stub
  - dead-code
  - jax-retirement
---

# temper-placer optimize's CP-SAT branch never calls the solver

## Problem

`temper-placer optimize` — the command the U6 plan doc's own baseline file
(`power_pcb_dataset/baselines/temper_production_baseline.yaml`) names as
"how to run a fresh baseline extraction" for the `cp_sat` metrics block —
does not run a CP-SAT placement, with any board, with any config, under any
flag combination.

Reading `packages/temper-placer/src/temper_placer/cli/__init__.py`'s
`optimize()` function directly: the `placer == "cp-sat"` branch (the
default and, per the CLI's own removal of `--placer jax-deprecated`, the
*only* active path) is:

```python
# CP-SAT placer (default, sole active path)
console.print()
console.print("[bold green]CP-SAT placer selected (default).[/]")
console.print("[dim]The JAX gradient-descent pipeline has been removed.[/]")
console.print("[dim]Full CP-SAT pipeline integration is in progress.[/]")
console.print("[dim]Use `temper pipeline` for router-based placement flows.[/]")

# Place→Route feedback loop (U4)
if loop:
    ...
```

Four `console.print` calls and nothing else. No `CpSatPlacementResult` is
constructed, no encoder is invoked, nothing from `temper_placer.placer.cp_sat`
is called. The only code that does anything is the `if loop:` block below
it — and since the "placement" step above never produced one, the loop's
gates immediately report `No PCB available for placement DRC` / `No routed
PCB available` and the loop exits with `gate_unmeasured` after 3 rounds.

**This is not evidence the CP-SAT solver itself is broken.** The solver
code (`cp_sat/encoder.py`, `cp_sat/gates.py`, `cp_sat/loop.py`) exists,
compiles, and — per `docs/solutions/architecture-patterns/
cp-sat-feasibility-first-paradigm-2026-07-03.md` and neighboring pattern
docs — is exercised elsewhere in this codebase. The gap is narrower and
more specific: this one CLI entry point was never wired to call it.

## Symptoms

- `--all-gates` (or any `--loop` invocation, the default): exit 1,
  `Place→route loop did not converge: gate_unmeasured`, all five gates
  (drc/routing/stackup/physics/quality) report no PCB/routed-PCB available.
- `--no-loop`: exit 0, but **no output file is written** — a silent no-op
  success. This is the more dangerous symptom: a script that only checks
  the exit code (rather than verifying the output artifact exists) would
  report success for a run that placed nothing.
- The CLI's own printed fallback advice ("Use `temper pipeline` for
  router-based placement flows") points at a command that does not exist:
  `temper-placer --help` lists `andon, optimize, profile, regression,
  timing, trace, version, watch` — no `pipeline`.

## What Didn't Work

- Assuming the failure was a config problem (tried both the stale generic
  `power_pcb_dataset/corpus/temper/constraints.yaml` the baseline file's
  own comment pointed at, and the physically-grounded
  `configs/temper_production_config.yaml` authored earlier the same day —
  identical stub output from both).
- Assuming `--no-loop` in isolation would at least produce a bare CP-SAT
  placement to inspect. It produces nothing at all, silently.
- Following the CLI's own suggested escape hatch (`temper pipeline`) —
  it's a dead pointer, not a real command.

## Resolution

Not fixed here — this is a genuine gap in the CLI's CP-SAT wiring, not a
config or invocation mistake, and closing it means actually connecting
`optimize()`'s cp-sat branch to the solver code that already exists
elsewhere (`temper_placer.placer.cp_sat`), which is real, non-trivial
integration work outside today's scope.

**What was done instead**: `power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`cp_sat` block is left `null`, with an explicit header comment stating
*why* it's null (this finding) rather than leaving it looking like an
oversight or silently populating it with fabricated numbers. The
deterministic-pipeline half of the baseline (the pipeline that does work)
was refreshed with current numbers instead.

## Why This Works (as a stopgap)

A `null` field with an explanatory comment pointing at a documented root
cause is honest; a fabricated or guessed number in its place would be
exactly the kind of silent-drift bug this whole project's `docs/solutions/`
history exists to prevent. The baseline file's own consumer
(`temper-placer regression`) already treats `cp_sat: null` as "not
measured" rather than failing on it, so this doesn't block anything that
currently depends on the baseline.

## Prevention

- **A CLI command that prints "integration in progress" and exits 0 is a
  trap for automation.** Any script or CI step that checks only the exit
  code (not the presence/content of the promised output artifact) will
  silently treat this as success. If a command path is genuinely
  unfinished, it should exit non-zero with a clear message, not exit 0
  having done nothing — matching this project's own stated fail-closed
  philosophy elsewhere (the identity gate, the DRC ratchet).
- **A "use X instead" fallback message is a promise a reader will try to
  keep.** When `X` (`temper pipeline`) doesn't exist, the message actively
  wastes the next person's time verifying it doesn't exist rather than
  saving them time. Either the referenced command should exist, or the
  message should say what actually works today (or nothing).
- **Plan docs that name a specific command as "how to regenerate this
  baseline" should be verified against the command's actual current
  behavior**, not just its help text or its existence. `docs/plans/
  2026-07-15-001-...`'s U6 section named `temper-placer optimize` as the
  regeneration path; running it (rather than trusting the plan doc's
  description) is what surfaced this.

## Related Issues

- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`,
  unit U6 — the re-benchmark task whose `cp_sat` baseline block this
  blocks; the deterministic-pipeline half is complete and current.
- [`docs/solutions/logic-errors/deterministic-placer-pipeline-post-jax-retirement-stubs.md`](deterministic-placer-pipeline-post-jax-retirement-stubs.md)
  — the original instance of this pattern (JAX-retirement-era code paths
  left unexercised and silently broken) in the deterministic pipeline;
  this is the same pattern's third confirmed instance in this codebase
  (the first two: three deterministic-pipeline type bugs, and
  `ClosureTest`'s hardcoded dead `strategy="template"` default found the
  same day as this one) — all three surfaced only when someone actually
  ran the code end-to-end rather than trusting it compiled or that its
  own tests (which mock or bypass the broken seam) were green.
