<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-a68418bfe13ef8302, branched from main at 11a7e7c52. pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified unchanged, never opened for writing by this task -- every fill/route/DRC run below executes against a scratch copy outside the repo/worktree tracked tree.) -->
---
title: "Resolving the 9 zone_dependent_unmeasured nets: connected, or genuinely open?"
date: 2026-08-18
module: temper-placer
tags: [router, routing, pad-connectivity, zone-fill, drc]
problem_type: routing-completion
status: in-progress
---

# STUB — in progress

**Task**: `docs/HANDOFF-2026-08-17.md` (§1, §4, §12) frames the headline
routing figure as 60/139 connected, with the other 79 nets treated as a
routing deficit. `pad_connectivity_audit.py`'s `category` property
(three-way `connected`/`broken`/`zone_dependent_unmeasured` partition)
says 60 `connected`, 70 `broken`, **9 `zone_dependent_unmeasured`** — pads
whose segment/via graph doesn't join them, but which the audit refuses to
call `broken` because every unreached pad has a zone declared on its own
layer, and the audit has no visibility into zone-fill geometry
(`_parse_zones`'s documented scope limit).

This document will resolve those 9 nets: connected through a filled zone
pour, or genuinely open. Method: identify the 9 by name against the
current committed board (`26981fea2...`), find a way to measure pad-to-pad
connectivity with zones actually filled (KiCad connectivity/ratsnest on a
zone-filled scratch copy, and/or an independent geometric check), validate
that method against nets with an already-known verdict (some of the 60
`connected`, some of the 70 `broken`), then report a verdict per net and
the corrected headline figure.

**Hard rules observed**: `pcb/temper.kicad_pcb` is diagnostic-only, never
written; sha256 verified before/after. No clearance/creepage/copper-weight/
DRU threshold touched. No oracle re-pinning. No widening of what
"connected" means — if a net is only connected under an assumption, that
assumption will be stated explicitly.

Full findings to follow in this document (redeploy in place, same
filename).
