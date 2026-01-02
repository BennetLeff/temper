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
- **Metric:** Fanout completion rate (% of pins with valid escape routes)

## 4. Expected Results

- All 40 pins should receive valid fanout routes
- No DRC violations from via-to-via clearance
- Routes should escape to appropriate inner layers

## 5. Files

- `pitchfork.kicad_pcb`: Generated test board
- `config_fanout.yaml`: Fanout configuration
- `run_experiment.py`: Experiment runner
