# Benchmark Fixtures (quarantined)

Boards in this directory are **synthetic benchmark fixtures**, not the
production design. They exist only to exercise the placer/router algorithms.

## Rules

- A board here can **never** be a production pipeline input. The artifact
  identity gate (plan `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`,
  unit U3/U4) infers role from this path: `pcb/benchmarks/**` ⇒ fixture.
- Nothing here is derived from `elec/src/*.ato`. Do not treat it as the design.

## Current contents

- `temper_fixture_33.kicad_pcb` — 33-component synthetic fixture. The real
  Temper design has ~100 components (`elec/build/default.net`).

## Sunset

This directory is temporary. Once the production board is generated from
schematics and the placer/router are re-benchmarked against it (plan
`2026-07-15-001` unit U6), this fixture is deleted and the committed
`.kicad_pcb` inventory becomes exactly one board.
