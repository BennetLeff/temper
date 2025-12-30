# Routing Benchmarks

Benchmark suite for C-Space routing approach comparison.

## Overview

This directory contains benchmarks comparing the C-Space routing approach against traditional methods.

## Running Benchmarks

```bash
# Run all benchmarks
pytest packages/temper-placer/tests/routing/benchmarks/ -v

# Run with benchmark tracking
pytest packages/temper-placer/tests/routing/benchmarks/ -v --benchmark-only

# Save results for comparison
pytest packages/temper-placer/tests/routing/benchmarks/ -v --benchmark-save=routing_results

# Compare against previous results
pytest packages/temper-placer/tests/routing/benchmarks/ -v --benchmark-compare=routing_results
```

## Benchmark Categories

### Performance Benchmarks
- Grid build time (target: < 100ms)
- Route time (target: < 30s)
- Memory usage (target: < 500MB)

### Quality Benchmarks
- DRC violations (target: 0)
- Routing completion (target: 100%)
- HV-LV separation (target: >= 3mm)

### Thermal Benchmarks
- DC_BUS trace width adequacy
- Thermal relief analysis

## Files

- `conftest.py` - Pytest fixtures and benchmark utilities
- `test_c_space_benchmarks.py` - Benchmark tests

## Integration

These benchmarks integrate with:
- `temper_placer.routing.c_space_builder` - C-Space grid generation
- `temper_placer.routing.maze_router` - A* pathfinding
- KiCad board files (temper_drc_verified.kicad_pcb)
