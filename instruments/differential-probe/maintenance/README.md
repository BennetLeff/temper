# Stage-53 maintenance handoff

`stage53-ct-applicability.patch` is a documentation-only patch for the separate `worktrees/ps-integrate` checkout. It preserves the native-13/native-17 fixture identities and arithmetic while adding an explicit stage-53 applicability boundary and the recalculated CT estimates. It does not change a simulation, a board, a release hash or an approved test limit.

From the Temper repository root, review/check it with:

```sh
git -C worktrees/ps-integrate apply --check ../../instruments/differential-probe/maintenance/stage53-ct-applicability.patch
```

Apply it in that worktree only when integrating its documentation revision. It was deliberately left unapplied because the probe work owns `instruments/differential-probe` and must not silently change another worktree's historical or pinned inputs.

The metadata/model-path repair is described in [`docs/stage53-ct-correction.md`](../docs/stage53-ct-correction.md). It belongs in a future producer/baseline revision, with the actual model resource and renewed provenance, rather than a patch applied to the current frozen stage-53 board.
