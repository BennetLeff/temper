# Temper Placer Requirements Specification

**Version:** 1.0  
**Date:** 2025-12-19  
**Status:** Active  
**Domain:** temper-placer PCB Optimizer

## Document Purpose

This document defines requirements for the JAX-based PCB placement optimizer.
For hardware requirements, see `REQUIREMENTS.md` in the project root.
For firmware requirements, see `FIRMWARE_REQUIREMENTS.md`.

## 1. Optimization Requirements (REQ-PLACER-OPT)

### REQ-PLACER-OPT-01: Overlap Resolution
**Priority:** P0  
**Status:** VERIFIED

Optimizer SHALL produce placements with overlap loss < 1.0.

| Parameter | Value |
|-----------|-------|
| overlap_loss target | < 1.0 |
| Current typical | ~0.5 |
| Measurement | `placer_overlap_loss` metric |

**Validation:** Integration tests, optimizer output JSON  
**Linked Issues:** temper-gcp.9

---

### REQ-PLACER-OPT-02: Boundary Compliance
**Priority:** P0  
**Status:** IN_PROGRESS

All components SHALL be fully within board boundaries (boundary loss < 10.0).

| Parameter | Value |
|-----------|-------|
| boundary_loss target | < 10.0 |
| Components outside | 0 |
| Margin from edge | >= 0.5mm |

**Validation:** `placer_boundary_loss` metric, visual inspection  
**Linked Issues:** temper-vo0, temper-a63

---

### REQ-PLACER-OPT-03: DRC Compliance
**Priority:** P0  
**Status:** VERIFIED

Placements SHALL pass KiCad DRC with 0 violations.

| Parameter | Value |
|-----------|-------|
| DRC violations | 0 |
| Check types | Clearance, courtyard, silkscreen |
| Validation tool | KiCad CLI DRC |

**Validation:** `placer_drc_violations` metric, `temper-placer validate`  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-OPT-04: Convergence
**Priority:** P1  
**Status:** VERIFIED

Optimizer SHALL converge within 8000 epochs for boards with < 100 components.

| Parameter | Value |
|-----------|-------|
| Max epochs | 8000 |
| Component limit | 100 |
| Convergence criteria | Loss delta < 0.001 for 100 epochs |

**Validation:** Optimizer runtime benchmarks  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-OPT-05: Wirelength Optimization
**Priority:** P1  
**Status:** IN_PROGRESS

Optimizer SHALL minimize estimated total wirelength.

| Parameter | Value |
|-----------|-------|
| Wirelength model | Manhattan distance |
| Weight in loss | Configurable |
| Typical improvement | >= 30% vs random |

**Validation:** `placer_wirelength_mm` metric  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-OPT-06: Rotation Support
**Priority:** P1  
**Status:** VERIFIED

Optimizer SHALL support discrete component rotation (0°, 90°, 180°, 270°).

| Parameter | Value |
|-----------|-------|
| Rotation angles | 4 discrete (0, 90, 180, 270) |
| Method | Gumbel-Softmax sampling |
| Temperature annealing | Yes |

**Validation:** Unit tests for rotation, visual inspection  
**Linked Issues:** temper-7t1

---

## 2. Heuristics Requirements (REQ-PLACER-HEUR)

### REQ-PLACER-HEUR-01: Heuristic Pipeline
**Priority:** P1  
**Status:** VERIFIED

The system SHALL apply 10 initialization heuristics before gradient optimization.

| Priority | Heuristic | Purpose |
|----------|-----------|---------|
| HARD | KeepoutAwarenessHeuristic | Respect keep-out zones |
| STRUCTURAL | ConnectorEdgeSnappingHeuristic | Place connectors on edges |
| STRUCTURAL | ThermalEdgePlacementHeuristic | Thermal components near edges |
| STRUCTURAL | CriticalLoopHeuristic | Minimize switching loops |
| ORGANIZATIONAL | FunctionalModuleClusteringHeuristic | Group related components |
| ORGANIZATIONAL | PowerFlowTopologyHeuristic | Input → distribution → load |
| ORGANIZATIONAL | DecouplingCapHeuristic | Decaps near ICs |
| ORGANIZATIONAL | DomainSeparationHeuristic | Separate analog/digital |
| STYLE | StarGroundTopologyHeuristic | Star ground arrangement |
| STYLE | SignalFlowPreservationHeuristic | Left-to-right signal flow |

**Validation:** Unit tests in `tests/heuristics/`  
**Linked Issues:** temper-600

---

### REQ-PLACER-HEUR-02: Heuristic Improvement
**Priority:** P1  
**Status:** VERIFIED

Heuristics SHALL reduce initial wirelength by at least 20% compared to random placement.

| Parameter | Value |
|-----------|-------|
| Wirelength reduction | >= 20% |
| Baseline | Random uniform placement |
| Measurement | Before/after heuristics |

**Validation:** Benchmark tests in `tests/heuristics/`  
**Linked Issues:** temper-600

---

### REQ-PLACER-HEUR-03: Heuristic Ordering
**Priority:** P2  
**Status:** VERIFIED

Heuristics SHALL be applied in priority order: HARD → STRUCTURAL → ORGANIZATIONAL → STYLE.

| Parameter | Value |
|-----------|-------|
| Order enforcement | Pipeline class |
| Conflict resolution | Higher priority wins |
| Partial application | Supported |

**Validation:** Integration tests  
**Linked Issues:** temper-600

---

## 3. Validation Requirements (REQ-PLACER-VAL)

### REQ-PLACER-VAL-01: Preflight Checks
**Priority:** P1  
**Status:** VERIFIED

System SHALL perform preflight validation before optimization:
- Board outline present and valid
- All components have footprints
- Netlist is valid (no orphan nets)
- Constraints file is valid YAML

| Check | Failure Action |
|-------|----------------|
| No board outline | Error, abort |
| Missing footprint | Warning, exclude component |
| Invalid netlist | Error, abort |
| Invalid constraints | Error, abort |

**Validation:** `tests/validation/test_preflight.py`  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-VAL-02: DRC Integration
**Priority:** P0  
**Status:** VERIFIED

System SHALL integrate with KiCad DRC for post-optimization validation.

| Parameter | Value |
|-----------|-------|
| DRC tool | KiCad CLI (`kicad-cli pcb drc`) |
| Output format | JSON report |
| Integration point | `temper-placer validate` command |

**Validation:** `tests/validation/test_drc.py`  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-VAL-03: Constraint Validation
**Priority:** P1  
**Status:** VERIFIED

System SHALL validate constraint YAML before optimization.

| Validation | Description |
|------------|-------------|
| Schema | Valid YAML structure |
| References | Component/net names exist in netlist |
| Values | Numeric constraints in valid range |
| Zones | Zone coordinates within board |

**Validation:** Config loader unit tests  
**Linked Issues:** temper-7t1

---

## 4. Output Requirements (REQ-PLACER-OUT)

### REQ-PLACER-OUT-01: KiCad Compatibility
**Priority:** P0  
**Status:** VERIFIED

Output placements SHALL be valid KiCad PCB files (.kicad_pcb).

| Parameter | Value |
|-----------|-------|
| Format version | KiCad 7.x/8.x |
| Parser library | kiutils |
| Roundtrip accuracy | 100% (no data loss) |

**Validation:** Roundtrip tests in `tests/integration/`  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-OUT-02: JSON Export
**Priority:** P2  
**Status:** VERIFIED

System SHALL export placements as JSON for downstream tooling.

| Field | Type | Description |
|-------|------|-------------|
| component_id | string | Component reference |
| x, y | float | Position in mm |
| rotation | int | Angle in degrees |
| layer | string | PCB layer |

**Validation:** `--placements-json` CLI flag  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-OUT-03: Visualization Output
**Priority:** P2  
**Status:** IN_PROGRESS

System SHALL generate HTML visualization reports.

| Feature | Status |
|---------|--------|
| Board outline | ✓ |
| Component positions | ✓ |
| Net connections | ✓ |
| Loss over time | ✓ |
| Interactive zoom | Planned |

**Validation:** Manual inspection of HTML output  
**Linked Issues:** temper-7t1

---

## 5. Performance Requirements (REQ-PLACER-PERF)

### REQ-PLACER-PERF-01: Optimization Speed
**Priority:** P2  
**Status:** IN_PROGRESS

Optimizer SHALL complete within reasonable time.

| Board Size | Max Time | Current |
|------------|----------|---------|
| < 50 components | 5 min | ~2 min |
| 50-100 components | 15 min | ~8 min |
| > 100 components | 30 min | TBD |

**Validation:** Benchmark suite  
**Linked Issues:** (create issue)

---

### REQ-PLACER-PERF-02: Memory Usage
**Priority:** P2  
**Status:** NOT_STARTED

Optimizer SHALL use < 4GB RAM for boards with < 100 components.

| Parameter | Value |
|-----------|-------|
| Max RAM | 4 GB |
| GPU VRAM | Optional, <= 2GB |
| Component limit | 100 |

**Validation:** Memory profiling  
**Linked Issues:** (create issue)

---

### REQ-PLACER-PERF-03: JAX Acceleration
**Priority:** P1  
**Status:** VERIFIED

Optimizer SHALL utilize JAX JIT compilation for performance.

| Feature | Status |
|---------|--------|
| JIT compilation | ✓ Enabled |
| GPU support | ✓ Optional |
| Vectorized ops | ✓ All loss functions |
| Gradient checkpointing | ✓ For large boards |

**Validation:** Performance benchmarks  
**Linked Issues:** temper-7t1

---

## 6. CLI Requirements (REQ-PLACER-CLI)

### REQ-PLACER-CLI-01: Optimize Command
**Priority:** P0  
**Status:** VERIFIED

`temper-placer optimize` command SHALL accept required inputs and options.

| Argument | Required | Description |
|----------|----------|-------------|
| input.kicad_pcb | Yes | Input PCB file |
| -c/--constraints | Yes | Constraints YAML |
| -o/--output | Yes | Output PCB file |
| --epochs | No | Max epochs (default: 8000) |
| --seed | No | Random seed |
| --heuristics/--no-heuristics | No | Enable heuristics (default: yes) |
| --curriculum/--no-curriculum | No | Enable curriculum (default: yes) |
| --visualize | No | Live visualization |
| --placements-json | No | JSON export path |

**Validation:** CLI integration tests  
**Linked Issues:** temper-7t1

---

### REQ-PLACER-CLI-02: Validate Command
**Priority:** P1  
**Status:** VERIFIED

`temper-placer validate` command SHALL run DRC and report results.

| Output | Format |
|--------|--------|
| Violations | List with severity |
| Pass/Fail | Exit code |
| JSON report | Optional --json flag |

**Validation:** CLI integration tests  
**Linked Issues:** temper-7t1

---

## Requirements Traceability Matrix

| REQ ID | Status | Validation | bd Issue |
|--------|--------|------------|----------|
| REQ-PLACER-OPT-01 | VERIFIED | placer_overlap_loss | temper-gcp.9 |
| REQ-PLACER-OPT-02 | IN_PROGRESS | placer_boundary_loss | temper-vo0 |
| REQ-PLACER-OPT-03 | VERIFIED | placer_drc_violations | temper-7t1 |
| REQ-PLACER-OPT-04 | VERIFIED | benchmarks | temper-7t1 |
| REQ-PLACER-OPT-05 | IN_PROGRESS | placer_wirelength_mm | temper-7t1 |
| REQ-PLACER-OPT-06 | VERIFIED | unit tests | temper-7t1 |
| REQ-PLACER-HEUR-01 | VERIFIED | tests/heuristics/ | temper-600 |
| REQ-PLACER-HEUR-02 | VERIFIED | benchmarks | temper-600 |
| REQ-PLACER-HEUR-03 | VERIFIED | integration tests | temper-600 |
| REQ-PLACER-VAL-01 | VERIFIED | test_preflight.py | temper-7t1 |
| REQ-PLACER-VAL-02 | VERIFIED | test_drc.py | temper-7t1 |
| REQ-PLACER-VAL-03 | VERIFIED | config loader tests | temper-7t1 |
| REQ-PLACER-OUT-01 | VERIFIED | roundtrip tests | temper-7t1 |
| REQ-PLACER-OUT-02 | VERIFIED | CLI test | temper-7t1 |
| REQ-PLACER-OUT-03 | IN_PROGRESS | manual inspection | temper-7t1 |
| REQ-PLACER-PERF-01 | IN_PROGRESS | benchmarks | TBD |
| REQ-PLACER-PERF-02 | NOT_STARTED | memory profiling | TBD |
| REQ-PLACER-PERF-03 | VERIFIED | benchmarks | temper-7t1 |
| REQ-PLACER-CLI-01 | VERIFIED | CLI tests | temper-7t1 |
| REQ-PLACER-CLI-02 | VERIFIED | CLI tests | temper-7t1 |

## Summary Statistics

| Category | Total | Verified | In Progress | Not Started |
|----------|-------|----------|-------------|-------------|
| Optimization (OPT) | 6 | 4 | 2 | 0 |
| Heuristics (HEUR) | 3 | 3 | 0 | 0 |
| Validation (VAL) | 3 | 3 | 0 | 0 |
| Output (OUT) | 3 | 2 | 1 | 0 |
| Performance (PERF) | 3 | 1 | 1 | 1 |
| CLI (CLI) | 2 | 2 | 0 | 0 |
| **Total** | **20** | **15** | **4** | **1** |

**Coverage:** 75% verified, 20% in progress, 5% not started
