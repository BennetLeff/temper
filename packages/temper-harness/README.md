# temper-harness

The provider transport layer for a self-owned agent harness on the official DeepSeek
API. Sub-project **S0** of
[`docs/plans/2026-09-17-001-feat-deepseek-pcb-harness-s0-provider-transport-plan.md`](../../docs/plans/2026-09-17-001-feat-deepseek-pcb-harness-s0-provider-transport-plan.md),
which is authoritative for what is and is not in scope here.

S0 is the substrate and nothing above it: one client seam, one error taxonomy, one
cost ledger with session lineage, one record/replay store, one fidelity oracle. The
agent loop, L1 assembly, compaction, budget enforcement, and retry policy are S1.

## What this package does *not* claim

Read this before quoting any number it produces.

* **USD is not measured.** The provider's response carries no cost field and no billing
  endpoint was found, so `estimated_usd` is `null` and there is no price table. Token
  counts are exact and reconcile against the provider's own total; money is unknown, and
  a figure derived from an invented rate would be worse than an absent one.
* **Tier A is a reproducibility instrument.** The recorded oracle proves the client
  turns these bytes into this typed view every time. It does not prove the typed view
  means what the provider meant. Tier B — the live canary — anchors the *wire shape*,
  and only that: that no field was renamed, moved, or dropped between the recording and
  a live observation. It says nothing about whether any particular completion is
  reproducible, and nothing about PCB design quality.
* **Fidelity claims are about bytes, not judgement.** Nothing here evaluates whether a
  model's answer is correct.

## Layout

| Path | What it is |
|---|---|
| `src/temper_harness/provider/` | The one module that knows the wire format, the live adapter, the replay adapter, the error taxonomy, and the message array rules |
| `src/temper_harness/ledger/` | Append-only ledger + in-flight journal, session lineage, and the single root-scoped aggregator |
| `src/temper_harness/store/` | Record/replay store with mode and arm exclusivity, content-hash identity, and the redaction canary |
| `src/temper_harness/oracle/` | Tier A: the recorded corpus, checked for fidelity and reproducibility |
| `src/temper_harness/canary/` | Tier B (live shape canary, opt-in) and the bounded concurrency probe |
| `schemas/` | The committed record definitions. R14 makes these the contract; nothing inline |

## The model id

`deepseek-v4.1-flash` **does not exist on this provider.** The account serves
`deepseek-flash` and `deepseek-v4-pro`, and the API's own 400 names them. `deepseek-flash`
is the target. This is recorded rather than quietly corrected because it is the single
most important thing U1's live probe found: every captured byte exists because a
request was issued against a real model rather than against a documented one.

## Running it

```bash
# Everything offline. This is what CI runs.
uv run --no-sync pytest packages/temper-harness/tests

# Lint and types.
cd packages/temper-harness
uv run --no-sync ruff check . && uv run --no-sync ruff format --check .
uv run --no-sync mypy src
```

Both live instruments read the credential from `DEEPSEEK_API_KEY` and never from a
file in the repository. They are on-demand, not CI gates (KTD8).

```bash
# Re-capture the probe set. Rewrites tests/fixtures/captured/ and its manifest.
DEEPSEEK_API_KEY=... uv run --no-sync python -m temper_harness.provider.probe \
    --out packages/temper-harness/tests/fixtures/captured

# Tier B: re-issue the probe set and compare response shapes against the corpus.
# Writes hashed evidence; contains no request body, response body, or key material.
TEMPER_HARNESS_CANARY=1 TEMPER_HARNESS_WRITE_CANARY_EVIDENCE=1 \
DEEPSEEK_API_KEY=... uv run --no-sync pytest \
    packages/temper-harness/tests/canary/test_canary_live.py
```

The canary is not collected unless `TEMPER_HARNESS_CANARY` is set, and if it is
collected without a credential it fails with a typed `credential_missing` error rather
than skipping. A skip would report the same green line as a run, which is the confusion
`R12` exists to prevent.

## Evidence in this tree

* `tests/fixtures/captured/` — the live probe captures, with a manifest carrying each
  request hash, status, and response digest. No fixture carries a credential, and the
  suite asserts that by scanning for a key *shape* rather than by listing fields.
* `tests/oracle/evidence/guard_removal.json` — nine oracle guards, each shown rejecting
  its own perturbation and accepting it once disabled. Re-derived on every test run, so
  it cannot drift from the behaviour it describes.
* `tests/canary/evidence/canary.json` — the Tier B run: per-probe shape digests, the
  response digest, the model, the date, and the commit. No bodies.

## Conventions worth knowing before editing

* **One home per fact.** The usage field list is read from `usage.schema.json`; the
  header allowlist is read from `recording.schema.json`; the supported recording
  versions are read from the same file. A Python constant that restated any of them
  could disagree with the committed schema, which is the drift this arrangement exists
  to make impossible.
* **Fail closed on empty.** Every gate and scan raises on an empty input rather than
  reporting a clean verdict over nothing.
* **Provenance is not the caller's to choose.** A live transport refuses to stamp a row
  `replay` and the replay transport refuses to stamp one `live`.
* **Cancellation is `close()` on the event iterator.** There is deliberately no
  `cancel()` on a transport: a method on the instance cannot be per-call.
* **A read failure mid-stream is classified.** `classify_request_exception` translates
  the HTTP client's hierarchy first, because `requests`' `Timeout` inherits from
  `OSError` and the general classifier would otherwise call a read timeout a
  pre-connection failure — which flips `billable` in the wrong direction.
