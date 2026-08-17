# Gate-drive ampacity key rename fix — 2026-08-17 (stub, in progress)

provenance: commit=8157b4344 (main HEAD at task start) dirty=false

Board sha256 at task start: `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(matches the task brief; `pcb/temper.kicad_pcb` not modified by this task).

This document extends `docs/evidence/2026-08-17-fact-registry-drift-gate-extension.md`
(PR #1320, merged), which registered but deliberately did not fix the defect
described there in its §3.3: `StackupGate._DEFAULT_NET_CURRENTS`
(`packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`) and
`temper_drc_rs::ipc::net_currents()` (`packages/temper-drc-rs/src/ipc.rs:121-122`)
both key on `"GATE_H"`/`"GATE_L"`, net names that do not exist on this board
(the real nets are `GATE_HS`/`GATE_LS`).

STUB — this is a placeholder committed as the first action per this
worktree's operational instructions (uncommitted work is destroyed when an
agent with no commits stops). Full findings, the fix, before/after trace
widths, and full DRC before/after will be filled in as the work proceeds.
