# EXP-01: Pitchfork Fanout Unit Test

**Date:** 2026-01-02  
**Experiment:** temper-3w66  
**Topic:** Router fanout on fine 1.27mm grids

## 1. Overview

This experiment creates a synthetic PCB fixture with 1.27mm (50mil) pitch pin headers to test router fanout capabilities on fine grids. The "pitchfork" pattern consists of multiple rows of closely-spaced pins that require escape routing to inner layers.

## 2. Hypothesis

The router's fanout generator can successfully escape route all pins from a 1.27mm pitch header to inner layers using appropriate via placement and trace routing.

## 3. Methodology

- **Test Fixture:** `packages/temper-placer/tests/fixtures/pitchfork.kicad_pcb`
- **Configuration:**
  - 4 pin headers with 10 pins each (40 total pins)
  - 1.27mm pin pitch (fine grid)
  - 80x60mm board
- **Fanout Generator:** SimpleFanoutGenerator with staggered via placement
- **Metric:** Fanout completion rate (% of pins with valid escape routes)

## 4. Results

```
Board Statistics:
  Footprints: 4
  Total pads: 40
  Named nets: 40

Fanout Results:
  Total fanouts generated: 40
  Unique nets with fanouts: 40
  Vias created: 40
  Traces created: 40

Via Clearance Check:
  Min clearance: 0.2mm
  Via size: 0.6mm
  Violations: 0

[PASS] Fanout test successful!
       All 40 pins have valid fanout routes
       No via-to-via clearance violations
```

## 5. Output Files

- `pitchfork.kicad_pcb`: Generated test board (40 pads)
- `pitchfork_with_fanout.kicad_pcb`: Board with 40 vias + 40 fanout traces
- `config_fanout.yaml`: Fanout configuration
- `run_experiment.py`: Experiment runner
