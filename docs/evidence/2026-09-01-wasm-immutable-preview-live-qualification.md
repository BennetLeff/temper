<!-- provenance: commit=8254acc827c0b1cf495eb354a3b7d4a2832aeef3 dirty=false -->
---
date: 2026-09-01
type: evidence
module: wasm-tier
tags: [wasm, cloudflare, preview, r19, qualification]
---

# Immutable Cloudflare preview — first live qualification

## Purpose

This PR is the test article for the first end-to-end run of the Phase 6
exact-head preview path. Opening it creates a fresh `pull_request_target`
event after #1566 placed the corrected, base-owned producer and publisher on
`main`. The source build remains credential-free; only the separately
protected `workflow_run` publisher receives the repository's `CF_TOKEN`.

This record was intentionally opened before the run. The first live attempt
proved the credential and immutable-preview machinery, but exposed a test-name
identity defect that correctly prevents qualification under the bar below. A
green local simulation is not accepted as live qualification evidence; the
corrected exact head therefore needs its own protected live run.

## Acceptance criteria

The run qualifies the path only if all of the following hold:

1. The producer builds the exact PR head and uploads the bounded candidate
   artifact without receiving any repository secret.
2. The `cloudflare-wasm-preview` environment gates the publisher before its
   credential-bearing step begins.
3. The publisher uploads an immutable `temper-wasm-io-types` version, resolves
   that same version by its run-bound tag, and verifies its capability-gated
   `/health` response.
4. The Cloudflare sweep and independently produced native verdict agree by
   test name with zero disagreements, zero unexpected passes, and zero
   wasm-only results.
5. The workflow proves that the production deployment identity is unchanged
   before and after the preview run.
6. The exact-head check on this PR reaches a terminal success and diagnostics
   contain neither `CF_TOKEN` nor the expiring preview capability.

## Attempt 1 — infrastructure passed, qualification did not

Status: **NOT QUALIFIED — two false wasm-only identities violate criterion 4.**

| Identity | Value |
|---|---|
| PR | #1567 |
| exact head SHA | `a3bca3ad6b39c61beddbc7927766e61a8ff803de` |
| producer workflow run / attempt | `33590617453` / `1` |
| publisher workflow run / attempt | `33591154495` / `1` |
| immutable Cloudflare version ID | `b131f128-cae1-4d48-8274-081aae4ab104` (version 112) |
| candidate WASM SHA-256 | `a73df72d8968edda33c821202c8c046b08ecf63eee826964140c42db1249c4ec` |
| comparison-contract SHA-256 | `ff1b64f09e2182f482495a081ff9834f95fd06c14e42e40dbf2a93d4ab771a19` |
| registered / executed tests | 6,927 / 6,927 |
| R19 agreement | 1.0 on 6,925 shared names; 61 native-only; **2 wasm-only** |
| production deployment invariant | unchanged (before/after JSON bit-identical) |
| exact-head PR check | success |

The protected publisher completed in 42 seconds. Its durable stage ledger is:
`artifact_validated`, `version_uploaded`, `health_verified`,
`sweep_and_r19_verified`, and `production_unchanged`. The version health
identity matched the exact head, WASM digest, comparison-contract digest,
service, version ID, ABI, and 6,927-test census. The diagnostics artifact was
uploaded only after both the API token and expiring capability leak checks.

### Finding: nested generated names omitted their parent module

The two wasm-only rows were not extra tests. They were the same frozen DSN
tests that native libtest reported under a different fully-qualified name:

| Generated WASM identity | Native libtest identity |
|---|---|
| `dsn_types::frozen_dsn_tests::frozen_dsn_corpus_is_non_vacuous` | `dsn_types::tests::frozen_dsn_tests::frozen_dsn_corpus_is_non_vacuous` |
| `dsn_types::frozen_dsn_tests::frozen_dsn_matches_golden_corpus` | `dsn_types::tests::frozen_dsn_tests::frozen_dsn_matches_golden_corpus` |

`gen_wasm_test_registry.py` already found the `tests` ancestor when emitting
the Rust callable path, so the module compiled. It did not use that same path
when emitting the string identity consumed by R19. The generator's self-check
therefore passed while the external native/WASM join exposed the defect.

The fix makes the generated identity use every inline ancestor while keeping
the stable splice marker separate. A synthetic nested-module regression test
pins the distinction. Two consecutive regenerations produced identical bytes.
The all-crate derived-artifact check then found the same latent mismatch in
five `temper-thermal` frozen operating-point tests. Regenerating that crate
closed those identities by construction too; the complete derived-artifact
check now passes for every registered crate.

Local isolated-target proof came from a clean detached checkout of commit
`1335c3b8f29c569f3b15123ec8464225512d600b`:

| Measure | Result |
|---|---:|
| generated-registry tests | 29 passed |
| candidate WASM SHA-256 | `86589ee11ede67b1944b36cb87d5f36b39d2b53c0543aebfa0b32f936391d0aa` |
| WASM registered / executed / passed | 6,927 / 6,927 / 6,927 |
| native passed | 6,986 |
| shared names / agreement | 6,927 / 1.0 |
| native-only / wasm-only | 59 / **0** |
| disagreements / unexpected passes | 0 / 0 |

The all-crate regeneration gate also verifies the corrected five-name
`temper-thermal` generated registry. It is not part of this Cloudflare
qualification candidate, so this record makes no separate thermal runtime
measurement claim.

## Corrected live run

Status: **QUALIFIED — every acceptance criterion passed.**

| Identity | Value |
|---|---|
| exact head SHA | `8254acc827c0b1cf495eb354a3b7d4a2832aeef3` |
| producer workflow run / attempt | `33592554528` / `1` |
| publisher workflow run / attempt | `33593061784` / `1` |
| protected deployment | `6215835658` in `cloudflare-wasm-preview` |
| diagnostics artifact | `wasm-preview-verdict-33592554528-1` (`9832482493`) |
| immutable Cloudflare version ID | `c74d83a2-49e1-4c85-bf77-4c4f1a837f8c` (version 114) |
| candidate WASM SHA-256 | `3df5e4c937fd9f39dcd1027bd879230ce71b37bcc3290baa5c49f395fbe9edbc` |
| test-name set SHA-256 | `09daa0db322641cf65da95d01a1ad20947af8709e947477ab5063630bcf899eb` |
| comparison-contract SHA-256 | `8d99b67f0ee776214cec06010a2b4efe8fc20e1e14f4459b318c908572c6a1bf` |
| registered / executed / passed | 6,927 / 6,927 / 6,927 |
| native passed | 6,986 |
| R19 agreement | 1.0 on 6,927 shared names; 59 native-only; **0 wasm-only** |
| disagreements / unexpected passes | 0 / 0 |
| production deployment invariant | unchanged (before/after JSON bit-identical) |
| exact-head PR check | success: `Exact PR-head Worker agrees with native` |

The producer completed in 1 minute 27 seconds without credentials. The
protected publisher completed in 44 seconds after approval. Its durable stage
ledger reached `artifact_validated`, `version_uploaded`, `health_verified`,
`sweep_and_r19_verified`, and `production_unchanged`. The health response
matched the exact head, service, version ID, ABI, module digest,
comparison-contract digest, and test census. The publisher uploaded diagnostics
only after checking them for both the API token and the expiring capability.

## Scope after this run

One successful live run proves the credential, account binding, immutable
upload, sweep, and exact-head status path work together. It does not by itself
satisfy the Phase 6 promotion bar. Promotion remains disabled until ten
consecutive comparable live runs pass and the negative-control/demotion drill
demonstrates that a disagreement removes eligibility.
