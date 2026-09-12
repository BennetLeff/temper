# Zapote

Zapote is Temper's agent engineering subproject centered on a large Rust
validation suite. The working Python/KiCad editing adapter stays in use.

It shares Temper's product inputs and copies needed existing Rust validators
into focused packages such as `zapote-drc` and `zapote-erc`, retaining tests and
provenance. The agent makes placement and routing decisions; Zapote supplies
explicit board edits, engineering feedback, memory, and recorded execution.
See [ARCHITECTURE.md](ARCHITECTURE.md) for package boundaries and
[VALIDATION.md](VALIDATION.md) for the board-validation objective and coverage
ambition. Replacing the Python adapter is deferred.

The [cooker delivery roadmap](../docs/plans/2026-09-10-1627-zapote-cooker-roadmap-plan.md)
sets the order from standalone buck/MCU units through the complete routed board and
physical bring-up. Each milestone adds cooker circuitry, Rust validation coverage
and reusable engineering lessons; implementation detail is added as it approaches.

## Current status

Zapote has a standalone Rust workspace with core, DRC, ERC and harness packages.
The [RTD unit](rtd/unit/ACCEPTANCE.md) exercises the source-to-board flow, and
[model qualification](rtd/model-correctness/README.md) checks the meaning of its
passive-network certificates. Device applicability and brownout timing remain
INDETERMINATE; physical tests are NOT RUN.

The [standalone current-sense / primary OCP unit](current-sense/README.md)
adds a separately compiled Atopile source, routed native PCB, corrected
transformer land pattern, bounded electrical model and Rust source/geometry
checks. Its acceptance record separates digital verification from unrun
physical qualification and procurement gaps.

The [standalone voltage-sense / OVP unit](voltage-sense/README.md) adds the next separately compiled, routed unit, a corrected ADC divider, source-derived electrical checks and saved-document consistency controls. Its digital construction passes while qualification remains explicit.

The [standalone thermal unit](thermal-sense/README.md) adds two external-NTC channels, loaded-feedback trip/release modeling, exact connectivity controls and a routed native PCB. Rev B adds conditional open-wire detection; physical qualification remains separate.

The [isolated gate-drive unit](gate-drive/README.md) has a routed 100 × 80 mm candidate with clean native ERC/DRC and passing Rust construction checks; physical qualification is unrun. The [active PFC power-entry unit](power-entry/README.md) preserves the 1,800 W nominal AC-input target. Its 230 × 190 mm candidate is placed but unrouted: 94 native unconnected links and a Rust connectivity failure prevent acceptance. See the [two-board demo](demo-gate-power/index.html).

[Engineering memory](skills/README.md) connects reviewed, versioned lessons to
construction inputs through Rust selection and a thin process transport. The
existing `harness-lab/` remains available for legacy experiments. The old Python
migration outline is superseded by [MIGRATION.md](MIGRATION.md).

## Layout

| Path | Purpose |
|---|---|
| `project.toml` | Zapote identity and shared Temper resource map |
| `AGENTS.md` | Local operating rules for work in this project |
| `Makefile` | Rust build/test and common saved-board gates |
| `Cargo.toml`, `packages/` | Rust workspace, validators and harness |
| `ports.toml` | Donor hashes, copied tests and extraction changes |
| `ARCHITECTURE.md` | Rust package ownership and agent/validator contract |
| `experiments/` | Experiment definitions and frozen inputs |
| `skills/` | Versioned agent skills and learned artifacts |
| `artifacts/` | Durable evidence manifests and local artifact indexes |
| `runs/` | Git-ignored runtime output |
| `docs/` | Design, migration, and operating notes |

## Commands

```sh
make -C zapote setup
make -C zapote check
make -C zapote build
```

`setup` checks Rust workspace metadata, `build` builds its binaries/examples,
and `check` runs the Rust tests followed by common checks on every registered
maintained Zapote board. `check-boards` runs just the saved-board checks.

Check any new board with `make -C zapote board-check BOARD=/absolute/path/to/board.kicad_pcb`.
The `zapote-board` Rust CLI reads the actual PCB bytes, hashes them and runs
`DRC.BOARD.STACKUP`; its pass is not a substitute for unit electrical checks
or native ERC/DRC. Register new maintained unit paths in `UNIT_BOARDS` before
acceptance. Historical/frozen artifacts are not modified by these commands.
Legacy buck `qualify-buck` and `engineering` commands remain explicitly delegated.

## Direction

Zapote is not another PCB optimizer. It is the harness layer that makes agent
behavior measurable, repeatable, inspectable, and improvable across Temper's
engineering domains. See `MIGRATION.md` for the planned boundary and the
current source-of-truth decisions.

The [standalone interlock](interlock/README.md) adds seven fault inputs, watchdog/liveness gating and a stateful reset latch. Its source-driven Rust checks evaluate 4,096 gate/state/clock combinations and reject physical connectivity and model mutations. The next separate unit is isolated gate drive; sensor-liveness production and receiver behavior remain integration obligations.
