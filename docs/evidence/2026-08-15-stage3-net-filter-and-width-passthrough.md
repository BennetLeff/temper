<!-- provenance: commit=7f6a6bd5c3cf9ce8adc1cd9ab67b677239d34792 dirty=UNKNOWN -->
---
module: temper-placer
tags: [router, stage3, sat, memory, trace-width]
problem_type: dead-option / print-only-filter
---

# 2026-08-15: Stage 3 selective-SAT net filter wired for real + Stage 4.4 width pass-through

Two router defects found by the Stage 3 memory investigation
(`investigate/stage3-memory-blowup`,
`docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md`), fixed on
`fix/router-net-filter-and-width-passthrough` (stacked on PR #1117's
`fix/router-netclass-trace-widths`).

## 1. Stage 3 net-filtering was print-only

`RouterV6Pipeline.max_sat_nets` / `_select_sat_nets` computed the top-N net
subset ("selective SAT") but never passed it anywhere: `ModelBuilder.build()`
encoded **every** net, so the Stage 3 CNF always carried the
`|nets| × |edges|` Sinz AtMostK term — measured 182–200 GB monolith demand on
the 110-net board, OOMing the 62 GB machine at the same pipeline boundary
every run. The only mechanism that actually subset nets was
`enable_net_batching` (off by default, and it renumbers net indices per
batch).

### The fix

- `temper-design-bundle` `ModelBuilder` gains an optional `net_filter` (a
  list of net names). Every per-net creation loop — channel vars, via vars,
  capacity-constraint terms, layer constraints, unbundled bundle-path vars —
  skips nets not in the filter. Net indices are **not** renumbered, so
  variable names (`uses_N{idx}_...`) and the index-based consumers
  (`extract_topology`'s `net_names.get(ni)`, `var_to_net`) stay consistent.
  The capacity-constraint hot loop precomputes per-net selection once (110
  reads) instead of once per (edge, net).
- `_pipeline_route._run_stage3` passes `target_names` as `net_filter` to
  both `ModelBuilder` constructions and as the net list to
  `solve_topology_rust`; the topology output then covers exactly the encoded
  nets. Non-selected nets fall through to Stage 4's existing
  `fallback_channel_path` A* path — `map_topology_to_channels` already drops
  nets with an empty channel sequence, so this is byte-identical to how nets
  the solver leaves unassigned behave today.
- `route_pcb()` and `scripts/route_board.py --max-sat-nets N` now expose the
  option (it was unreachable from every driver — exactly why it rotted into
  print-only).

### Measured on the real board

`TEMPER_MODEL_TRACE=1 scripts/route_board.py --output /tmp/... --max-sat-nets 5`
(route from scratch, board untouched — sha256 verified before/after):

```
[model-trace t=5.542s] ModelBuilder.build() done, pruning=False,
primary_vars=1,020,720 (net_channel=1,020,720, via=0), constraints=109,155
Result: 65/104 nets (62.5%)  segments=3295 vias=28 zones=72  wall=150.9s
```

1,020,720 = exactly 5 nets × the 204,144-edge real skeleton — the filter
collapses the model to 5/110 of the 22.5M-variable monolith. Route completes
in 151 s with no OOM; the pre-fix equivalent (same flag, model built anyway)
is the 182–200 GB blowup the investigation measured.

## 2. Stage 4.4 width pass-through

`assign_trace_widths` received only `default_width`
(`_pipeline_route.py:674`); the net-name keyword cascade matched "POWER" →
`power_width=0.508`, so `power_in.ntc-no`'s declared netclass width never
reached the drawn copper. Drawn copper was 0.508 mm vs the 5.0 mm the
netclass table declares for HighVoltage (the class `power_in.ntc-no`
resolves to) — ~4.5× under the 15 A requirement (3.3 A carried vs 15 A
required).

### The fix

PR #1117's `fix/router-netclass-trace-widths` (this branch's base) threads
`pcb.design_rules` into `assign_trace_widths` and reads
`get_rules_for_net(net).trace_width` — the SSOT — with the keyword cascade
kept only as a loud (WARNING-logged) no-class fallback. Verified on this
branch: `get_rules_for_net("power_in.ntc-no").trace_width == 5.0` (the
post-#1129 re-scope table).

Two follow-ups landed on top:

- #1117's tests pinned 3.0 mm (its pre-re-scope base); the 2026-08-13
  re-scope (#1129) re-valued HighVoltage/HighVoltageTank to 5.0 and moved
  the mA-scale members to HighVoltageSignal at 0.5. Re-pinned to the live
  table (`test_trace_width_assignment.py`,
  `test_zone_stitch_netclass_width.py`) with the re-scope cited — a test
  pinned to a superseded table manufactures confidence.
- 10 new net-filter unit tests (`test_constraint_model_net_filter.py`):
  channel-vars subsetting, capacity-term subsetting (the Sinz input), via
  vars, layer constraints, pruning composition, original-index preservation,
  and the R10 guard firing loudly on an all-excluding filter.

## Verification

- `cargo check`/`clippy -p temper-design-bundle --features python`: clean.
- 246 router_v6 tests pass (constraint-model builder differential/PBT,
  pipeline-route differential/metamorphic/PBT, net-batching, trace-width,
  zone-stitch, net-filter) — zero regressions.
- `make extensions-check`: 10/10 fresh (isolated worktree venv).
- Import-linter gate: PASSED, 0 new violations.
- Live route with `--max-sat-nets 5`: model 1,020,720 vars / 109,155
  constraints, 151 s wall, no OOM (above).
- `pcb/temper.kicad_pcb` sha256 unchanged.
