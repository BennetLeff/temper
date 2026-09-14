# Engineering memory

Zapote keeps three connected records: the durable explanation in
`docs/solutions/`, short versioned notes selected for an attempt, and Rust
validators with counterexamples that enforce engineering acceptance. Notes are
advice. They cannot change the source circuit, operating requirements or verdicts.

The initial package is [rtd-lessons-v1](revisions/rtd-lessons-v1/catalog.json):

| Entry | Applicability |
|---|---|
| `rtd-mem-001` | Portable model-qualification procedure; requires `simulation-evidence-scoping` and `assumption-ledger-reading` capabilities |
| `rtd-mem-002` | Conditional RTD timing result; requires the same capabilities plus matching board, source-manifest, model-source and certificate identities |

The subsequent [current-sense-lessons-v1](revisions/current-sense-lessons-v1/catalog.json)
preserves those entries and adds `current-sense-mem-001`, a portable
land-pattern review procedure requiring `datasheet-land-pattern-review`.
Its preparation check selected both portable procedures and excluded the
RTD-specific fact without matching source identities. Preparation is not proof
of delivery to a future agent. The current-sense attempt's selection, reported
use and review limitations are recorded under `current-sense/memory/`.

The portable note links to the [semantic-binding lesson](../../docs/solutions/best-practices/model-certificates-need-semantic-binding.md).
Exact source identities come from the current engineering input. Never copy
them from the memory catalog just to make an entry selectable. For a different
unit, omit RTD identities: its numerical fact must be excluded.

## Before construction

1. Build `zapote-rtd` from `zapote/Cargo.toml`. Supply an explicit binary path
   to the transport so the receipt can identify the policy used.
2. Prepare an attempt with its ID, actual capabilities, current source hashes,
   required entry IDs and the normal task prompt. `zapote/memory.py` reads
   repository-contained catalog, entry and evidence files; Rust checks their
   bytes and selects applicable notes. Require `rtd-mem-001` when doing model
   qualification; do not require it for an unrelated task.
3. Dispatch the prepared context through the transport to a process that accepts
   the complete model prompt on stdin. Supply argv directly, without a shell.
   Keep credentials in the provider's normal authentication environment, never
   in recorded argv or prompts.
   The process must actually forward that input to its model; the generic
   transport does not turn arbitrary command output into proof of model use.
4. Retain the attempt directory with the request, selection, exact outbound
   prompt, process output and receipt. Failed attempts consume their directory;
   use a new attempt ID and directory after diagnosing a failure.

The Rust entry point is `zapote-rtd --memory-input FILE` (`-` for stdin).
Its `memory/v1` commands include `entry.validate`, `selection.select`,
`promotion.review`, and `context.prepare`. Preparation receives the catalog,
entry and evidence UTF-8 bytes plus task metadata and the base prompt. Complete
rendered memory notes, including headings, are limited to 64 KiB.

The host CLI has `prepare` (save only) and `run` (prepare and dispatch):

```sh
python3 zapote/memory.py run \
  --repo-root "$PWD" \
  --catalog zapote/skills/revisions/rtd-lessons-v1/catalog.json \
  --task path/to/task.json --prompt path/to/task-prompt.txt \
  --binary /absolute/path/to/zapote-rtd \
  --attempt-dir zapote/runs/new-unit-attempt-001 \
  --timeout 300 -- your-provider-adapter
```

Replace the example paths and adapter with the actual task inputs and a provider
command that accepts a full prompt on stdin. The current host buffers child
output in memory; use it for bounded text responses. It is not a general provider
streaming service or an automatic wrapper around every legacy run command.

## What a receipt establishes

| Evidence | Claim supported |
|---|---|
| Prepared context | Rust selected these notes from these bytes |
| Outbound prompt and process receipt | These exact bytes were submitted at the recorded process boundary, with the recorded outcome |
| Provider request capture | The provider adapter forwarded these bytes to the model |
| Agent decision record | The agent reports using a named lesson; this is attributed self-report |
| Observed helper invocation and result | That helper actually ran |
| Controlled comparison | May support an improvement claim, within the experiment's limits |

No helper is supplied by this initial notes-only revision. A successful child
process does not prove model consumption, engineering correctness or improvement.
The existing RTD model gate remains authoritative and keeps device applicability
and brownout timing INDETERMINATE.

## After an attempt

Keep new discoveries as proposals with source/evidence references. Review their
cause, applicability and counterexamples; add or strengthen the Rust regression
when the lesson concerns acceptance. Publish a new revision between attempts,
with new entry/evidence hashes. Do not edit an old revision to repair a frozen
receipt. Do not automatically promote an agent's claim that its solution worked.

The [pre-memory qualification snapshot](../artifacts/model-qualification-before-memory/README.md)
preserves the earlier validator sources and all 62 receipt-bound files while the
live harness evolves. The original acceptance evidence remains unchanged.

See the [integration closeout](../artifacts/memory-integration/README.md) for
the real-catalog controls, process-boundary replay and separate live Luna control.

The [voltage-sense-lessons-v1](revisions/voltage-sense-lessons-v1/catalog.json) revision adds a portable procedure for worst-case substitutions, electrical symbol identities and saved-board evidence binding. Voltage attempt retrieval and its limits are recorded in [the memory record](../voltage-sense/memory/README.md).

The [thermal-sense-lessons-v1](revisions/thermal-sense-lessons-v1/catalog.json) revision adds complete-connectivity and assembly-rating checks. [Thermal memory evidence](../thermal-sense/memory/README.md) separates selected notes, reported use and the incomplete initial dispatch capture.

The [thermal-sense-lessons-v2](revisions/thermal-sense-lessons-v2/catalog.json) revision adds analog open-wire margin, threshold-crossing timing and fault-injection procedures from Rev B. Earlier exact thermal behavior remains historical, not a reusable board fact.

The [interlock-lessons-v1](revisions/interlock-lessons-v1/catalog.json) revision adds stateful compiled-graph counterexamples, package-pin review and the correct nested KiCad ERC report boundary. The [interlock memory record](../interlock/memory/README.md) preserves the preceding catalog selection and review limits.

The [gate-power-lessons-v1](revisions/gate-power-lessons-v1/catalog.json) revision
adds a portable note separating assigned pin nets, physical pad census and actual
copper connectivity. It links the accepted gate-drive construction checkpoint and
the explicitly rejected unrouted PFC candidate. Earlier revisions remain unchanged.

## PFC routing checkpoint

[pfc-routing-lessons-v1](revisions/pfc-routing-lessons-v1/catalog.json) adds the
voltage-profile, exact-part and non-vacuous-counterexample lesson. It preserves
old evidence at its original bytes and binds the new lesson to the routed
checkpoint. This is a reviewed memory artifact; it is not a claim that a future
agent has received it or that it improves routing performance.

## Bridge FEM validation

[bridge-fem-lessons-v1](revisions/bridge-fem-lessons-v1/catalog.json) adds the
independent domain/port and shared-package balance procedure. It is backed by
retained native FEM evidence and mutation regressions. Temperatures and uncertain
assembly parameters are deliberately excluded from portable memory. This revision
records reviewed guidance; it does not establish delivery to a future agent.
