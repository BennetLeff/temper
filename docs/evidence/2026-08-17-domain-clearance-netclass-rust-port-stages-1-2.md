<!-- provenance: commit=caec25d61 (main, HEAD at task start), worktree agent-a7148c963cf859481.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged at task start. -->

# Stub — domain_clearance.py / netclass_constraints.py Rust-port (stages 1-2)

Survival commit per handoff §15 ("commit a stub as your first action"). This
document will be filled in as stage 1 (finish `domain_clearance.py`'s port +
single-source the `IEC60335_REQUIREMENTS`/`MATRIX_ROWS` safety matrix into
`SafetyValue`) and stage 2 (port `netclass_constraints.py`'s orchestration
loop, coordinating with the sibling agent fixing its classifier) are executed.

Specification: `docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md`
(PR #1319, read via `git show 1e21b6111:...` — not yet on `main` at task
start). Its findings are taken as verified per task instructions.

Status: IN PROGRESS.
