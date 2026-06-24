# Memory Token Cost Experiment: Findings

**Epic:** temper-8k1  
**Date:** 2025-12-19  
**Status:** Complete (historical — gpbm tool was removed on 2026-06-23; see plan 2026-06-23-010)

## Executive Summary

The GPBM GATHER phase injects semantic memories into AI agent context. We measured token costs and tested optimization strategies. **Key finding: The current design is efficient (~940 tokens) and well under target (1500). No aggressive optimization needed.**

## Background

### Problem Statement
We hypothesized that injecting Eco memories into GATHER context might be expensive in terms of tokens. The question was whether chunking or summarization would be worthwhile.

### Critical Discovery
Before measuring, we discovered that **GATHER was searching empty namespaces**:
- AGENTS.md instructed agents to use `temper-agent` as userId
- eco_client.py searched `temper-shared`, `temper-architect`, etc.
- All 106+ memories lived under `temper-agent`

**Fix:** Added `LEGACY` namespace to EcoConfig and updated all search methods.

## Methodology

### Test Cases
5 representative GATHER queries across domains:

| Goal | Domain | Role |
|------|--------|------|
| Implement thermal protection | firmware | architect |
| Optimize placement heuristics | placer | coder |
| Add unit tests for state machine | firmware | tester |
| Design gate driver circuit | pcb | architect |
| Fix PID oscillation | firmware | coder |

### Variants Tested

| Variant | min_score | limit | Description |
|---------|-----------|-------|-------------|
| A (Baseline) | 0.6 | 5 | Current defaults |
| B (Aggressive) | 0.8 | 3 | High threshold, low limit |
| C (Intermediate) | 0.7 | 5 | Moderate threshold |
| D (Limit Only) | 0.6 | 3 | Reduce limit, keep threshold |

## Results

### Baseline (Variant A)

| Goal | Tokens | Memories |
|------|--------|----------|
| Implement thermal protection | 920 | 5 |
| Optimize placement heuristics | 1183 | 5 |
| Add unit tests for state machine | 976 | 5 |
| Design gate driver circuit | 930 | 5 |
| Fix PID oscillation | 699 | 5 |
| **Average** | **942** | **5** |

**Observation:** Already well under 1500 token target!

### Score Distribution Analysis

Sample query "Implement thermal protection":

| Namespace | Scores |
|-----------|--------|
| legacy (temper-agent) | 0.81, 0.80, 0.79, 0.79, 0.78 |
| shared | - (empty) |
| role/domain | - (empty) |

All scores clustered in 0.78-0.81 range. Raising threshold to 0.8 would eliminate 60% of memories.

### Variant Comparison

| Variant | Avg Tokens | Avg Memories | Queries with 0 Mems | Token Reduction |
|---------|------------|--------------|---------------------|-----------------|
| A (Baseline) | 942 | 5.0 | 0/5 | - |
| B (0.8/3) | 638 | 0.8 | 3/5 | -32% |
| C (0.7/5) | 942 | 5.0 | 0/5 | 0% |
| D (0.6/3) | 769 | 3.0 | 0/5 | -18% |

### Key Insights

1. **Baseline is already efficient**: 942 tokens average is well under 1500 target
2. **Aggressive filtering breaks functionality**: Variant B (0.8 threshold) returns 0 memories 60% of the time
3. **Limit reduction is safer than score thresholds**: Variant D maintains 100% query coverage
4. **Memory sizes are reasonable**: Current 300-char truncation in markdown is effective

## Token Budget Breakdown

Current GATHER output composition:

| Component | Estimated Tokens |
|-----------|-----------------|
| Eco memories (5 @ ~60 tokens each) | 300 |
| Requirements table (2-5 rows) | 100-200 |
| Issues list (10 items) | 200-300 |
| Files list (12 items) | 50-100 |
| Headers/formatting | 200 |
| **Total** | **850-1100** |

## Recommendations

### Immediate: Keep Current Defaults

The baseline (min_score=0.6, limit=5) is efficient and functional:
- Average 942 tokens (37% under target)
- Maximum 1183 tokens (21% under target)
- 100% of queries return relevant memories

**No changes to defaults needed.**

### Optional: Use Environment Variables for Tuning

The implemented `ECO_MIN_SCORE` and `ECO_LIMIT` environment variables allow per-session tuning if needed:

```bash
# For token-constrained sessions
ECO_LIMIT=3 bd-gather "goal" domain role

# For exhaustive context gathering
ECO_LIMIT=10 bd-gather "goal" domain role
```

### Future Considerations (Not Needed Now)

These optimizations are **not recommended** at current scale:

1. **Summarization**: Would add latency and complexity for ~200 token savings
2. **Chunking**: Would lose context coherence with minimal benefit
3. **Memory type filtering**: Could exclude ISSUE/BEADS mirrors, but they often contain useful context

### When to Revisit

Re-evaluate if:
- Memory database grows significantly (>500 memories)
- Memory content sizes increase (>1000 chars avg)
- GATHER output regularly exceeds 1500 tokens
- New token-constrained deployment targets emerge

## Implementation Summary

### Changes Made

1. **eco_client.py**
   - Added `LEGACY: str = "temper-agent"` to EcoConfig
   - Updated `search_comprehensive()` to include legacy namespace
   - Added `--no-legacy` CLI flag

2. **gather.py**
   - Added `ECO_MIN_SCORE` and `ECO_LIMIT` environment variables
   - Updated `_search_eco()` to use configurable thresholds
   - Added `eco_legacy` to GatherContext

3. **METRICS.md**
   - Added "Eco Memory Metrics" section
   - Defined eco_gather_tokens, eco_memories_returned, eco_avg_memory_chars, eco_min_score

### Files Modified
- `tools/gpbm/eco_client.py`
- `tools/gpbm/gather.py`
- `metrics/METRICS.md`

## Conclusion

**The hypothesis that memory injection is expensive was not supported by data.** The current GATHER phase is efficient at ~940 tokens, well under the 1500 token target. The main fix needed was discovering and resolving the namespace mismatch that prevented memories from being found at all.

The implemented environment variables provide flexibility for future tuning without code changes. Chunking and summarization are not warranted at current scale.
