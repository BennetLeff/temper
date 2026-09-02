<!-- provenance: commit=6ad4f325c6a899142056322d7cd142a146eaee84 dirty=false -->
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

This record is intentionally opened before the run and will be completed with
the immutable GitHub and Cloudflare identities produced by that run. A green
local simulation is not accepted as live qualification evidence.

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

## Run identity and result

Status: **PENDING — awaiting the fresh PR event and protected-environment run.**

| Identity | Value |
|---|---|
| PR | pending |
| exact head SHA | pending |
| producer workflow run / attempt | pending |
| publisher workflow run / attempt | pending |
| immutable Cloudflare version ID | pending |
| candidate WASM SHA-256 | pending |
| comparison-contract SHA-256 | pending |
| registered tests | pending |
| R19 agreement | pending |
| production deployment invariant | pending |

## Scope after this run

One successful live run proves the credential, account binding, immutable
upload, sweep, and exact-head status path work together. It does not by itself
satisfy the Phase 6 promotion bar. Promotion remains disabled until ten
consecutive comparable live runs pass and the negative-control/demotion drill
demonstrates that a disagreement removes eligibility.
