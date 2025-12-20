# Boundary Loss Constant Value Investigation

**Issue**: In correlation analysis, boundary loss returns constant zero across all optimization runs, causing undefined (NaN) correlations with routing metrics.

**Ticket**: temper-h0n9.2

## Root Cause Analysis

### The Problem

Correlation analysis (`scripts/correlation_analysis.py`) captures final loss values after optimization completes. For boundary loss, this consistently returns **exactly 0.0** across all runs with different random seeds.

### Investigation Results

Through TDD-based testing (`tests/losses/test_boundary_constant_investigation.py`), we discovered:

1. **Boundary loss function works correctly**:
   - Returns non-zero when components are outside board boundaries ✅
   - Returns zero when all components are inside ✅
   - Correctly detects keepout zone violations ✅

2. **Smart initialization prevents violations**:
   - Random uniform placement: **97% violation rate** (test confirmed)
   - Optimizer initialization: **0% violation rate** (uses safety margin)
   - Implementation in `PlacementState.create_random()`:
     ```python
     x = jax.random.uniform(key1, (n_components,), 
                            minval=ox + margin, 
                            maxval=ox + board_width - margin)
     ```

3. **Why boundary loss is always zero during optimization**:
   - Components start **inside** board with safety margin
   - Gradient descent keeps them inside (strong penalty gradient pushes components inward)
   - Final loss value is **always exactly 0.0** → no variation to correlate

### Evidence

**Test Suite Results** (all passing):
- ✅ Test 1: Boundary loss detects out-of-bounds components (loss = 3575.00)
- ✅ Test 2: Boundary loss returns zero for valid placements (loss = 0.00)
- ✅ Test 3: Keepout loss detects rectangular zone violations (loss = 156.25)
- ✅ Test 4: Keepout loss detects mounting hole violations (loss = 25.00)
- ✅ Test 5: Random placement has 97% violation rate, but optimizer init prevents this
- ✅ Test 6: Smaller board produces varying boundary loss (mean=306.2, std=107.2)

**Board Statistics** (temper.kicad_pcb):
- Board size: 100mm × 150mm = 15,000 mm²
- Total component area: 858 mm²
- Packing density: 5.7%
- Mounting holes: 4 corner keepouts (5.2mm radius)
- Rectangular keepouts: 0

## Why This Breaks Correlation Analysis

Correlation requires **variation** in both variables:

```
correlation = covariance(X, Y) / (stddev(X) * stddev(Y))
```

When `stddev(boundary_loss) = 0`:
- Division by zero → **NaN**
- Or constant denominator → **correlation = 0.0** (meaningless)

This prevents us from determining if boundary violations actually impact routing quality.

## Proposed Solutions

### Option A: Use Epoch 0 Loss Values (Recommended)

Capture loss values at **initialization** (epoch 0) before optimization:

**Pros**:
- Shows natural variation from random initialization
- No config changes needed
- Tests actual correlation between constraint violations and routing
- Most realistic: measures "does starting with violations hurt final routing?"

**Cons**:
- Requires code change to correlation analysis script

**Implementation**:
```python
# In scripts/correlation_analysis.py
if "data_points" in loss_history and len(data_points) > 0:
    initial_epoch = data_points[0]  # Use epoch 0 instead of final
    if "breakdown" in initial_epoch:
        for loss_name in ["wirelength", "overlap", "boundary", ...]:
            if loss_name in initial_epoch["breakdown"]:
                loss_values[loss_name] = initial_epoch["breakdown"][loss_name]
```

### Option B: Add Keepout Zones to Config

Force boundary violations by adding artificial keepout zones:

**Pros**:
- No code changes
- Tests optimizer's ability to respect keepouts
- Realistic scenario (PCBs often have keepouts)

**Cons**:
- Modifies the problem (not testing "natural" boundary behavior)
- Requires new config file
- Keepouts might be too small to matter

**Implementation**:
```yaml
# packages/temper-placer/configs/temper_correlation_test.yaml
keepout_regions:
  - name: "center_keepout"
    bounds: [40, 60, 60, 90]  # 20mm × 30mm in center
  - name: "left_edge_keepout"
    bounds: [0, 0, 10, 150]   # 10mm strip on left edge
```

### Option C: Use Smaller Test Board

Create a test config with tighter board dimensions:

**Pros**:
- Test 6 proves this works (std=107.2 on 50×50mm board)
- Forces tighter packing → boundary violations during optimization

**Cons**:
- Not representative of actual temper board
- May produce unrealistic routing scenarios
- Components might not fit at all

**Implementation**:
```yaml
# packages/temper-placer/configs/temper_small_board_test.yaml
board:
  width_mm: 50.0   # Reduced from 100mm
  height_mm: 75.0  # Reduced from 150mm
  margin_mm: 5.0
```

### Option D: Disable Smart Initialization

Modify optimizer to skip margin-based initialization:

**Pros**:
- Tests optimizer's ability to recover from bad starts
- Most variation in boundary loss

**Cons**:
- Not testing realistic scenario (smart init is a feature)
- Requires code changes
- Might break convergence

## Recommendation

**Use Option E (Filter Constant Losses) - IMPLEMENTED** because:

1. **Mathematically correct**: Constant values cannot correlate (division by zero in stddev)
2. **Smart initialization is a feature**: Avoiding boundary violations from the start is desirable
3. **No artificial problem modification**: Uses actual temper board and realistic initialization
4. **Generalizable**: Automatically handles ANY constant loss, not just boundary
5. **Clear reporting**: Users see which losses were skipped and why
6. **Minimal code change**: Added std check before correlation computation

**Why other options were rejected**:

- **Option A (Epoch 0)**: Doesn't help - smart init means boundary=0 even at epoch 0
- **Option B (Keepout zones)**: Smart init respects keepouts too - still constant
- **Option C (Smaller board)**: Artificial problem that doesn't represent actual design
- **Option D (Disable smart init)**: Breaks a useful feature for no benefit

**The key insight**: Constant losses aren't a bug to fix - they're a natural result of effective initialization. The correct solution is to recognize and skip them during analysis.

## Implementation

### Changes Made

**File: `scripts/correlation_analysis.py`**

Added std check before correlation computation (line ~247):

```python
# Skip constant losses (std = 0) - they cannot correlate with anything
loss_std = np.std(loss_values)
if loss_std < 1e-10:
    print(f"  Skipping constant loss '{loss_name}' (std={loss_std:.2e})", flush=True)
    continue
```

### Test Results

Ran with 3 samples on temper.kicad_pcb:

```
[3/3] Computing correlations...
  Skipping constant loss 'boundary' (std=0.00e+00)
  Skipping constant loss 'boundary_edge_violation' (std=0.00e+00)
  Skipping constant loss 'boundary_keepout_violation' (std=0.00e+00)
  Skipping constant loss 'boundary_per_component' (std=0.00e+00)
Found 16 loss functions with significant correlations
```

**Result**: ✅ No more NaN/undefined correlations, clear reporting of skipped losses

## Completion Status

1. ✅ **Create TDD test suite** (6/6 tests passing)
2. ✅ **Verify tests pass** (all green)
3. ✅ **Document findings** (this document)
4. ✅ **Implement filter for constant losses** (Option E)
5. ✅ **Verify no NaN correlations** (confirmed with test run)
6. ✅ **Test identifies all 4 constant boundary losses** (boundary, edge, keepout, per_component)
7. ⏳ **Close ticket** temper-h0n9.2

## Test File Location

```
packages/temper-placer/tests/losses/test_boundary_constant_investigation.py
```

Run with:
```bash
pytest tests/losses/test_boundary_constant_investigation.py -v
```

## Related Issues

- **temper-h0n9.1**: Run full correlation analysis (blocked by this issue)
- **temper-h0n9**: Parent epic for correlation analysis validation
- **temper-1my**: Optimizer validation epic (uses correlation analysis)

## References

- `PlacementState.create_random()` in `src/temper_placer/core/state.py`
- `BoundaryLoss` in `src/temper_placer/losses/boundary.py`
- `scripts/correlation_analysis.py` line ~150 (loss history extraction)
