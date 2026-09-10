# Continual buck harness

The harness keeps OpenCode as the solver runtime. Ordinary Python runs in a
persistent macOS sandbox, PCB edits and measurements run through KiCad, and Rust
owns admission, hashes, budgets, failure classification, and inheritance policy.
Reusable memory is a versioned pair of `notes.md` and `skills.py`.

This follows the persistent computation and external-evidence ideas in
[Prime Agent](https://arxiv.org/html/2608.23552v1#S2) and the bounded act/refine
and frozen/updating comparison in
[Continual Harness](https://arxiv.org/html/2605.09998v1#S3).
The implementation contract is
[the refinement plan](../docs/plans/2026-09-09-1945-feat-buck-harness-refinement-plan.md),
with the experiment and engineering requirements inherited from
[the engineering plan](../docs/plans/2026-09-09-1635-feat-buck-engineering-validation-plan.md).

## Attempt lifecycle

```mermaid
flowchart LR
  A[Current qualification and engineering evidence] --> B[Fresh attempt]
  B --> C[OpenCode / persistent Python]
  C --> D[Atomic KiCad operation and native measurement]
  D --> E[Rust policy]
  E --> C
  E --> F[Bounded refiner]
  F --> G[Immutable notes and skills revision]
  G --> C
  E --> H[Final local result]
  H --> I[Optional telemetry export]
```

The admitted tools are `inspect`, `check`, `place`, `replace_copper`, and
`execute`. Native edits are staged with the full fixture context, refilled and
checked independently, then atomically committed. A valid failing DRC result
is feedback during construction. `inspect` succeeding means inspection worked;
it does not mean the board passes construction.

Each attempt has one absolute 1,200-second deadline and a budget of 200
successfully committed mutations. Nested Python calls use that same counter.
A cell has a 120-second elapsed ceiling and 64-KiB returned-output limit.
Oversized protocol frames, output floods, lost workers, or killing timeouts
end the attempt as indeterminate and preserve completed-action evidence.

Updating conditions may request refinement after native measurement at
mutation 20, 60, and 100, once each, while construction still fails. Each
refiner call is limited to 90 seconds and the remaining cell/attempt time.
Refinement never extends either deadline.

The refiner receives instructions, current notes/skills, the current native
observation, and the last 20 complete operation pairs from its own attempt.
Rust trims oldest whole pairs to fit 128 KiB. Indispensable context that cannot
fit is recorded as a rejected refinement. The refiner has only the structured
`update_artifacts` operation and returns both files, jointly at most 64 KiB.

## Persistent state and learned artifacts

`Workspace` owns one running Python process. Variables and the active call
stack survive skill replacement. A replacement module gets a new namespace;
old function aliases keep their original module and revision tag. These tags
are diagnostic provenance, not an independent proof of arbitrary Python state.

The trusted host compiles proposed source without executing it. Rust binds the
artifact contents and source-window metadata to SHA-256 identities. Executable
loading happens inside the sandbox. The store publishes a complete manifest
only after both files have been saved; incomplete writes cannot be consumed.
Reads recompute identities and reject symlinks or changed contents. Failed
proposals, failed loads, earlier revisions, and application receipts remain
available. Unchanged baseline contents cannot be called learned memory.

The sandbox admits a bounded Python runtime and dedicated scratch directory.
Real canaries test denied outside reads/writes, repository and board reads,
bootstrap writes, network connections, and subprocess creation. A missing or
unqualified boundary blocks use; there is no import-filter fallback.

## Recovery and experiment isolation

Recovery may resume the same attempt only after a driver interruption following
a complete, verified provider response. The parent must still own the live
worker and verify a fresh liveness challenge plus the acknowledged board,
action count, revision, and unchanged absolute deadline. Arbitrary Python
globals are never reconstructed from serialized representations.

An incomplete or failed provider response remains terminal even if the worker
survives. Native apparatus faults, missing evidence, stale identities, and
invalid admissions are recorded separately from valid model outcomes.

Development has four slots: `buck-dev-a/b` under `fixed_base` and
`updating_base`. Evaluation has six slots: `buck-res-a/b` under `fixed_base`,
`inherited_frozen`, and `inherited_updating`. Each slot is consumed once;
indeterminate slots are retained rather than silently replaced.

Only an explicit frozen development artifact crosses into evaluation. Rank
usable applied revisions by completed construction first, then lower total
elapsed time, then lexical revision digest. No usable revision means no
inherited evaluation. Independent attempts start with fresh board, Python,
OpenCode conversation, working directory, and isolated XDG state. Reserved
results never feed another attempt.

## Run and verify

```sh
make -C harness-lab build check
python3 harness-lab/run_buck_trials.py harness-lab/runs/new-preflight \
  --phase preflight --qualification /path/to/qualification.json \
  --engineering /path/to/report.json
python3 harness-lab/run_buck_trials.py harness-lab/runs/new-development \
  --phase development --qualification /path/to/qualification.json \
  --engineering /path/to/report.json \
  --preflight-receipt harness-lab/runs/new-preflight/preflight-receipt.json
python3 harness-lab/run_buck_trials.py harness-lab/runs/new-evaluation \
  --phase evaluation --qualification /path/to/qualification.json \
  --engineering /path/to/report.json \
  --preflight-receipt harness-lab/runs/new-preflight/preflight-receipt.json \
  --inheritance harness-lab/runs/new-development/inheritance.json
```

Use fresh output directories. The runner rechecks retained evidence against
current source, board, contract, evaluator, approved evidence, and runtime
identities. Old reports saying “pass” do not bypass these checks. The current
engineering limitations and empty approved component/model registries still
block live full-buck scoring. Software controls do not qualify a SPICE model,
electrical performance, fabrication, or hardware safety.

## Optional tracing

Export is disabled by default and runs only after the authoritative local
result is finalized. The adapter sends allowlisted metadata through OTLP/HTTP
JSON in a separate, bounded subprocess. Prompts, executable code, raw tool
payloads, and model credentials are excluded. Export failures produce a
separate diagnostic and do not change results or retries.

Pass `--telemetry` to opt in for a run. Configure a collector using `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` for a complete
URL, or `OTEL_EXPORTER_OTLP_ENDPOINT` for a base URL to which `/v1/traces` is
appended. Explicit OTLP export headers may provide collector credentials.
A collector can forward to LangSmith using its standard exporter.
[LangSmith documents non-LangChain OpenTelemetry ingestion](https://docs.langchain.com/langsmith/trace-with-opentelemetry);
[OTLP specifies the JSON wire format](https://opentelemetry.io/docs/specs/otlp/).
Local collector delivery is tested. Direct SaaS delivery remains unverified.
No LangChain, LangGraph, vector database, or tracing SDK is required.
