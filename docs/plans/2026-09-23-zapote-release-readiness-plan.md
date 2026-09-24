---
title: Zapote release and assembled-test readiness
date: 2026-09-23
status: digital-readiness
parent: docs/plans/2026-09-23-zapote-remaining-roadmap-parallel-plan.md
---

# Release and assembled-test readiness

## Decision

The current release stage is `preintegration`. No integrated cooker PCB, frozen
whole-board suite, fabrication package, or tested assembled article is claimed.
This unit creates an inventory and a fail-closed evidence gate so later work can
advance without confusing a standalone digital result with a release result.

## Implementation

1. Keep a closed registry of source, integrated-board, firmware, suite, native
   CAD, BOM/fabrication, and physical-obligation roles. Require one manifest row
   for every role; reject unknown, missing, or duplicate rows.
2. Bind each present file by SHA-256. For runnable checks, capture the exact
   executable bytes, argument vector, version string, board identity, exit code
   and raw combined output. Replay the command to derive its status. A stored
   `PASS` string and file hash alone have no authority.
3. Make frozen-board identity explicit. A release board must occupy the
   integrated-board role and match the separately pinned frozen hash. A
   standalone board copied under that role, a changed board, or a receipt for
   another board fails. Physical obligations require independent review and
   cannot be promoted by a generic command receipt.
4. Retain mutation tests for missing/duplicate/unknown roles, stale bytes,
   substituted board, forged result, failing replay, and wrong-board receipt.
5. Stage a physical test record with explicit prerequisites, stop conditions,
   calibration and waveform fields. Every stage initially says `NOT_RUN`.

## Exit and handoff

The digital gate and its tests are reproducible. The release verdict remains
`INCOMPLETE` until accepted standalone units, a frozen integrated design and
its source-bound checks, exact manufacturing outputs, independently reviewed
physical evidence and corrective retests exist. The gate does not authorize
energization or appliance use.
