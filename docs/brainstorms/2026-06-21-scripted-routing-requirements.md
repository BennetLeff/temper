---
date: 2026-06-21
topic: board-specific-scripted-routing
status: ready-for-planning
---

# Scripted Routing Requirements — Temper Board

## Goal

Replace general-purpose PCB routers with a single deterministic Python script that encodes explicit waypoint-by-waypoint routing intent for every critical net on the Temper board, validated in real time by the DRCOracle.

---

## Problem — Why General Routers Failed

- Six or more general-purpose routers (A*, maze, homotopy, Benders, iterative DRC, bidirectional A*) all failed to produce a routable result for this board
- Root cause: general routers search a solution space; the Temper board is not a search problem — the correct routing is **known** from power electronics physics (loop area, current density, creepage), it just needs to be executed correctly
- General routers cannot encode domain intent such as "keep the DC bus switching loop under 5 cm²" or "gate return traces must run adjacent to gate drive traces"; they approximate these constraints through cost functions that the router can trade off
- The combination of HV clearances (2–6 mm), high-current via arrays (Via3x3, Via4x4), and a 4-layer stackup with mandatory plane layers creates a constraint density that exhausts router search budgets

---

## Success Criteria

- [ ] Script routes all nets listed in scope without a single DRC violation (verified by `DRCOracle` and confirmed by KiCad DRC post-route)
- [ ] DC bus switching loop area ≤ 5 cm²
- [ ] Each gate drive loop area ≤ 2 cm²
- [ ] Bootstrap loop area ≤ 1 cm²
- [ ] Script is fully deterministic: same waypoints → same `.kicad_pcb` output every run
- [ ] On waypoint rejection, script exits non-zero and prints a structured diagnostic report (see Diagnostic Output below)
- [ ] Script completes in < 60 seconds on a developer laptop

---

## Scope

### What the script does

- Reads the placed `.kicad_pcb` file via the `pcbnew` Python API
- Iterates nets in priority order (see Net Routing Priority)
- For each net, walks a human-authored waypoint list: `[(x_mm, y_mm, layer, via?), ...]`
- For each segment between consecutive waypoints:
  - Calls `DRCOracle.can_place_track_segment(p1, p2, layer, net, width)` before committing
  - On `True`: writes the track segment to the board via `pcbnew.PCB_TRACK`
  - On `False`: **hard fail** — exits immediately with a diagnostic report
- For via waypoints: calls `DRCOracle.can_place_via(position, via_template, net)` before placing
- After all nets are routed: saves the board and re-runs `DRCOracle.validate_all()` as a final sanity check

### Net routing priority order

Derived from `docs/hardware/CRITICAL_LOOP_DESIGN.md`:

1. **Power loop** — `DC_BUS+`, `DC_BUS-`, `SW_NODE` (HighVoltage class: 3 mm trace, 2 mm clearance, Via3x3)
2. **Gate drive** — `GATE_H`, `GATE_L`, `PWM_H`, `PWM_L` (GateDrive / FinePitch: 0.4 mm / 0.127 mm traces)
3. **Resonant tank** — resonant capacitor side connections (HighCurrent class: 0.5 mm trace, Via4x4)
4. **Control signals** — remaining ESP32-S3 and auxiliary nets (Signal class: 0.2 mm trace)

### Net class rules used

Source: `packages/temper-placer/temper_placer/core/design_rules.py` → `TEMPER_NET_CLASSES`

| Net class | Trace width | Clearance | Via template |
|-----------|-------------|-----------|--------------|
| HighVoltage | 3.0 mm | 2.0 mm | Via3x3 |
| ACMains | 2.5 mm | 6.0 mm | Via2x2 |
| HighCurrent | 0.5 mm | 0.25 mm | Via4x4 |
| GateDrive | 0.4 mm | 0.25 mm | Via1x1 |
| Power | 0.5 mm | 0.25 mm | Via2x2 |
| GND | 1.0 mm | 0.3 mm | Via3x3 |
| Signal | 0.2 mm | 0.15 mm | Via1x1 |
| HighSpeed | 0.15 mm | 0.2 mm | Via1x1 |
| FinePitch | 0.127 mm | 0.1 mm | Via1x1 |

### Layer stackup

| Layer | Role |
|-------|------|
| L1 `F.Cu` | Signal, gate drive |
| L2 `In1.Cu` | GND plane |
| L3 `In2.Cu` | Power planes |
| L4 `B.Cu` | HV / power traces |

### DRCOracle integration

- Class: `DRCOracle` in `packages/temper-placer/temper_placer/deterministic/stages/setup.py` (production implementation at `routing.constraints.drc_oracle`)
- Spatial index: cKDTree; query latency ~0.021 ms
- Methods used:
  - `can_place_track_segment(p1, p2, layer, net, width) -> (bool, reason_str)`
  - `can_place_via(position, via_template, net) -> (bool, reason_str)`
  - `validate_all() -> list[Violation]` — final post-route sweep

### Diagnostic output when a waypoint is rejected

Script prints to stderr and exits with code 1:

```
ROUTING FAILURE
  Net:         DC_BUS+
  Segment:     (45.2, 31.0) -> (52.7, 31.0)  on B.Cu
  Waypoint #:  3 of 9
  Reason:      clearance violation
  Required:    2.000 mm  (HighVoltage class)
  Actual gap:  1.342 mm
  Offending geometry: track DC_BUS- @ (52.1, 30.8)-(52.1, 35.0) on B.Cu
  Fix hint:    move waypoint #3 X to ≤ 50.3 mm or reroute DC_BUS- first
```

Fields: net name, segment endpoints and layer, waypoint index, violation type, required vs. actual clearance, identity of the conflicting geometry, and a suggested fix direction.

---

## Out of Scope

- Plane fills / copper pours — handled separately by KiCad zone fill after routing
- Component placement — already complete; script treats placement as fixed
- Any search or retry logic — the script is a deterministic executor; waypoint updates are a human or agent responsibility
- Routing nets other than those explicitly listed in the waypoint file
- Differential pair length matching (separate concern)
- Manufacturing output (Gerbers, drill files)

---

## Dependencies

| Dependency | Location |
|------------|----------|
| Net class rules | `packages/temper-placer/temper_placer/core/design_rules.py` |
| DRCOracle | `packages/temper-placer/temper_placer/deterministic/stages/setup.py` |
| Loop area targets & priority order | `docs/hardware/CRITICAL_LOOP_DESIGN.md` |
| Placed board file | `hardware/temper.kicad_pcb` (or current working board) |
| pcbnew Python API | KiCad installation (system); no pip install |
| Via templates | `TEMPER_NET_CLASSES` — Via1x1 through Via4x4 defined in design_rules.py |
