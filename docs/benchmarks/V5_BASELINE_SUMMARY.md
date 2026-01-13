# Router V5 Baseline Results

**Date:** 2026-01-11
**Router:** V5 Sequential Router (bidirectional A*)
**Test Suite:** 4 unrouted boards

---

## Executive Summary

V5 router baseline established on 4 diverse boards:
- **Completion rates:** 71.9% to 94.4%
- **Geometric mean completion:** 83.2%
- **Overall score:** 0.000 (geometric mean penalizes any failures)

**Key Finding:** V5 router achieves 72-94% completion but has complete failures on 5-11 nets per board, causing geometric mean score to drop to zero.

---

## Per-Board Results

### 1. Piantor Right (Digital, 2L)

| Metric | Value |
|--------|-------|
| Total nets | 32 (excluding 1 zone net) |
| Auto-routed | 23 (71.9%) |
| Failed | 9 |
| Runtime | 3.4s |
| Score | 0.000 |

**Failed nets:** rx, tx, VCC, and 6 others
**Analysis:** Lower completion than expected. Original claim was "100% routed by V5" but actual is 71.9%.

### 2. LibreSolar BMS (Power, 4L)

| Metric | Value |
|--------|-------|
| Total nets | 90 (excluding 28 zone nets) |
| Auto-routed | 85 (94.4%) |
| Failed | 5 |
| Runtime | 123.8s |
| Score | 0.000 |

**Analysis:** Best performance - highest completion rate. Complex 4-layer power board.

### 3. RP2040 Design Guide (Mixed, 4L)

| Metric | Value |
|--------|-------|
| Total nets | 53 (excluding 3 zone nets) |
| Auto-routed | 42 (79.2%) |
| Failed | 11 |
| Runtime | 141.4s |
| Score | 0.000 |

**Analysis:** Mixed digital/power, moderate success rate.

### 4. BitAxe Ultra (Mixed, 2L)

| Metric | Value |
|--------|-------|
| Total nets | 55 (excluding 6 zone nets) |
| Auto-routed | 49 (89.1%) |
| Failed | 6 |
| Runtime | 129.7s |
| Score | 0.000 |

**Analysis:** Bitcoin ASIC miner, good completion despite 2-layer constraint.

---

## Aggregate Metrics

**Completion Rates:**
- Minimum: 71.9% (Piantor)
- Maximum: 94.4% (BMS)
- Arithmetic mean: 83.7%
- **Geometric mean: 83.2%**

**Runtime:**
- Total: 398.3s (6.6 minutes)
- Average per board: 99.6s
- Fastest: 3.4s (Piantor - smallest board)
- Slowest: 141.4s (RP2040 - most complex)

**Failure Analysis:**
- Total nets: 230
- Successfully routed: 199 (86.5%)
- Failed: 31 (13.5%)

---

## Scoring Methodology

**Why score is 0.000:**

The geometric mean score goes to zero when ANY net has score 0.0. This is intentional - it creates a strong penalty for complete failures.

```python
# For a board with 10 nets: 9 success (score=1.0), 1 failure (score=0.0)
geometric_mean = (1.0^9 * 0.0^1)^(1/10) = 0.0
```

This scoring emphasizes that **partial routing is as bad as no routing** from a production perspective - you still can't manufacture the board.

**Alternative metric: Completion rate**
- Geometric mean completion: **83.2%**
- This better represents V5's actual capability

---

## Router V6 Target

Per the plan, V6 needs to achieve:
- **80%+ geometric mean AUTO-ROUTED** ✓ (V5 baseline: 83.2%)
- **100% of flagged nets have actionable guidance** (V5: 0% flagged)

**V6 success criteria:**
1. Match or exceed 83.2% completion
2. Provide diagnostic reports for ALL failed nets
3. Generate placement suggestions for failures

---

## Board Complexity Analysis

| Board | Nets | Layers | Complexity | Completion |
|-------|------|--------|------------|------------|
| Piantor | 32 | 2 | Low | 71.9% |
| RP2040 | 53 | 4 | Medium | 79.2% |
| BitAxe | 55 | 2 | Medium | 89.1% |
| BMS | 90 | 4 | High | 94.4% |

**Observation:** More nets doesn't always mean lower completion. BMS has the most nets but highest completion, suggesting good placement quality in the source design.

---

## Known Limitations of V5

Based on prior analysis and these results:

1. **No placement feedback** - fails silently on placement issues
2. **Binary success/failure** - no diagnostic information
3. **No retry strategies** - gives up after max iterations
4. **Same-layer crossings** - not detected, causes DRC violations
5. **No channel awareness** - can create congestion

---

## V6 Improvement Strategy

Based on these baseline results, V6 should focus on:

1. **Diagnostic coverage** - explain WHY each of 31 failed nets failed
2. **Placement suggestions** - actionable feedback for the 13.5% failures
3. **Channel-based routing** - prevent congestion before it happens
4. **Graceful degradation** - flag nets early if unroutable

**Success metric for V6 Phase 1:**
- Diagnostic report for ALL 31 failed nets
- At least 10 actionable placement suggestions

---

## Files

**Benchmark data:** `docs/benchmarks/v5_baseline_full.json`
**Raw log:** `/tmp/v5_baseline.log`

**Command to reproduce:**
```bash
python -m temper_placer.router_v6.benchmark --router v5 --output docs/benchmarks/v5_baseline_full.json
```

---

## Next Steps

1. ✅ V5 baseline established
2. ⏳ Implement channel extraction
3. ⏳ Build V6 topology solver
4. ⏳ Run V6 on same boards and compare

**Target:** V6 should match 83.2% completion + provide diagnostics for 100% of failures.
