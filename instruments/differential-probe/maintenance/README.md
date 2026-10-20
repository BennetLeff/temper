# Stage-53 maintenance handoff

`stage53-probe-operating-rules.patch` preserves the 2026-10-20 changes actually applied to the producer checkout's BRING-UP and COMMISSIONING notes at the user's request. It adds the battery-only/no-additional-HOT-earth restriction, explicitly excludes the existing bonded steps 2–4, and adds the measured CT-burden cross-check record. It changes no board, frozen BOM, firmware setting or limit. The producer's commissioning-board-table check passes with these edits; its pre-existing finding about a firmware ceiling range above the fitted bank's procedural limit remains. This patch is archived on the probe branch so these edits are not dependent on the producer worktree's lifetime. It is separate from the older, unapplied CT applicability patch below.

`stage53-ct-applicability.patch` is a documentation-only patch for the separate `worktrees/ps-integrate` checkout. It preserves the native-13/native-17 fixture identities and arithmetic while adding an explicit stage-53 applicability boundary and the recalculated CT estimates. It does not change a simulation, a board, a release hash or an approved test limit.

From the Temper repository root, review/check it with:

```sh
git -C worktrees/ps-integrate apply --check ../../instruments/differential-probe/maintenance/stage53-ct-applicability.patch
```

Apply it in that worktree only when integrating its documentation revision. It was deliberately left unapplied because the probe work owns `instruments/differential-probe` and must not silently change another worktree's historical or pinned inputs.

The metadata/model-path repair is described in [`docs/stage53-ct-correction.md`](../docs/stage53-ct-correction.md). It belongs in a future producer/baseline revision, with the actual model resource and renewed provenance, rather than a patch applied to the current frozen stage-53 board.
