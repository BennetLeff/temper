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
sets the order from buck/MCU integration through the complete routed board and
physical bring-up. Each milestone adds cooker circuitry, Rust validation coverage
and reusable engineering lessons; implementation detail is added as it approaches.

## Current status

Zapote has a standalone Rust workspace with core, DRC, ERC and harness packages.
The [RTD unit](rtd/unit/ACCEPTANCE.md) exercises the source-to-board flow, and
[model qualification](rtd/model-correctness/README.md) checks the meaning of its
passive-network certificates. Device applicability and brownout timing remain
INDETERMINATE; physical tests are NOT RUN.

[Engineering memory](skills/README.md) connects reviewed, versioned lessons to
construction inputs through Rust selection and a thin process transport. The
existing `harness-lab/` remains available for legacy experiments. The old Python
migration outline is superseded by [MIGRATION.md](MIGRATION.md).

## Layout

| Path | Purpose |
|---|---|
| `project.toml` | Zapote identity and shared Temper resource map |
| `AGENTS.md` | Local operating rules for work in this project |
| `Makefile` | Transitional commands delegating to `harness-lab/` |
| `Cargo.toml`, `packages/` | Rust workspace, validators and harness |
| `ports.toml` | Donor hashes, copied tests and extraction changes |
| `ARCHITECTURE.md` | Rust package ownership and agent/validator contract |
| `experiments/` | Experiment definitions and frozen inputs |
| `skills/` | Versioned agent skills and learned artifacts |
| `artifacts/` | Durable evidence manifests and local artifact indexes |
| `runs/` | Git-ignored runtime output |
| `docs/` | Design, migration, and operating notes |

## Transitional commands

```sh
make -C zapote setup
make -C zapote check
make -C zapote build
```

These commands still delegate to the legacy harness. Build and test Zapote's
implemented Rust suite with `cargo build --manifest-path zapote/Cargo.toml` and
`cargo test --manifest-path zapote/Cargo.toml` from the repository root.

## Direction

Zapote is not another PCB optimizer. It is the harness layer that makes agent
behavior measurable, repeatable, inspectable, and improvable across Temper's
engineering domains. See `MIGRATION.md` for the planned boundary and the
current source-of-truth decisions.
