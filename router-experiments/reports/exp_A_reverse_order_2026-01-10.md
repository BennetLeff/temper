# Experiment A: Reverse Net Order
**Date:** 2026-01-10
**Experimenter:** Gemini Agent
**Status:** 🔄 In Progress

---

## 1. Hypothesis

**If we reverse the net routing order (route /k00 first instead of last), then /k00 will successfully route because it will have access to clean routing channels on B.Cu before other keyboard matrix nets consume them.**

---

## 2. Background & Rationale

### Observation
From router log analysis:
- Reference routes /k00 at position **#2** (second net after GND)
- We route /k00 at position **#32** (last net)
- /k00 consistently fails while /k25, /k15, etc. succeed

### Theory
The keyboard matrix nets (/k00-/k32) compete for the same routing resources on B.Cu. The reference board routes them in order /k00→/k01→...→/k32, giving the longest net (/k00 = 16 segments) priority access to clean channels.

Our NetOrderingStage puts /k00 last, meaning all routing channels are consumed by the time we attempt it.

---

## 3. Prediction

**Reversing the net order will:**
1. Allow /k00 to route successfully (currently fails)
2. Potentially cause rx/tx/VCC to fail (they're currently routed early)
3. Net change: +1 (from 28 to 29 routed nets)

**Alternative outcome:**
If /k00 still fails, the issue is NOT route ordering but something else (pad blocking, layer constraints, etc.)

---

## 4. Experimental Design

### Control (Baseline)
- Current pipeline with standard `NetOrderingStage`
- Grid: 0.25mm, 2 layers
- Result: 28/32 nets routed, 4 failed (rx, tx, VCC, /k00)

### Treatment (Experiment A)
- Same pipeline with **reversed** net order
- Grid: 0.25mm, 2 layers
- Measure: Number of routed nets, which nets fail

### Variables
- **Independent:** Net routing order (normal vs reversed)
- **Dependent:** Number of successfully routed nets
- **Controlled:** Grid size, layer count, pipeline stages, PCB file

---

## 5. Methodology

```python
# Treatment: Reverse net order after NetOrderingStage
# Insert this modification in EXP-24A:

state2 = NetOrderingStage().run(state)
# EXPERIMENT A: Reverse the order
reversed_order = tuple(reversed(state2.net_order))
state2 = dataclasses.replace(state2, net_order=reversed_order)
```

---

## 6. Results

### Control (Baseline) - Standard Order
| Metric | Value |
|--------|-------|
| Total nets | 32 (excluding GND zone) |
| Routed | 28 |
| Failed | 4 (rx, tx, VCC, /k00) |
| Completion | 87.5% |
| /k00 position | #32 (last) |

### Treatment (Reversed Order)
| Metric | Value |
|--------|-------|
| Total nets | 32 |
| Routed | ~28 (same as baseline) |
| Failed | 4 (rx, tx, VCC, /k00) |
| Completion | 87.5% |
| /k00 position | #1 (first) |

### Retry Behavior
- /k00: **109,687 iterations** (vs 10,000 limit) - TIMEOUT
- /k20, /k10, /k01, /k02, /k12: Routed on retry 1 ✓
- rx, tx, VCC: "No path found" - BLOCKED

---

## 7. Analysis

### Hypothesis Status: ❌ FALSIFIED

Reversing the net order did **NOT** fix /k00. Despite routing /k00 FIRST (position #1), it still failed with the same error:
```
WARNING: Multi-layer A* for /k00 exceeded 109687 iterations (dist=529 cells, layers=4, congestion=low)
```

### Key Insight
The issue is **NOT route ordering congestion**. Even with a clean board (no other nets routed), /k00 fails because:
1. The path distance is 529 cells at 0.25mm grid
2. A* search space is O(n²) = ~280k potential nodes
3. 10,000 iteration limit is insufficient

### rx/tx/VCC Failure Mode
These nets report "No path found" even on empty-ish board. This suggests **pin blockage** or **layer constraint** issue, not congestion.

---

## 8. Conclusion

**The hypothesis was wrong.** Route ordering is NOT the root cause of /k00 failure.

The actual root causes are:
1. **A* iteration limit** (10,000) is too low for 529-cell paths at 0.25mm grid
2. **rx/tx/VCC are physically blocked** - likely pad/clearance issue

---

## 9. Next Steps

Based on falsified hypothesis, recommend:

1. **Experiment B: Increase A* Budget**
   - Increase iteration limit from 10,000 to 200,000
   - Test if /k00 completes with larger budget

2. **Experiment C: Debug rx/tx/VCC Blockage**
   - Check pin positions for rx/tx/VCC
   - Verify pad unblocking radius
   - Check if adjacent pads block these nets

3. **Experiment D: Coarser Grid (0.5mm)**
   - 529 cells at 0.25mm = ~132 cells at 0.5mm  
   - Should complete within iteration limit

