# AR-PROTECT attempt-001 — checkpoint (Step 1)

Date: 2026-09-18

## Task question

Corrected fault-loop and protection assessment. Assess the **proposed active
bridge** (TEA2209T four-MOSFET synchronous bridge), separate the two fault
classes (line-fed switch shorts vs internal capacitor discharge), name a
protection element that can act on each loop and the faults it cannot
interrupt, keep unresolved peak current / energy distribution null, and pass
every current/energy assignment through the loop-consistency checker.

## Workspace identity

- Worktree: `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`
- Branch: `codex/buck-harness-experiment-plan`
- HEAD: `fd9d705770db3f4d836bbd2d762bf458e6adc834`
- Dispatch `source_revision`: `3691798cac69e894fec3caa6fa66fdc70fe1c4e4` —
  the AR-FAULT `feat` commit, one commit behind HEAD. HEAD is that commit
  **plus** the coordinator's own withdraw/enforce commit, which is the commit
  that added this very dispatch. Same pattern recorded by AR-DESIGN and
  AR-VERIFY; source-only, so the delta cannot affect a number.
- `git status` shows foreign, uncommitted work in the tree (the in-progress
  Rust `fault_loop` migration): `zapote/packages/zapote-erc/src/lib.rs`,
  `zapote/tools/check_fault_loop.py`, `zapote/tools/test_check_fault_loop.py`
  modified; `zapote/packages/zapote-erc/src/fault_loop.rs` and
  `zapote/packages/zapote-harness/src/bin/zapote-fault-loop.rs` untracked.
  **These are not mine. I read and execute them; I do not edit, revert, or
  stage them.** The checker provenance is recorded as working-tree /
  uncommitted in `inputs.json`.

## Changed design variable

**None.** Source-only assessment of the existing routed candidate and the
`AR-DESIGN` / `AR-VERIFY` proposed active bridge. No model, solver, CAD, BOM or
netlist edit.

## Frozen controls

- Contract C1.1 `0accd9bc55afbf875b08ed4dcdd8b7bbaf009d6f6fd1824f6b03c58797a825d6`
- Netlist evidence: `AR-FAULT/attempt-001/raw/netlist_fault_loop.json`
  `83b6b49477a3da69bfade5a4587d9b5edd87539c55aea872094b974db5381f7b`
  (copied byte-identical into `raw/`).
- Fault-loop checker: Rust `zapote-erc::fault_loop`, CLI `zapote-fault-loop`,
  binary sha256 `cc2a3ee60edcf3044f0377e15c6cc57e81833c8f86abe548580e55d06a773c54`.
- Stored energy basis: 4 x 560 uF + 470 nF = 2240.47 uF at 400 V.

## Remaining unknowns (by design, not to be filled)

AC source/line impedance; prospective line-fault current and duration; F1
total clearing behaviour at matching conditions; internal-loop peak current
and the U9/U10 energy split; active-bridge MOSFET survival at the fault
waveform; controller post-fault response.
