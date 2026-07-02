---
title: "Pattern: Physics-Aware Potential Fields with Hard Safety Gates for Safety-Critical Placement Initialization"
date: 2026-07-01
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - Power devices must be placed with thermal constraints before other components
  - A pipeline needs hard-abort safety gates (not warnings) when thermal limits are violated
  - Placement initialization must be informed by physics-derived field gradients
  - A composite field blends multiple physics models into a single cost surface
  - A DAG pipeline needs a prepended Stage 0 that feeds anchored decisions into downstream stages
tags:
  - thermal-field
  - potential-fields
  - safety-gates
  - greedy-assignment
  - anchor-first
  - pipeline-stage-0
  - curriculum-weighting
---

# Pattern: Physics-Aware Potential Fields with Hard Safety Gates for Safety-Critical Placement Initialization

## Context

Power-device placement on a PCB is a safety-critical problem: if a MOSFET or
regulator is placed where thermal dissipation is insufficient, the board can
overheat, damage components, or fail outright. Naive placement (spreading power
devices evenly across available area) ignores the PCB's thermal gradients:
copper-poor regions conduct heat poorly, adjacent devices couple thermally,
board edges limit heatsink contact, and keepout zones block airflow.

A pipeline that places power devices _after_ other components cannot fix thermal
violations without displacing already-placed devices. The solution is to compute
a composite thermal potential field over the board surface, place power devices
at field minima via a safety-gated greedy assignment, freeze them as fixed
anchors, and then place remaining components relative to those anchors. This
becomes **Stage 0** of a DAG pipeline — it runs first and its outputs are
immutable to downstream stages.

## Guidance

### 1. Composite Thermal Potential Field (5 Components)

The potential field φ(x, y) is a superposition of five physics-derived
components, each normalized to [0, 1] before summation:

```
φ(x, y) = φ_edge(x,y) + φ_copper(x,y) + φ_coupling(x,y) + φ_exclusion(x,y) + φ_convection(x,y)
```

**φ_edge — Board-Edge Proximity Penalty.** Power devices near the board edge
have reduced heatsink contact area and worse thermal coupling to the enclosure.
The penalty is a saturating exponential decay from each edge:

```
φ_edge(x,y) = 1 − exp(−d_edge(x,y) / λ)
```

where `d_edge` is the Manhattan distance to the nearest board edge and `λ` is
the thermal coupling length constant (calibrated per board stackup). Near-edge
locations receive φ_edge ≈ 0 (low penalty = convenient placement), while
board-center locations approach φ_edge → 1 (high penalty — no edge heatsink
benefit). In practice, φ_edge is inverted so that _away-from-edge_ locations are
preferred: the field minimization objective drives devices toward edge regions.

**φ_copper — Copper Density Grid.** A grid-sampled density field computed from
the PCB stackup's copper layers. Each grid cell accumulates the fractional
copper area from all layers, weighted by thermal conductivity `k` and layer
thickness `t`. Copper-poor cells (φ_copper → 1) are penalized; copper-rich cells
(φ_copper → 0) are favorable. This field component is **disabled entirely**
when the PCB stackup has fewer than 4 copper layers (Safety Gate 3), since thin
2-layer boards have minimal lateral thermal conduction and the density grid
becomes misleading noise.

**φ_coupling — Mutual Heating Kernel.** A pairwise kernel that penalizes
placing two power devices too close together. The coupling between devices `i`
and `j` is:

```
φ_coupling(i,j) = P_j × R_θ_board × exp(−d_{ij}² / σ²)
```

where `P_j` is the thermal dissipation of device `j` (from datasheet), `R_θ_board`
is the board-level thermal resistance derived from the stackup (Guidance 4),
`d_{ij}` is the center-to-center distance, and `σ` is the thermal spreading
radius. The kernel is summed over all already-placed devices for each candidate
position.

**φ_exclusion — Step-Function Keepout Zones.** Binary exclusion: regions marked
as keepout (mounting holes, connector overhang, antenna zones) have
φ_exclusion = ∞, making them unreachable by the greedy assignment. Non-keepout
regions have φ_exclusion = 0. This is a hard geometric constraint, not a soft
penalty.

**φ_convection — Airflow Gradient.** A directional gradient field aligned with
the enclosure's forced-airflow axis. Cells upstream (closer to the intake fan)
have lower φ_convection; downstream cells (exhaust side) have higher values.
The gradient is linear along the airflow vector with a slope proportional to the
expected temperature rise across the board length:

```
φ_convection(x,y) = (x · u_air + y · v_air) / L_air × ΔT_rise / T_max
```

where `(u_air, v_air)` is the unit airflow vector and `L_air` is the board
length along that axis.

### 2. Greedy Two-Pass Assignment at Field Minima

Pass 1 (no coupling) runs first: for each power device, compute φ(x,y) without
the φ_coupling term, since no device positions are yet known. Pick the global
minimum of φ across all unoccupied grid cells. Place the device, mark the cell
as occupied, and proceed to the next device.

Pass 2 (with coupling) reruns the assignment with known positions from Pass 1.
φ_coupling is now active because all first-pass positions are known. For each
device, recompute the field with coupling from all _other_ devices' Pass 1
positions. If the new optimal position differs from the Pass 1 position by more
than 5 mm, reassign to the Pass 2 position. Devices within the 5 mm convergence
threshold retain their Pass 1 positions.

```
def greedy_two_pass(devices, board, step=1.0):
    # Pass 1: no coupling
    positions = {}
    for device in devices:
        phi = compute_field(board, positions, device, include_coupling=False)
        positions[device] = grid_min(phi, occupied=positions.values(), step=step)

    # Pass 2: with coupling, reassign if >5mm delta
    positions_2 = {}
    for device in devices:
        others = {d: p for d, p in positions.items() if d != device}
        phi = compute_field(board, others, device, include_coupling=True)
        best = grid_min(phi, occupied=positions_2.values(), step=step)
        if distance(best, positions[device]) > 5.0:
            positions_2[device] = best
        else:
            positions_2[device] = positions[device]

    return positions_2
```

### 3. Three Hard Safety Gates (Pipeline Abort, Not Warning)

Unlike soft-launch fences that emit WARNING and optionally halt later (see
Per-Stage DRC Fence pattern), these safety gates produce **hard pipeline
aborts**. If a gate fails, the pipeline halts immediately — there is no
recovery path and no WARNING-only grace period. Thermal violations in
safety-critical hardware cannot be deferred.

**Gate 1: Heatsink Edge Validation.** After assignment, every power device's
position is checked against the board's heatsink boundary. A device must have at
least `min_heatsink_overlap` (default 80%) of its footprint within the heatsink
region. If any device fails, the gate raises `HeatsinkEdgeError` and the
pipeline aborts.

```
if overlap_ratio(device_pos, heatsink_polygon) < min_heatsink_overlap:
    raise HeatsinkEdgeError(device, overlap_ratio)
```

**Gate 2: Junction Temperature vs Rated Maximum.** For each placed power device,
compute the estimated junction temperature:

```
T_j(device) = T_ambient + P_device × (R_jc + R_θ_board(device_pos))
```

where `R_jc` is the junction-to-case thermal resistance from the package lookup
table (Guidance 5) and `R_θ_board` is the position-dependent board thermal
resistance (Guidance 4). If any device's `T_j` exceeds its datasheet-rated
`T_j_max`, the gate raises `JunctionTemperatureExceededError` and the pipeline
aborts.

```
for device, pos in positions.items():
    t_j = T_ambient + device.P * (device.R_jc + board_resistance(pos))
    if t_j > device.T_j_max:
        raise JunctionTemperatureExceededError(device, t_j, device.T_j_max)
```

**Gate 3: Stackup Layer Count Guard.** Before computing φ_copper, inspect the
PCB stackup. If the board has fewer than 4 copper layers, φ_copper is
**disabled** (set to zero contribution) and a `StackupLayerGuardWarning` is
logged. The rationale: 2-layer boards have negligible lateral thermal
conduction through copper — the density grid would be misleading noise. This
gate runs pre-flight, before any field computation, and the φ_copper disable
is a deterministic behavior change, not a runtime warning.

### 4. R_θ_board Derivation from PCB Stackup

The position-dependent board thermal resistance `R_θ_board(x,y)` is derived
from the stackup geometry at each grid cell:

```
R_θ_board(x,y) = Σ (t_layer / (k_layer × A_effective(x,y)))
```

where `t_layer` is the layer thickness (from stackup definition), `k_layer` is
the layer material's thermal conductivity (copper: 385 W/m·K, FR4: 0.3 W/m·K),
and `A_effective(x,y)` is the local effective thermal cross-section. The sum
runs over all layers in the stackup. At copper-rich cells, `A_effective` is
larger (more copper area), reducing `R_θ_board` — which is consistent with the
φ_copper field also penalizing copper-poor cells.

### 5. R_jc Inference from Package Type Lookup Table

`R_jc` values are not computed dynamically — they are looked up from a
pre-populated table keyed by package type code:

```
R_jc_table = {
    "SOT-23":    85.0,   # °C/W
    "SOT-223":   15.0,
    "TO-252":    3.0,
    "TO-263":    2.0,
    "SO-8":      45.0,
    "QFN-16":    8.0,
    "QFN-32":    5.0,
    "DFN-8":     12.0,
    "WSON-8":    10.0,
    "SOP-8":     50.0,
}
```

Package types not in the table cause a `UnknownPackageTypeError` — treated as a
hard abort because `R_jc` is required for Gate 2's `T_j` calculation. Missing
`R_jc` means `T_j` cannot be bounded, which is a safety-critical gap.

### 6. DAG Manifest Integration as Stage 0 Pipeline Prepending

The thermal anchoring stage is **Stage 0** in the pipeline DAG manifest. It runs
before all other stages and its output (anchored power-device positions) is
immutable to downstream stages. The DAG manifest declares it as:

```yaml
pipeline:
  stages:
    - id: thermal_anchor
      name: "Thermal Potential-Field Anchoring"
      class: ThermalAnchorStage
      priority: 0
      anchors: true
      downstream_forbidden_fields:
        - power_device_positions
        - anchored_components
```

Downstream stages receive the anchored positions as fixed constraints. The
`downstream_forbidden_fields` block enforces immutability: any downstream stage
that writes to `power_device_positions` or `anchored_components` is rejected at
manifest-parse time. This is a static validation, not a runtime check.

### 7. Curriculum Weight Adjustment: thermal_spread Reduced 5× When Anchored

After Stage 0 anchors power devices, the remaining components are placed by
downstream stages (e.g., a force-directed spread stage). These stages typically
have a `thermal_spread` weighting that encourages even thermal distribution.
Once power devices are anchored, this weight is **reduced by a factor of 5**
because:

- The dominant heat sources are already placed at thermal optima.
- Over-weighting thermal spread for low-power passives forces them away from
  power devices, which increases trace lengths without meaningful thermal benefit.
- The 5× reduction is a curriculum adjustment — thermal concerns dominated
  Stage 0 and should now recede, letting signal integrity and routability
  weights dominate.

```python
if "thermal_anchor" in pipeline_outputs and pipeline_outputs["thermal_anchor"].anchored:
    self.weights.thermal_spread /= 5.0
```

### 8. Test Coverage: 49 Tests Across Four Suites

The implementation is validated by 49 tests organized into four suites:

| Suite | Count | Focus |
|---|---|---|
| Property invariants | 18 | Field monotonicity, φ_edge saturation at λ, φ_copper grid consistency, φ_coupling distance decay, φ_exclusion binary behavior, φ_convection gradient linearity, superposition commutativity, normalization bounds [0, 5] |
| Safety gate tests | 12 | Gate 1: heatsink overlap ratios (0%, 50%, 80%, 100%), Gate 2: T_j below/at/above T_j_max, Gate 3: 2-layer disable, 4-layer enable, Gate error types and messages |
| Two-pass assignment | 9 | Pass 1 no-coupling correctness, Pass 2 reassign-on-delta (>5mm), Pass 2 retain-on-convergence (≤5mm), empty board, single-device degenerate case, duplicate-coordinate tiebreaking |
| Integration | 10 | Full pipeline: field → assign → gate → anchor, DAG manifest parse, R_θ_board position dependence, R_jc table coverage (all entries), curriculum weight adjustment, downstream immutability enforcement |

Property invariants include:

- **Monotonicity:** ∀d₁ > d₂: φ_edge(d₁) ≤ φ_edge(d₂) (closer to edge = lower penalty).
- **Saturation:** φ_edge → 0 as d_edge → 0; φ_edge → 1 as d_edge → ∞.
- **Superposition commutativity:** The order in which field components are summed does not affect φ(x,y).
- **Bounds:** 0 ≤ φ(x,y) ≤ 5 when all 5 components are active and normalized.

## Why This Matters

Placing power devices at thermal optima is not an optimization — it's a safety
requirement. A MOSFET at T_j > 175°C fails. Placing it at a local cost minimum
that ignores thermal coupling from an adjacent power device produces a
_technically-optimal_ but _unsafe_ result.

The composite field approach converts diverse physics models (edge proximity,
copper density, mutual heating, exclusion zones, convection) into a single
numerical surface. The greedy two-pass assignment is a heuristic, not a global
optimizer — but the hard safety gates after assignment ensure the heuristic
never produces an unsafe result. This is the key architectural insight: **the
optimizer is allowed to be approximate; the safety gates are not**.

The pipeline-abort severity of the safety gates (vs. soft-launch WARNING) is
deliberate. Thermal violations in hardware are not "fix later" issues. A
violation that halts the pipeline forces the engineer to address it before any
other pipeline stage runs. This prevents waste: without the abort, the router
would spend minutes routing a thermally-unsound placement.

The curriculum weight adjustment (thermal_spread / 5 after anchoring) prevents
a common pathology: downstream stages that try to re-optimize thermal placement
for passives, fighting against the anchored power devices and producing
longer-than-necessary traces. The 5× factor encodes the design judgment that
thermal optimization for low-power passives is ~5× less important than for
power devices.

Stage 0 prepending integrates with the DAG manifest rather than requiring a
separate entry point. This is consistent with the DAG-pipeline pattern: every
pipeline is a sequence of stages, and Stage 0 is simply the first stage in that
sequence. Downstream stages don't need to know that Stage 0 is "special" — they
just receive anchored positions as part of their input state.

## When to Apply

Apply this pattern when:

- Power-dissipating components (MOSFETs, regulators, amplifiers) are present on
  the board and their placement has thermal safety implications.
- The PCB stackup is known and has ≥4 copper layers (if <4, the pattern still
  applies but φ_copper is disabled via Gate 3).
- The enclosure airflow direction and board-edge heatsink geometry are known at
  placement time.
- A multi-stage pipeline exists where power-device placement must precede all
  other component placement.
- Thermal failure is a safety-critical event (not a performance degradation).

Do NOT apply when:

- The board has zero power-dissipating components (purely digital/logic with
  negligible self-heating). The thermal field would be flat and the anchoring
  stage would be a no-op.
- The pipeline is single-pass and does not have distinct thermal-vs-signal
  placement phases.
- R_jc values for all package types are unavailable and cannot be sourced from
  datasheets. Without R_jc, Gate 2 cannot validate T_j, and the pattern's safety
  guarantee is incomplete.
- The board is single-sided with no heatsink — φ_edge would dominate and produce
  degenerate placements at the board edge for all devices.

### Decision Flow

```
Power devices present with known thermal parameters?
    │
    ├─ Stackup ≥4 layers? ── No ──→ φ_copper disabled (Gate 3); proceed with
    │                              4-component field (no copper density)
    │
    ├─ R_jc table populated for all package types? ── No ──→ Hard abort:
    │                                                        cannot validate T_j
    │
    ├─ Heatsink geometry known? ── No ──→ Gate 1 will fail all devices;
    │                                     pattern requires heatsink geometry
    │
    ├─ Multi-stage pipeline with DAG manifest? ── No ──→ Use standalone;
    │                                                    skip manifest integration
    │
    └─ Compute field → assign → gate → anchor → reduce thermal_spread weight
```

## Examples

### Field Computation and Assignment

```python
class ThermalAnchorStage:
    def run(self, state: BoardState) -> BoardState:
        stackup = state.pcb.stackup
        power_devices = [d for d in state.components if d.is_power]

        # Gate 3: disable φ_copper for <4 layers
        include_copper = len(stackup.copper_layers) >= 4
        if not include_copper:
            logger.warning("StackupGuard: <4 copper layers, φ_copper disabled")

        # Build field
        field = CompositeThermalField(
            board=state.pcb,
            include_copper=include_copper,
            airflow_vector=state.enclosure.airflow_vector,
            keepout_zones=state.pcb.keepout_zones,
        )

        # Two-pass greedy assignment
        positions = greedy_two_pass(power_devices, field, step=1.0)

        # Gate 1: heatsink edge validation
        for device, pos in positions.items():
            overlap = state.pcb.heatsink.overlap_ratio(device.footprint.at(pos))
            if overlap < MIN_HEATSINK_OVERLAP:
                raise HeatsinkEdgeError(device=device, overlap=overlap)

        # Gate 2: junction temperature vs rated max
        for device, pos in positions.items():
            r_jc = R_JC_TABLE[device.package_type]
            r_board = stackup.board_resistance_at(pos)
            t_j = T_AMBIENT + device.power * (r_jc + r_board)
            if t_j > device.T_j_max:
                raise JunctionTemperatureExceededError(
                    device=device, t_j=t_j, t_j_max=device.T_j_max
                )

        # Anchor and return
        return state.with_anchored(devices=power_devices, positions=positions)
```

### DAG Manifest Entry

```yaml
pipeline:
  name: "deterministic_placement"
  stages:
    - id: thermal_anchor
      name: "Thermal Potential-Field Anchoring"
      class: ThermalAnchorStage
      priority: 0
      anchors: true
      downstream_forbidden_fields:
        - power_device_positions
        - anchored_components
    - id: component_spread
      name: "Force-Directed Spread"
      class: ForceDirectedStage
      priority: 1
      weights:
        thermal_spread: 0.2  # reduced from 1.0 (5× curriculum adjustment)
```

### Safety Gate Error Output

```
THERMAL SAFETY GATE: ABORT
  Gate:        Junction Temperature
  Device:      Q3 (MOSFET, TO-252)
  Position:    (45.2, 78.9)
  T_j:         182.3°C
  T_j_max:     175.0°C
  Margin:      -7.3°C (OVER LIMIT)
  R_jc:        3.0 °C/W
  R_θ_board:   12.1 °C/W
  Pipeline halted. Fix thermal constraints and re-run.
```

## Related

- `packages/temper-placer/src/temper_placer/deterministic/stages/thermal_anchor.py` — `ThermalAnchorStage`, `CompositeThermalField`, `greedy_two_pass`
- `packages/temper-placer/src/temper_placer/thermal/fields.py` — `EdgeField`, `CopperDensityField`, `CouplingField`, `ExclusionField`, `ConvectionField`
- `packages/temper-placer/src/temper_placer/thermal/gates.py` — `HeatsinkEdgeError`, `JunctionTemperatureExceededError`, `StackupLayerGuard`, `UnknownPackageTypeError`
- `packages/temper-placer/src/temper_placer/thermal/stackup.py` — `board_resistance_at()`, `R_θ_board` derivation, `copper_layer_count`
- `packages/temper-placer/src/temper_placer/thermal/package_table.py` — `R_JC_TABLE` lookup, `UnknownPackageTypeError`
- `packages/temper-placer/src/temper_placer/deterministic/manifest.py` — DAG manifest parser, `downstream_forbidden_fields` enforcement
- `packages/temper-placer/tests/test_thermal_fields.py` — 18 property invariant tests
- `packages/temper-placer/tests/test_thermal_gates.py` — 12 safety gate tests
- `packages/temper-placer/tests/test_thermal_assignment.py` — 9 two-pass assignment tests
- `packages/temper-placer/tests/test_thermal_integration.py` — 10 integration tests
- `packages/temper-placer/tests/conftest.py` — shared thermal test fixtures
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — DAG manifest pattern that Stage 0 prepending integrates with
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — soft-launch fence pattern (contrast with hard safety gates)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — CI-gate enforcement pattern (structural sibling to safety gates)
