# Router V6 Plan: Critical Analysis

This document applies four critique methods to stress-test the V6 Topological Architecture plan before implementation.

---

## 1. Pre-Mortem Analysis

> *"It is July 2026. We implemented Router V6 exactly as planned. It failed catastrophically. Here's why."*

### The Autopsy Report

**Project Duration:** 6 months (January - July 2026)
**Outcome:** Abandoned. Reverted to manual routing with KiCad.
**Completion Rate at Abandonment:** 45% on test suite (worse than V5's estimated 60%)

### Primary Cause of Death: The Topology Abstraction Was Wrong

We built an elaborate channel-based topology model, but **PCB routing doesn't actually decompose into clean channels**.

The Voronoi-based channel extraction worked beautifully on the Piantor keyboard (regular grid of switches) but completely failed on the Temper board because:

1. **Components aren't points.** A 20mm x 15mm IGBT module isn't a Voronoi site - it's a region. The "channels" between large components were computed from centroids, missing the actual routing bottlenecks at component edges.

2. **Channels aren't independent.** We modeled channels as having fixed capacity, but in reality, a net using Channel A affects available capacity in adjacent Channel B due to clearance halos. The SAT solver said "satisfiable" but geometric realization failed because clearance interactions weren't modeled.

3. **Pin escape isn't channel routing.** 60% of routing difficulty is escaping from dense pin fields (QFN, BGA). Channels are irrelevant here - you need dog-bone fanout patterns. We built the wrong abstraction.

### Secondary Cause: Test Suite Selection Bias

We chose test boards that were **too similar to Piantor**:
- Arduino Uno: Regular 0.1" headers, simple 2-layer
- Adafruit Feather: Dense but symmetric layout
- LibreSolar MPPT: Power electronics but with generous spacing

None of these had:
- Mixed fine-pitch (0.5mm) and coarse-pitch (2.54mm) on the same board
- High-voltage isolation requirements (3mm+ clearance)
- Asymmetric component clustering

When we finally ran on real Temper board, all the "validated" code failed.

### Tertiary Cause: Over-Engineering the Diagnostics

We spent 8 weeks building the `RoutingDiagnostics` system with beautiful JSON reports and actionable suggestions. But:

1. **The suggestions were wrong.** "Move C12 south 2mm" was geometrically impossible due to board edge. The suggestion generator didn't know about board constraints.

2. **The feedback loop diverged.** Placement adjustments based on routing feedback created new bottlenecks. After 10 iterations, the board was worse than the starting point.

3. **We optimized for explainability over correctness.** Beautiful failure reports don't ship products.

### The Assumption That Killed Us

> "Topology can be solved independently from geometry, then geometry is easy."

**This was false.** In PCB routing, topology and geometry are deeply coupled:
- Via placement affects topology (which layer transitions are possible)
- But via placement is geometric (must avoid pads, meet drill rules)
- You can't assign "via at location X" without knowing if X is valid
- But you can't know if X is valid without knowing the topology

We built a two-phase system for a fundamentally single-phase problem.

### What We Should Have Done

1. **Started with the hardest board first** (Temper), not the easiest (Piantor)
2. **Built incremental improvements to V5** instead of architectural rewrite
3. **Focused on the 80/20**: escape routing and crossing detection would have given 80% of the benefit with 20% of the complexity
4. **Shipped something** instead of planning for 3 months

---

## 2. Red Team Review

> *Persona: Senior Principal Engineer, 25 years experience, infamous for killing projects in design review*

### BLOCKING CONCERNS - Must Address Before Approval

#### BC-1: No Working Prototype Validates the Core Thesis

**Concern:** The entire plan rests on "topological routing can be separated from geometric routing." This is a research hypothesis, not an engineering fact.

**Evidence of Risk:**
- No citation of production autorouters using this architecture
- Prior art section lists academic papers from 1971-2000 - nothing modern
- Industrial tools (Cadence, Altium) are closed-source; we don't know their architecture

**Required Action:** Build a minimal prototype (1 week max) that demonstrates topology→geometry separation on ONE net before committing to full architecture.

#### BC-2: SAT Solver Performance is Hand-Waved

**Concern:** Section 3.2 says "SAT solver may be slow for large boards" and proposes "use greedy solver as primary." This is architectural capitulation disguised as mitigation.

**Evidence of Risk:**
- If SAT is too slow, we lose the "unsatisfiability proof" benefit - the core value proposition
- Greedy solver doesn't provide proofs
- No performance benchmarks on expected problem size

**Required Action:** Before proceeding, model the constraint count for Temper board:
- ~80 nets × ~10 channels = 800 assignment variables
- Channel capacity constraints: ~50
- Crossing constraints: O(n²) = ~6400

Run a benchmark SAT instance of this size. If solve time > 10 seconds, the architecture is non-viable.

#### BC-3: Channel Extraction Algorithm is Undefined

**Concern:** Section 3.1 says "Build Voronoi diagram of component centroids." This is a one-sentence description of a critical algorithm.

**Questions unanswered:**
- How do you handle components that aren't point-like?
- How do you handle overlapping component bounding boxes?
- How do you handle board edges and cutouts?
- How do you handle zones that block routing?
- What's the computational complexity?

**Required Action:** Write pseudocode for channel extraction. Identify at least 3 edge cases. Demonstrate on Temper board schematically before implementation.

#### BC-4: Placement Feedback Loop Has No Convergence Guarantee

**Concern:** Section 3.5 shows a loop: route → feedback → adjust placement → route. No termination condition except iteration limit.

**Evidence of Risk:**
- V5 documentation says "placement adjustments based on routing created new bottlenecks"
- No damping factor or step size limit
- No proof that feedback improves placement

**Required Action:** Define mathematically:
1. What metric decreases each iteration? (Loss function)
2. What's the step size / learning rate?
3. What's the convergence criterion?
4. What happens if it oscillates?

#### BC-5: Test Suite is Inadequate for Power Electronics

**Concern:** Proposed test suite has 1 power electronics board (LibreSolar MPPT). Temper is power electronics. This is 17% coverage of the target domain.

**Required Action:** Add at least 2 more power electronics boards:
- One with high-voltage isolation (>1kV)
- One with high-current traces (>10A)
- Ideally one with thermal management constraints

### ADVISORY CONCERNS - Should Address

#### AC-1: 12-Week Timeline is Aggressive

Phase 3 (Topological Router) is allocated 4 weeks for:
- Constraint model definition
- Greedy solver
- SAT solver integration
- Testing

This is a research project masquerading as engineering. Estimate should be 8-12 weeks with 50% probability of success.

#### AC-2: No Rollback Plan

If V6 fails at week 8, what's the fallback? V5 code will have diverged. Consider:
- Feature branch with regular V5 sync
- Defined decision points for go/no-go
- Minimum viable V6 that ships before full vision

#### AC-3: Team of One

This plan assumes a single developer. PCB autorouting is a PhD-level problem. Consider:
- Partnering with academic research group
- Using existing open-source router as baseline (FreeRouting)
- Hiring contractor with autorouter experience

### VERDICT: Conditional Approval

Approve for **Phase 1 only** (test suite + diagnostics).

Before Phase 2, demonstrate:
1. Channel extraction on Temper board (manual inspection of output)
2. SAT solver benchmark on realistic problem size
3. At least one more power electronics test board

---

## 3. Steel-Man the Alternative

### Solution A (Current Plan): Topological-First Architecture
Build channel analysis → SAT-based topology solver → geometric realization pipeline.

### Solution B: Incremental V5 Improvement
Don't rewrite. Fix the three identified root causes in V5 directly.

#### Solution B Design

**Phase 1: Same-Layer Crossing Detection (Root Cause #1)**
- Add `LineSegment.intersects()` to cost function
- ~50 lines of code change
- Expected: 33% violation reduction

**Phase 2: Net-Aware Clearance (Root Cause #2)**
- Inflate blocking radius by `clearance_matrix.get_clearance(net_a, net_b)`
- ~200 lines of code change
- Expected: 19% violation reduction

**Phase 3: Multi-Layer Retry Logic (from Failed Net Analysis)**
- When routing fails on layer L1, explicitly retry on L2, L3, L4
- ~100 lines of code change
- Expected: +30% completion on Temper

**Phase 4: Escape Routing for Dense Pins**
- Pre-compute dog-bone fanout for QFN/BGA pads
- Route escape vias before main routing
- ~300 lines of code change
- Expected: Handle the 60% of failures at pin escape

**Total: ~650 lines of targeted fixes vs ~3000+ lines of new architecture**

#### Trade-offs Where Solution B is Superior

| Dimension | Solution A (Topology) | Solution B (Incremental) |
|-----------|----------------------|--------------------------|
| **Time to first improvement** | 8+ weeks | 1-2 weeks |
| **Risk of total failure** | High (unproven architecture) | Low (known codebase) |
| **Code reuse** | ~30% of V5 | ~95% of V5 |
| **Debugging difficulty** | New abstractions to learn | Familiar code paths |
| **Reversibility** | Hard to rollback | Easy to revert individual fixes |
| **Validation** | Need new test infrastructure | Existing benchmarks work |

#### Trade-offs Where Solution A is Superior

| Dimension | Solution A (Topology) | Solution B (Incremental) |
|-----------|----------------------|--------------------------|
| **Theoretical ceiling** | Could achieve 100% | Limited by A* exploration |
| **Explainability** | Structured proofs | Still "it failed" |
| **Placement feedback** | Architectural support | Bolted-on heuristics |
| **Long-term maintainability** | Clean separation | Accumulated patches |

#### Cost-Benefit Analysis

**Solution B Expected Outcome:**
- Completion: 21% → ~60-70% (based on root cause analysis)
- Timeline: 4-6 weeks
- Risk: Low
- Ceiling: ~80% (some boards fundamentally need placement changes)

**Solution A Expected Outcome:**
- Completion: 21% → 80%+ (if it works)
- Timeline: 12-16 weeks (realistic)
- Risk: High (50% chance of architectural failure)
- Ceiling: ~95% (with placement co-optimization)

**Expected Value Calculation:**

Solution B: 0.9 × 70% + 0.1 × 21% = **65.1% expected completion**

Solution A: 0.5 × 85% + 0.5 × 21% = **53% expected completion**

**Under expected value, Solution B is superior.**

#### Revised Recommendation

**Hybrid Approach:**
1. Implement Solution B first (Phases 1-4) - 6 weeks
2. Measure completion rate on full test suite
3. If <80%, THEN implement Solution A topology layer on top of improved V5
4. Solution A becomes an optional "topology hint" layer, not a rewrite

This gives:
- Fast wins from Solution B
- Option value on Solution A
- Lower risk of total failure

---

## 4. Confidence Score Analysis

### Initial Rating: 6/10

### Criteria Preventing a 10:

#### Gap 1: No Prototype Validation (Cost: -1.5 points)
The plan proposes a novel architecture without evidence it works. A 10/10 plan would include:
- A minimal working prototype demonstrating the core thesis
- Performance benchmarks on representative problem sizes
- At least one end-to-end success story

#### Gap 2: Underspecified Algorithms (Cost: -1.0 points)
Several critical components are described at "what" level, not "how":
- Channel extraction: "Voronoi diagram" is insufficient
- SAT encoding: No formula provided
- Placement feedback: No convergence analysis

A 10/10 plan would have pseudocode for each algorithm.

#### Gap 3: Inadequate Test Suite (Cost: -0.5 points)
Test suite has 1/6 power electronics boards for a power electronics project. Survivorship bias risk.

#### Gap 4: No Decision Points (Cost: -0.5 points)
Plan is "implement all phases" with no go/no-go gates. A 10/10 plan would have:
- "If Phase 1 benchmark shows <X, abort"
- "If SAT solve time >Y seconds, switch to greedy-only"
- Clear criteria for when to cut losses

#### Gap 5: Timeline Optimism (Cost: -0.5 points)
12-week timeline for research-grade work by single developer. Realistic estimate is 16-24 weeks.

### Rewritten Plan Elements to Raise Score

#### Addition 1: Prototype Gate (Week 2)

Before any infrastructure, build a **throwaway prototype** that:
1. Takes ONE net from Temper board
2. Manually defines 3-4 channels it could use
3. Encodes as SAT problem
4. Solves and prints assignment
5. Verifies geometric realization is possible

**Go/No-Go:** If prototype takes >1 week or fails, STOP and implement Solution B instead.

#### Addition 2: Algorithm Specifications

**Channel Extraction Pseudocode:**
```
function extract_channels(board, components):
    # Step 1: Create obstacle map
    obstacles = []
    for comp in components:
        obstacles.append(comp.bounding_box.inflate(clearance))
    for zone in board.zones:
        obstacles.append(zone.polygon)

    # Step 2: Compute routing regions (complement of obstacles)
    routing_space = board.outline.difference(union(obstacles))

    # Step 3: Skeletonize routing space to get channel centerlines
    skeleton = medial_axis(routing_space)

    # Step 4: Convert skeleton edges to channels
    channels = []
    for edge in skeleton.edges:
        width = min_distance_to_boundary(edge)
        capacity = floor(width / (trace_width + clearance))
        channels.append(Channel(edge, width, capacity))

    # Step 5: Connect channels at junctions
    return ChannelGraph(channels)
```

**SAT Encoding:**
```
Variables:
  uses[net_id, channel_id]: bool  # Net n uses channel c
  layer[net_id]: int {0,1,2,3}    # Layer assignment

Constraints:
  # Capacity: sum of nets using channel ≤ capacity
  for c in channels:
    sum(uses[n,c] * width[n] for n in nets) <= capacity[c]

  # Connectivity: net must have path from source to sink
  for n in nets:
    connected(source[n], sink[n], {c : uses[n,c]})

  # Crossing: same-channel same-layer nets need ordering
  for (n1, n2) in pairs where exists c: uses[n1,c] AND uses[n2,c]:
    (layer[n1] != layer[n2]) OR (order[n1,n2] is defined)
```

#### Addition 3: Decision Points

| Milestone | Metric | Go | No-Go Action |
|-----------|--------|-----|--------------|
| Week 2: Prototype | Single-net topology→geometry works | Continue | Implement Solution B |
| Week 4: Channel extraction | Temper channels look reasonable (manual review) | Continue | Revisit algorithm |
| Week 6: SAT performance | Temper-scale problem solves in <30s | Continue | Switch to greedy-only |
| Week 8: Phase 2 complete | Channel analysis improves diagnostics | Continue | Cut scope to diagnostics only |
| Week 12: Phase 3 complete | Test suite score > V5 baseline | Continue | Rollback, ship V5 + fixes |

#### Addition 4: Expanded Test Suite

Add to test suite:
- **VESC 6** (Benjamin Vedder): Motor controller, high-current, open source
- **LibreSolar BMS 8S50**: Battery management, multiple voltage domains
- **GreatScott SMPS**: Switch-mode power supply, isolation requirements

New suite composition:
- 2 digital (Piantor, Arduino)
- 1 mixed (Feather)
- 3 power electronics (MPPT, VESC, BMS)

### Revised Rating: 7.5/10

**Remaining gaps for 10/10:**
- Still no actual prototype (would need to build it, not just plan it)
- Academic prior art is dated; modern autorouter architectures unknown
- Single-developer risk not fully mitigated

**Acceptable for proceeding** with the understanding that this is research-grade work with meaningful failure probability.

---

## Summary of Required Plan Changes

### Must-Have (Blocking)

1. **Add Week 2 Prototype Gate** - prove topology separation works before building infrastructure
2. **Add Algorithm Pseudocode** - channel extraction and SAT encoding must be specified
3. **Add Decision Points** - explicit go/no-go criteria at weeks 2, 4, 6, 8, 12
4. **Expand Test Suite** - add 2+ power electronics boards

### Should-Have (Advisory)

5. **Consider Hybrid Approach** - implement Solution B first, Solution A as enhancement
6. **Extend Timeline** - 16-20 weeks realistic, not 12
7. **Define Rollback Plan** - what ships if V6 fails?

### Nice-to-Have

8. **Seek External Review** - academic advisor or industry consultant
9. **Prototype on Hardest Board First** - Temper, not Piantor
10. **Build Convergence Analysis** - prove feedback loop terminates

---

## Appendix: Updated Risk Register

| Risk | Likelihood | Impact | Mitigation | Residual Risk |
|------|------------|--------|------------|---------------|
| Topology/geometry separation doesn't work | Medium (40%) | Critical | Week 2 prototype gate | Low (10%) |
| SAT solver too slow | Medium (30%) | High | Week 6 performance gate; greedy fallback | Medium (20%) |
| Channel extraction fails on complex boards | Medium (35%) | High | Medial axis algorithm; manual review gate | Medium (15%) |
| Test suite doesn't represent target domain | High (50%) | Medium | Add 2+ power boards | Low (10%) |
| Placement feedback diverges | Medium (30%) | Medium | Convergence analysis; damping | Medium (20%) |
| Timeline overrun | High (60%) | Medium | Buffer 4 weeks; scope cuts defined | Medium (30%) |
| Total project failure | Medium (25%) | Critical | Solution B fallback ready | Low (10%) |

**Overall Project Risk: Medium-High**
**Recommended Approach: Proceed with gates and fallback plan**
