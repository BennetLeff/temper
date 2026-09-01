<!-- provenance: commit=c24d0381044e6c77621d18a7616b5e945bb4419b (persistent main commit for PR #1523 carrying this evidence; original experiment worktree ref was not retained) dirty=false -->
# Regional HV↔SELV layout candidates — bounded result

## Decision contract

The experiment followed
`docs/ideation/2026-08-26-hv-selv-layout-convergence-ideation.md`: at most two
candidates per region, evaluated by the Rust-owned regional Pareto kernel.
A candidate must introduce no HV↔SELV pair, no routed-pad endpoint drift, no
new or worsened F.Fab collision, no total DRC-finding rise, and no increase in
the hard-veto DRC categories. At least one tracked quantity must improve.

All seven target footprints were confirmed unrouted at their pads before the
experiment. The baseline was the post-#1521 board: 93 HV↔SELV pad pairs below
12.6 mm, 409 DRC errors, and 402 warnings.

## Results

| region | candidate | pair result | DRC result | verdict |
|---|---|---:|---:|---|
| R23/R43 | R43 `(41.54,187.57)` → `(37.54,189.57)` | 93 → 89, no new pair | errors 409 → 414 | reject: shorting +2, clearance +1, R43↔U17 body collision |
| R23/R43 | R23 `(51.75,184.22)` → `(51.75,179.50)` | 93 → 89, no new pair | errors 409 → 409; warnings 402 → 403 | reject: total findings +1 |
| C14/U13 | U13 `(147.70,42.48)` → `(150.70,46.48)` | 93 → 90, no new pair | errors 409 → 406; warnings unchanged | **accept** |
| R4/U6/U16 | R4 → `(78.14,162.80)`, U6 → `(86.41,141.73)` | 90 → 86, no new pair | errors 406 → 408 | reject: shorting and hole-clearance rises |
| R4/U6/U16 | R4 only → `(78.14,162.80)` | two removed, one new pair | errors/warnings unchanged | reject: new HV↔SELV pair |

The accepted U13 candidate removes exactly these pairs:

- C14.1 `+170V_BUS` ↔ U13.2 `gnd`
- C14.1 `+170V_BUS` ↔ U13.4 `gnd`
- C14.1 `+170V_BUS` ↔ U13.5 `+3V3`

It has zero routed-pad endpoint drift and zero new or worsened F.Fab body
collision. Re-evaluation against the committed board reproduced the scratch
verdict exactly.

## DRC re-measurement

The accepted board is clean commit
`2da1fcb3857064a4c1bde09e991b825ed26c24cf`, SHA-256
`a65bb65c5247493637f9acb510769e604d0e407b256e87e1845160609052b13f`.
After regenerating `pcb/temper.kicad_dru` and verifying all 10 pyo3 extensions
fresh immediately before measurement, 120
`temper_placer.validation._drc_api.run_drc()` runs with kicad-cli 10.0.5
produced zero spread:

- errors: 406 in 120/120 runs;
- warnings: 402 in 120/120 runs;
- creepage: 100 in 120/120 runs, down from ceiling 103;
- every other error and warning category unchanged.

The ceiling therefore ratchets 409 → 406 and creepage 103 → 100. No category
rises and no noise headroom is required.

## Consequence

The bounded placement search is over. R23/R43 and R4/U6/U16 each exhausted
their two-candidate budget. Further coordinate tuning would be the
ad-infinitum behavior this experiment was designed to prevent; their remaining
shortfalls now require a topology, package, isolation-slot, or standards-level
decision rather than another placement nudge.
