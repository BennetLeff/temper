#!/bin/bash
# R-D1 Pre-Implementation Spike: Verify BottleneckMap data path
set +e

echo "=== R-D1 Spike: BottleneckMap Data Path Verification ==="
echo

echo "Step 1: Search for bottleneck_analysis read sites in deterministic pipeline"
rg -n "bottleneck_analysis" packages/temper-placer/src/temper_placer/deterministic/ 2>&1
if [ $? -ne 0 ]; then
  echo "  -> No read sites in deterministic pipeline"
fi
echo

echo "Step 2: Search for cell-grid BottleneckMap concept (cell_size_mm, width, height, origin, scores)"
rg -n "cell_size_mm.*width.*height.*origin.*scores" packages/temper-placer/src/ 2>&1 | head -10
echo

echo "Step 3: Check BottleneckAnalysis dataclass structure"
rg -n "@dataclass" packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py -A 5
echo

echo "Step 4: Check for placement.channels.json sidecar pattern"
rg -n "placement\.channels\.json|sidecar" packages/ 2>&1 | head -10
echo

echo "Step 5: Check if deterministic pipeline populates bottleneck_analysis"
rg -n "bottleneck_analysis=" packages/temper-placer/src/temper_placer/deterministic/ 2>&1 | head -10
echo

echo "Step 6: Check test fixture for temper board"
rg -n "temper" packages/temper-placer/tests/integration/test_closure_canonical_boards.py 2>&1 | head -5
ls packages/temper-placer/tests/integration/test_closure_canonical_boards.py 2>&1
echo

echo "=== Step 0 Summary ==="
echo "  - BoardState.bottleneck_analysis field EXISTS (line 60 of state.py)"
echo "  - But the type is BottleneckAnalysis (per-layer), NOT BottleneckMap (per-cell grid)"
echo "  - BottleneckAnalysis has bottlenecks (per-layer), total_capacity, total_demand - no cell grid"
echo "  - No placement.channels.json sidecar in code"
echo "  - The deterministic pipeline (pipeline.py) does NOT populate bottleneck_analysis"
echo "  - BottleneckAnalysisStage only runs in Router V6 path"
echo
echo "NO-GO: BottleneckMap (per-cell grid) is not reachable from any current code path."
echo "       BottleneckAnalysis exists but is a per-layer analysis, not a per-cell grid."
echo "       Filter will silently disable on this board; SC1 unmeasurable."
echo
echo "Per instructions: extending scope to wire the missing data."
