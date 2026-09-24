# Cooker release evidence gate

Current stage: **preintegration**. Run from the repository root:

```sh
rustc --edition=2021 zapote/release/release_gate.rs -o /private/tmp/zapote-release-gate
/private/tmp/zapote-release-gate verify . zapote/release/release-manifest.tsv
rustc --edition=2021 --test zapote/release/release_gate.rs -o /private/tmp/zapote-release-tests
/private/tmp/zapote-release-tests
```

An incomplete release returns exit 1, malformed or corrupt evidence returns
exit 2, and only a complete release returns 0. `--replay` is required to
promote a runnable role to `PASS`; it executes the named tool without a shell.
Use it only on trusted, reviewed receipts. The role set is closed in Rust and
every role must appear exactly once in the manifest. `-` means absent evidence,
not a successful or inapplicable check.

The five present source files are byte identities for provisional work, not
accepted unit sources. Their result is `INDETERMINATE`. The integrated board,
firmware, adopted whole-board suite, native ERC/DRC, exact BOM, manufacturing
outputs and every physical obligation are `NOT_RUN`. No assembled cooker has
been tested.

## Receipt contract for a future frozen board

A machine check receipt is produced by `release_gate capture ROOT ROLE ARTIFACT
BOARD TOOL RECEIPT RAW -- ARGS...`. It stores the role, SHA-256 of the exact
board, artifact and tool, the tool's own version output, argument vector, exit
code and hash of raw stdout followed by stderr. The argument vector must name
the canonical integrated board and output artifact paths; the command family
is restricted per role. The command must create a new artifact; capture refuses
to replace existing artifact, raw-output or receipt files. The manifest then
names the artifact and receipt paths and their independent SHA-256 values. `verify --replay`
checks the exact bytes, reruns the same command, compares exit and raw output,
and checks the board/artifact did not change. Historical CLI output alone is
not a passing release check. Nondeterministic checks need a purpose-built
reviewed aggregation receipt and checker extension; weakening byte replay is
not an acceptable workaround.

The frozen stage requires `zapote/integration/cooker.kicad_pcb` and a separately
pinned full SHA-256. This path and pin prevent a standalone-board substitution
in the current schema. They cannot prove that a future board implements every
unit. Integration acceptance and source/netlist/native identity checks must
be reviewed before changing the manifest to `frozen_integrated`. A generic
replay receipt also cannot establish calibration, article identity, thermal
behavior, or a physical stop path; physical roles stay `INDETERMINATE` until a
reviewed measurement-specific gate is implemented and applied.

## Open release blockers

- Accepted standalone auxiliary, discharge, inverter, cooling, programming/UI
  and Rev38 sources with their own construction evidence.
- Complete integrated circuit and native cooker PCB, including a suitable
  390 V bus voltage-sense interface, and a frozen firmware identity.
- Adopted whole-board Rust suite and final-board native ERC/DRC with correct
  KiCad sidecars, repeat sampling where required, and reviewed result semantics.
- Exact selected BOM, fabrication and assembly outputs tied to the frozen board.
- Independently reviewed isolation, default-off, separate VD/VB stop and
  discharge, thermal and assembled-test records.

The [physical protocol](physical-test-protocol.md) is a blank execution
template. It does not authorize energized testing.
