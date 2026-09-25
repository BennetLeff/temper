# Architecture reduction verification — 2026-09-19

Worktree: `/private/tmp/temper-pkgs-1-4`; base revision
`5dde29ab3e2f1223c2d33c129ced2cf647238307`; local changes present.
Agent: Codex. No new electrical protection acceptance is claimed.

- All 48 files listed in `rejected-133/archive-receipt.json` matched their
  recorded SHA-256 after copying.
- All nine restored tracked files matched their recorded baseline SHA-256.
- Canonical candidate PCB is byte-identical to `native-01/section.kicad_pcb`.
- Canonical candidate manifest contains 54 components.
- `component-census.json` assigns all 70 supervisor instances from the rejected
  native-05 manifest exactly once, with no unassigned or duplicate instances.
- `git diff --check`: exit 0.

Command:

```sh
cargo test --locked --offline --manifest-path zapote/Cargo.toml -p zapote-erc --test passive_reva --test passive_protection
```

Result: exit 0. One canonical baseline source/native binding test passed.
Nine historical rejected-supervisor graph/logic tests passed. The latter bind
`native-05`, not the restored canonical candidate. Compilation used the existing
shared Cargo target; these tests do not invoke Python extension measurements.

No new ERC, DRC, thermal simulation, controller transient simulation or hardware
qualification was performed. Restoring identical baseline bytes does not make
previously unresolved protection or cooling requirements pass.
