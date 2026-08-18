# DRC ceiling re-baseline: closing the `silk_overlap` and 120-sample methodology gaps

**Status: IN PROGRESS — stub committed first per working-pattern instructions.**

**Board sha256 pinned for all numbers in this document:**
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(verified via `sha256sum pcb/temper.kicad_pcb` at the start of this task, in
worktree `agent-aaad9bbfda4c0ef0a`, main `ac8dbf7ab`). This agent does not
modify `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`, and
writes no `Ceiling-Approval:` trailer — this task closes measurement
methodology gaps only; the re-baseline itself is a separate owner-ceremonied
act (per `docs/evidence/2026-08-17-drc-ceiling-rebaseline-measurement-and-declined-approval.md`,
commit `3b032eaf7`).

This document will be filled in as measurement proceeds. See the task's two
gaps:

1. `silk_overlap` — is it obtainable by direct geometric computation
   (validated against kicad-cli), or does it remain "not obtainable" with an
   established reason for why the bucket-pair bisection double-counts here
   but not for `clearance`?
2. The 120-sample bar — per-category sampling requirement derived from
   measured spread, not inherited as a folk number. Is `creepage` still
   nondeterministic today (KiCad issue #20048), or was it fixed / moved to
   `temper_drc_rs` per the 2026-08-04 survey's recommendation?

Raw measurement outputs live under
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/drc-gaps/`
(scratch, not committed).
