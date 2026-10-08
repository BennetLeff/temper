# Temper — ESP32-S3 Induction Cooker

[![zapote](https://github.com/BennetLeff/temper/actions/workflows/zapote.yml/badge.svg)](https://github.com/BennetLeff/temper/actions/workflows/zapote.yml)
[![Firmware Tests](https://github.com/BennetLeff/temper/actions/workflows/firmware-tests.yml/badge.svg)](https://github.com/BennetLeff/temper/actions/workflows/firmware-tests.yml)
[![License](https://img.shields.io/badge/license-proprietary-red)](./LICENSE)

Temper is a consumer induction cooker: a 120 V full-bridge power stage, isolated
gate drive, sensing and protection units, and ESP32-S3 firmware with an
8-state transition-table machine and hardware-latched protection.

> Implementation and qualification status lives with the evidence, not here:
> see [zapote/CHECKS.md](zapote/CHECKS.md) and each unit's acceptance record.
> Nothing has been qualified on hardware.

## Layout

| Path | What it is |
|---|---|
| [`zapote/`](zapote/README.md) | Board validation workspace: Rust ERC/DRC/DFM, the five standalone units (RTD, current-sense, thermal-sense, interlock, gate-drive), the 120 V power stage, native KiCad adapters and fab-house profiles |
| [`firmware/`](firmware/) | ESP32-S3 firmware, host tests, code generators and state-machine/invariant gates (`firmware/tools/`) |
| [`packages/`](packages/README.md) | The design-bundle crate chain zapote's unit tools build on |
| `components/`, `datasheets/` | Part documentation and datasheets |
| `docs/`, `skills/`, `output/` | Plans, evidence and history; product/PCB/mechanical review skills; mechanical and prototype outputs |

The legacy placer/router, the old production board (`pcb/`, `elec/`), datasets,
dashboards and their CI were removed on 2026-10-08. Everything is recoverable from
tag [`archive/temper-legacy-2026-10-08`](https://github.com/BennetLeff/temper/tree/archive/temper-legacy-2026-10-08).

## Check a board

```sh
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
export KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
make -C zapote check-board BOARD=/abs/path/board.kicad_pcb PROFILE=fab-profiles/jlcpcb-2layer-2oz.json
```

Stackup, KiCad ERC/DRC (one finding per violation, with location and values) and
fab-house DFM against a vendor profile. `make -C zapote help` lists the unit,
layout and current checks.

## Build and test

```sh
make zapote          # zapote Rust suite
make firmware-test   # firmware host tests
make crates          # design-bundle crate chain
make bridge-python   # build zapote_bridge (uv sync)
```

See [AGENTS.md](AGENTS.md) for working rules and [CONTRIBUTING.md](CONTRIBUTING.md) for conventions.
