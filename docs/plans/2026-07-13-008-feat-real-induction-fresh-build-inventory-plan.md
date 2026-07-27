---
title: Fresh-build inventory gate
type: feat
status: stale
date: 2026-07-13
origin: docs/brainstorms/2026-07-13-real-induction-board-closure-arc-requirements.md
swept: 2026-07-25
swept_basis: "insufficient evidence - needs human triage"
---

# Fresh-build inventory gate

Run `ato build src/main.ato:Top`, capture the tool version and source hashes,
then parse the generated KiCad netlist. Reject missing, empty, stale, duplicate
reference/timestamp, duplicate net-code, or count-mismatched artifacts. The
inventory is the only artifact accepted by downstream ingest; it does not
silently substitute the historical board.

Acceptance: a clean build produces a deterministic inventory with component and
net identities, source provenance, artifact SHA-256, command, and tool version.
The current build is green; the generated artifact contains 73 components and
118 nets and passes the inventory parser with freshness checking enabled.

The gate is exercised with Hypothesis-generated fixtures covering deterministic
round-trips, duplicate component identities, and duplicate net codes.
