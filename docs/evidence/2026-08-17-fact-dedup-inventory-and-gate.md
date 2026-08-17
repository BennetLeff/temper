# Fact deduplication inventory + gate — 2026-08-17 (STUB, in progress)

Board sha256 at start of this work: `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`
(matches task brief; unchanged from `HANDOFF-2026-08-17.md`'s claim of the prior
`9c1f4a37…` hash having moved — this is a newer commit, `aec4bf1f8`).

Task: inventory facts stored in more than one place across this repo (safety/geometry
constants, thresholds, net names/netclasses, layer/stackup facts, board metadata,
metric definitions, ratchet ceilings, BOM values, config duplicated across
Python/Rust/YAML/JSON/.kicad_pro/.kicad_dru/docs), declare authority for each, and
build a machine-checked gate that fails when copies diverge — wired into a real
per-PR CI gate, proven non-vacuous.

This is a stub committed first so the worktree survives. Being filled in now.

## Status
- [ ] Inventory swept
- [ ] Authority declared per fact
- [ ] Gate script built (extending existing registries, not a parallel mechanism)
- [ ] Gate wired into a real (non-schedule-only, non-continue-on-error) CI job
- [ ] Gate proven non-vacuous (fails on real divergence, passes once reconciled)
- [ ] Cheap unambiguous divergences fixed
- [ ] Judgment-call divergences left as open findings with precise decision needed
