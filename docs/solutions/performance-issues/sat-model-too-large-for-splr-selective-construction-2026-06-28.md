---
title: "SAT model explosion — 130K variables unsolvable by splr, fixed with selective net construction"
date: "2026-06-28"
category: performance-issues/
module: temper-rust-router
problem_type: performance_issue
component: tooling
severity: high
symptoms:
  - "Full Temper PCB constraint model: 228,597 variables, splr 0.13 cannot solve within any timeout"
  - "Stage 2 produces ~6,000 skeleton edges × 23 nets = ~138K NetChannelVars, plus ~85K ViaVars from escape via generation"
  - "Even for 3 nets, the full model has 29K variables (splr can solve ~31K with encoding overhead but M=6+ panics)"
root_cause: config_error
resolution_type: code_fix
tags:
  - sat-solver
  - splr
  - constraint-model
  - selective-routing
  - model-decomposition
  - pcb-router
  - escape-vias
---

# SAT Model Explosion — Selective Net Construction Fixes splr Scale Limit

## Problem

The Temper PCB constraint model (23 nets, 2 signal layers, ~6,000 skeleton edges) produces 228,597 variables — 143K NetChannelVars + 85K ViaVars. splr 0.13 cannot solve this within any timeout. The sequential counter encoding adds O(n·k) auxiliary variables per channel, making each additional net's cost compound across all channels.

## Symptoms

- Full model (228K vars): splr hangs indefinitely
- M=6 smallest nets (68K vars): splr panics (`trail_saving.rs:40` — index out of bounds)
- M=3 smallest nets (31K vars): SAT in 10.6s ✓
- Pipeline A\*-only baseline: times out at 5 minutes with 17% completion

## What Didn't Work

- **Bottleneck pruning.** The capacity encoding already skips channels where demand ≤ capacity. The remaining channels are genuinely constrained — pruning doesn't help.
- **Totalizer encoding.** Reduces auxiliary variable count from O(n·k) to O(n log k), but the constraint model itself (pre-encoding) at 31K vars is the bottleneck, not the encoding overhead.
- **Post-hoc constraint model filtering.** Building the full 228K model then filtering to 29K was wasteful and buggy — it kept all ViaVars and non-capacity constraints for non-selected nets.

## Solution

Add `target_net_names` to `ModelBuilder` so it only creates variables and constraints for the specified nets. Downstream constraint methods (`_create_capacity_constraints`, `_create_diff_pair_constraints`, `_create_layer_constraints`) auto-exclude non-target nets because their channel variables were never created.

```python
# constraint_model.py — before (builds everything)
builder = ModelBuilder(skeletons, nets, ...)
cm = builder.build()  # 228K vars

# constraint_model.py — after (builds only target nets)
builder = ModelBuilder(skeletons, nets, ..., target_net_names=["AC_L", "AC_N", "PWM_H"])
cm = builder.build()  # 29K vars (13% of full)
```

The guard is minimal — one `continue` per net-iterating method:

```python
# _create_channel_vars
for net_idx, net in enumerate(self.nets):
    if self.target_set and net.name not in self.target_set:
        continue
    # ... create NetChannelVar

# _create_via_vars
for net_idx, net in enumerate(self.nets):
    if self.target_set and net.name not in self.target_set:
        continue
    # ... create ViaVar
```

The pipeline selects the top N nets by ascending pin count (smallest nets produce the smallest SAT models):

```python
def _select_sat_nets(self, pcb):
    pin_counts = {net.name: len(net.pins) for net in pcb.nets}
    return sorted(pin_counts, key=lambda n: pin_counts.get(n, 0))[:self.max_sat_nets]
```

## Why This Works

Every net adds ~6,233 NetChannelVars (one per skeleton edge) and ~3,706 ViaVars (one per skeleton node). With escape vias enabled, 23 nets × ~9,940 vars = 228K. Limiting to 3 nets = 3 × 9,940 = 29K. The SAT model is linear in net count — the problem was building variables for nets that don't enter SAT.

The downstream constraint methods are self-guarding: `_create_capacity_constraints` checks `if (net_idx, edge_id) in self.model.net_channel_vars` — non-target nets have no channel vars, so their constraints are never built. No explicit guards needed in constraint methods.

## Prevention

- `target_net_names` parameter is the primary prevention — never build what you don't need
- `_select_sat_nets` picks the simplest nets first (ascending pin count) — produces the smallest possible SAT model
- Constraint audit (`audit.rs`) validates every SAT output regardless of model size
- In the pipeline, `max_sat_nets` gates whether target filtering is applied — `None` builds the full model, `Some(N)` builds only N nets
