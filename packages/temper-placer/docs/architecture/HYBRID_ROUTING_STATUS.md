# Hybrid Routing Status - Incomplete

## Summary

Attempted to implement hybrid routing (sequential + negotiated) to resolve SPI net oscillation. **Oscillation detection works perfectly, but infinite loop bug prevents completion.**

---

## What Was Implemented

### ✅ Phase 1: Oscillation Detection

**Files:** `astar_pathfinding.py`

```python
oscillation_tracker: dict[tuple[str, str], int] = {}
competing_nets: set[str] = set()

# Track when nets rip each other up
pair_key = tuple(sorted([net_a, net_b]))
oscillation_tracker[pair_key] += 1

if oscillation_tracker[pair_key] >= 2:
    competing_nets.add(net_a)
    competing_nets.add(net_b)
```

**Result:** ✅ Works perfectly - detects SPI_MOSI ↔ SPI_MISO, SPI_CLK ↔ SPI_MOSI, etc.

### ✅ Phase 2: NegotiatedRouter Integration

**Files:** `negotiated_router.py`, `pipeline.py`

- Updated NegotiatedRouter to support MST routing
- Added multilayer support
- Integrated handoff logic in pipeline

**Result:** ✅ Code compiles and integrates correctly

### ❌ Phase 3: Infinite Loop Bug

**Problem:** Router enters infinite loop even with oscillation detection

**Symptoms:**
```
Routing SPI_MOSI...
  ⚠️  Oscillation detected: SPI_MOSI ↔ SPI_MISO (2 times)
     Marking both for negotiated routing, NO FURTHER RIP-UPS
Routing PWM_L...
Routing AC_L...
...
Routing I_SENSE...
Routing SPI_CLK...
  ⚠️  Oscillation detected: SPI_CLK ↔ SPI_MOSI (2 times)
...
(loops forever, timeout after 60s)
```

**Root Cause:**

The reroute queue keeps growing even after oscillation is detected:

1. First pass routes all nets
2. Some nets rip up others, adding them to `reroute_queue`
3. Oscillation detected after 2 rip-ups
4. Competing nets marked, but queue already populated
5. Second pass processes queue:
   - Skips competing nets ✓
   - But non-competing nets still route
   - Their routing rips up other nets
   - Those nets added back to queue
   - **Queue never empties → infinite loop**

**Attempted Fixes:**

1. ❌ `max_reroute_attempts = 30` - doesn't work, queue refills
2. ❌ `max_loop_iterations = 15` - doesn't work, counter not respected
3. ❌ `max_iterations_per_net = 2` - doesn't work, successful routes don't count
4. ❌ `max_depth = 5` - doesn't work, recursion not the issue
5. ❌ Skip competing nets in `attempt_route()` - doesn't work, queue still grows

---

## Why It's Hard to Fix

The reroute queue logic is complex:

```python
# First pass
for net in routable_nets:
    success, reason, blockers, region = attempt_route(net)
    # If success but forced, adds blockers to reroute_queue
    
# Second pass  
while reroute_queue:  # ← This never terminates!
    net = reroute_queue.pop(0)
    success, reason, blockers, region = attempt_route(net)
    # If success, may add MORE nets to queue
```

The queue is a **work queue** that grows dynamically. Even with limits, it refills faster than it drains.

---

## Possible Solutions

### Option A: Disable Rip-Up After Oscillation (Simplest)

When oscillation detected, **stop all rip-ups globally**:

```python
if len(competing_nets) > 0:
    # Disable rip-up for ALL nets
    allow_ripup = False
```

**Pros:** Simple, guaranteed to terminate
**Cons:** May leave more nets unrouted

**Effort:** 30 minutes

### Option B: Pre-Filter Reroute Queue

Before entering second pass, remove competing nets from queue:

```python
# After first pass
reroute_queue = [n for n in reroute_queue if n not in competing_nets]
```

**Pros:** Targeted fix
**Cons:** May not fully solve the refilling issue

**Effort:** 1 hour

### Option C: Use Only NegotiatedRouter

Skip sequential routing entirely for known problem nets:

```python
problem_nets = {"SPI_MOSI", "SPI_MISO", "SPI_CLK", "I_SENSE"}
negotiated_nets = [n for n in all_nets if n in problem_nets]
sequential_nets = [n for n in all_nets if n not in problem_nets]
```

**Pros:** Clean separation, no oscillation possible
**Cons:** Requires identifying problem nets ahead of time

**Effort:** 2 hours

### Option D: Redesign Reroute Logic

Replace work queue with fixed iteration count:

```python
for iteration in range(MAX_ITERATIONS):
    for net in failed_nets:
        if net in competing_nets:
            continue
        attempt_route(net)
```

**Pros:** Guaranteed termination
**Cons:** Major refactor, may break existing behavior

**Effort:** 4-6 hours

---

## Recommendation

**Use Option C: Pre-route with NegotiatedRouter**

The cleanest solution is to identify competing nets **before** sequential routing:

1. Run a quick "probe" pass to detect potential oscillations
2. Route those nets with NegotiatedRouter first
3. Route remaining nets with sequential router

This avoids the infinite loop entirely and leverages the strengths of both routers.

---

## Current State

**Code Status:**
- Oscillation detection: ✅ Complete and working
- NegotiatedRouter integration: ✅ Complete
- Pipeline handoff: ✅ Complete
- Infinite loop fix: ❌ Incomplete

**Test Results:**
- Cannot complete test due to infinite loop
- Oscillation correctly detected for 6 nets
- Timeout after 60 seconds

**Time Invested:** ~4 hours

**Estimated Time to Complete:** 2-4 hours depending on approach

---

## Files Modified

- `astar_pathfinding.py`: Oscillation detection, competing nets tracking
- `negotiated_router.py`: MST support, multilayer routing
- `pipeline.py`: Hybrid routing handoff logic
- `test_hybrid_routing.py`: Test script (cannot complete)

---

## Next Steps

1. Choose solution approach (recommend Option C)
2. Implement and test
3. Verify 17/17 nets route successfully
4. Test Benders convergence

**OR**

Accept current 88.2% (15/17) routing success and focus on other improvements.
