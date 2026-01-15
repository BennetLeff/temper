# Benders Decomposition Quick Reference

**One-page guide for using the Benders placement optimizer**

---

## Installation

```bash
cd packages/temper-placer
pip install ortools  # Required for ILP solving
```

---

## Quick Start (3 Lines)

```python
from temper_placer.placement.benders_loop import run_benders_optimization

result = run_benders_optimization("data/benders_input.json", max_iterations=20)
print(f"Status: {result.status.value}, Iterations: {result.iterations}")
```

---

## API Reference

### Main Entry Point

```python
from temper_placer.placement.benders_loop import BendersOptimizer, run_benders_optimization

# Method 1: Using convenience function
result = run_benders_optimization(
    component_data_json="data/benders_input.json",
    max_iterations=20,
    verbose=True
)

# Method 2: Using optimizer class (more control)
optimizer = BendersOptimizer(
    component_data_json="data/benders_input.json",
    max_iterations=20,
    time_limit_per_ilp_sec=60.0,
    check_routability=True,  # Set False to skip Max-Flow
    verbose=True
)
result = optimizer.optimize()
```

### Result Object

```python
result.status          # BendersStatus enum (OPTIMAL, FEASIBLE, INFEASIBLE, MAX_ITERATIONS, ERROR)
result.iterations      # Number of Benders iterations executed
result.final_positions # dict[str, tuple[float, float]] - component positions
result.total_movement  # float - total movement in mm
result.cuts_added      # list[RoutabilityCut] - cuts added during optimization
result.solve_time_sec  # float - total optimization time
```

### BendersStatus Enum

- `OPTIMAL`: Found provably routable placement
- `FEASIBLE`: Found feasible placement (routability not verified)
- `INFEASIBLE`: No feasible placement exists
- `MAX_ITERATIONS`: Reached iteration limit
- `ERROR`: Error during optimization

---

## Component APIs

### MinCutMapper

```python
from temper_placer.placement.benders_mincut_mapper import MinCutMapper

mapper = MinCutMapper(components, tolerance_mm=2.0)
blocking = mapper.map_mincut_to_components(min_cut_edges)
pairs = mapper.get_component_pairs(blocking)
```

### CutGenerator

```python
from temper_placer.placement.benders_cut_generator import BendersCutGenerator

generator = BendersCutGenerator(min_gap_mm=2.0, max_gap_mm=10.0)
cuts = generator.generate_cuts(blocking, iteration=0)

# Apply cuts to Master Problem
for cut in cuts:
    cut_type, components, gap = cut.to_master_problem_args()
    master_problem.add_routability_cut(cut_type, components, gap)
```

### Master Problem (Direct Use)

```python
from temper_placer.placement.benders_master import BendersMasterProblem

problem = BendersMasterProblem.from_json("data/benders_input.json")
problem.build()
result = problem.solve(time_limit_sec=60.0)

# Add cuts manually
problem.add_routability_cut("horizontal", ["U1", "U2"], gap_required=5.0)
```

---

## Input Format (benders_input.json)

```json
{
  "board": {
    "width_mm": 100,
    "height_mm": 150
  },
  "coordinate_system": "center",
  "hv_nets": ["AC_L", "DC_BUS+", ...],
  "components": [
    {
      "ref": "U1",
      "width_mm": 10.0,
      "height_mm": 5.0,
      "center_x_mm": 20.0,
      "center_y_mm": 30.0,
      "classification": "FREE",  // FREE, FIXED, or HV
      "hv_nets": []
    }
  ]
}
```

---

## Common Patterns

### Pattern 1: ILP-Only (Skip Routability Check)

```python
optimizer = BendersOptimizer(
    "data/benders_input.json",
    max_iterations=1,
    check_routability=False
)
result = optimizer.optimize()
```

### Pattern 2: Full Benders with Verbose Output

```python
result = run_benders_optimization(
    "data/benders_input.json",
    max_iterations=20,
    verbose=True
)

if result.status == BendersStatus.OPTIMAL:
    print(f"✓ Converged in {result.iterations} iterations")
    for ref, pos in result.final_positions.items():
        print(f"{ref}: ({pos[0]:.2f}, {pos[1]:.2f})")
```

### Pattern 3: Manual Cut Generation

```python
from temper_placer.placement.benders_master import BendersMasterProblem
from temper_placer.placement.benders_mincut_mapper import MinCutMapper
from temper_placer.placement.benders_cut_generator import BendersCutGenerator

# Setup
problem = BendersMasterProblem.from_json("data/benders_input.json")
problem.build()
mapper = MinCutMapper(list(problem.components.values()))
generator = BendersCutGenerator()

# Solve → generate cuts → re-solve
result1 = problem.solve()

min_cut_edges = [...]  # From Max-Flow
blocking = mapper.map_mincut_to_components(min_cut_edges)
cuts = generator.generate_cuts(blocking)

for cut in cuts:
    cut_type, components, gap = cut.to_master_problem_args()
    problem.add_routability_cut(cut_type, components, gap)

result2 = problem.solve()
```

---

## Validation

```bash
# Test min-cut mapper
python3 experiments/test_mincut_mapper.py        # 7/7 tests

# Test cut generator
python3 experiments/test_cut_generator.py        # 10/10 tests

# Test Benders loop (requires OR-Tools)
python3 experiments/test_benders_loop.py         # 8/8 tests

# Test Master Problem
PYTHONPATH=src python3 -m temper_placer.placement.benders_master data/benders_input.json
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'ortools'` | `pip install ortools` |
| ILP solver too slow | Reduce `time_limit_per_ilp_sec` |
| Too many cuts generated | Increase `min_gap_mm` in `BendersCutGenerator` |
| Cuts not opening channels | Increase `tolerance_mm` in `MinCutMapper` |
| Max iterations reached | Increase `max_iterations` or relax movement budget |

---

## Performance Tuning

### Faster convergence:

```python
optimizer = BendersOptimizer(
    ...,
    time_limit_per_ilp_sec=30.0,  # Reduce ILP time
    max_iterations=10,             # Reduce max iterations
)
```

### More aggressive cuts:

```python
generator = BendersCutGenerator(
    min_gap_mm=3.0,  # Larger minimum gap
    max_gap_mm=15.0  # Allow larger gaps
)
```

### More lenient detection:

```python
mapper = MinCutMapper(
    components,
    tolerance_mm=5.0  # Larger tolerance
)
```

---

## Files & Docs

| File | Description |
|------|-------------|
| `placement/benders_loop.py` | Main orchestration |
| `placement/benders_mincut_mapper.py` | Min-cut mapper |
| `placement/benders_cut_generator.py` | Cut generator |
| `placement/benders_master.py` | ILP Master Problem |
| `docs/architecture/BENDERS_INTEGRATION_GUIDE.md` | Full guide |
| `docs/architecture/BENDERS_IMPLEMENTATION_SUMMARY.md` | Implementation details |

---

## Next Steps (After Installation)

1. **Test ILP:** `PYTHONPATH=src python3 -m temper_placer.placement.benders_master data/benders_input.json`
2. **Run experiments:** `python3 experiments/test_benders_loop.py`
3. **Integrate Max-Flow:** See `BENDERS_INTEGRATION_GUIDE.md`
4. **Validate on Temper:** Full board optimization

---

**Quick Tips:**

- Start with `check_routability=False` for fast testing
- Use `verbose=True` to see iteration progress
- Check `result.status` before using `result.final_positions`
- Increase `max_iterations` if reaching limit
- Review `result.cuts_added` to understand bottlenecks
