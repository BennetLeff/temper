# Ideation: Sidecar Feedback Loop Convergence

**Date:** 2026-06-28
**Topic:** sidecar-feedback-convergence
**Focus:** Resolve oscillation and convergence risk in the placement↔routing feedback loop
**Mode:** repo-grounded

## Grounding Context

The feedback loop skeleton exists (`pipeline/feedback.py:147`, `pipeline/iterative_placer.py`, `pipeline/orchestrator.py` with `max_iterations=5`, `routability_threshold=0.85`) but has unresolved TODOs at `pipeline/feedback.py:129,132` (actual coordinate shifts not implemented).

The `RoutingFeedbackLoss` class (`feedback.py:31`) takes a `CongestionHeatmap` from routing, applies Gaussian blur (`sigma=2.0`), and uses bilinear interpolation via JAX `map_coordinates` to compute a smooth cost field that repels components from congested areas. The heatmap is a static per-iteration snapshot.

The convergence risk: if the bottleneck report overstates congestion in an area, the placer over-corrects (moves components too far), opening space the router doesn't need. The next routing pass sees a completely different congestion pattern → the placer corrects in the opposite direction → oscillation instead of convergence.

## Topic Axes

1. Noise reduction in the bottleneck signal
2. Damping and step-size control in placer response
3. Convergence detection and termination
4. Signal richness — what the router tells the placer
5. Architectural — making the sidecar a contract

## Ranked Ideas

### 1. Momentum-damped congestion loss with iteration-decaying weight

**Description:** Replace the raw congestion heatmap with an exponentially weighted moving average (EWMA) across iterations. The placer's congestion loss term is `alpha * current_congestion + (1-alpha) * historical_congestion`. On iteration 0, alpha=1.0 (no damping). Each subsequent iteration decays alpha geometrically so the placer makes smaller corrections as it approaches convergence, preventing overshoot-oscillation cycles.

**Axis:** Damping and step-size control

**Basis:** `direct:` `feedback.py:31-89` — current `RoutingFeedbackLoss` uses raw per-iteration heatmap with no iteration memory. `reasoned:` momentum damping is the canonical solution to optimization oscillation in gradient-based systems (SGD with momentum, Adam optimizer, PID controllers). The placement optimizer (JAX gradient descent) already benefits from momentum-like behavior — the congestion loss should match by carrying history rather than reacting to single-iteration snapshots.

**Why it matters:** Single-iteration congestion snapshots are noisy by design — the heatmap is a discretized grid of whether a given cell had routing demand. Two iterations that produce similar-but-not-identical routes will produce different hot-spots even when the placement is improving. EWMA smooths the noise without losing the signal that a region is persistently congested.

**Confidence:** 85%
**Complexity:** Low (~30 LOC in `RoutingFeedbackLoss`)

---

### 2. Convergence halt on routability monotonicity

**Description:** Track whether `routable_nets / total_nets` has improved in the last 2 iterations. If the ratio hasn't improved and is above the threshold, stop early — the loop has converged. If the ratio regressed (got worse), stop with a diagnostic: the feedback loop is oscillating. This avoids the current fixed `max_iterations=5` behavior that wastes cycles on converged solutions and damages solutions that oscillate.

**Axis:** Convergence detection and termination

**Basis:** `direct:` `pipeline/convergence.py:143` — current termination is only `iteration >= max_iterations`. `reasoned:` early-stopping is standard in iterative optimization (validation loss plateau detection in ML training, congestion negotiation iteration caps in PathFinder/VPR). The routability ratio is a cheap, directly-meaningful signal that doesn't require a separate validation step.

**Why it matters:** The worst outcome of a noisy feedback loop isn't failure to converge — it's that the loop damages a good placement. If iteration 2 produces 18/24 routed and iteration 3 produces 16/24, continuing is harmful. Early termination on regression prevents the loop from being worse than single-pass.

**Confidence:** 90%
**Complexity:** Low (~20 LOC in `run_feedback_loop`)

---

### 3. Per-net-class bottleneck categories instead of uniform heatmap

**Description:** Replace the single congestion heatmap with per-net-class heatmaps (HV, LV, Signal, Power). The placer's loss function applies different weights: HV congestion costs 3× more than signal congestion, because an HV net failing to route is a hard failure while a signal net failing may be tolerable. This gives the placer non-uniform guidance — "move this component because it's blocking a high-voltage trace" carries more weight than "move it because a signal net is slightly congested."

**Axis:** Signal richness

**Basis:** `direct:` `routing/net_ordering.py:33-53` — `NetClass` enum already classifies HV=0, Power=2, Signal=4 by priority. `reasoned:` the current heatmap treats all net classes uniformly, so the placer can't distinguish between "this area is congested with critical HV nets" and "this area has room for signal nets but they chose a specific path." Per-class weighting makes the bottleneck report a richer signal.

**Why it matters:** The 33% completion wall exists specifically because HV nets with 6mm clearance requirements can't route through congested areas. A uniform heatmap tells the placer "this area is crowded" but doesn't tell it *which nets are stuck*. Per-class heatmaps say "this area is crowded with HV nets that physically can't route elsewhere" — a much stronger signal.

**Confidence:** 80%
**Complexity:** Medium (~80 LOC: per-class heatmap generation + weighted loss)

---

### 4. Diff-based modified-region feedback (only re-place components near bottlenecks)

**Description:** Instead of applying the congestion loss to all components (which can cause global placement drift), compute the spatial diff between consecutive bottleneck reports: only components whose bounding boxes overlap *new* or *growing* bottleneck regions receive the congestion gradient. Components in areas that improved or were never congested stay put. This prevents the feedback loop from perturbing stable regions.

**Axis:** Noise reduction

**Basis:** `direct:` `pipeline/feedback.py:58-89` — current loss applies to all positions uniformly. `reasoned:` the per-stage DRC fence plan's R5 (incremental scoping) established that only *modified regions* need re-checking. The same principle applies to placement adjustments: only components near *changing* bottlenecks should move. Global re-placement introduces noise that masks the signal from actually-congested areas.

**Why it matters:** A feedback loop that moves every component every iteration is actively destabilizing. If iterations 2-5 all move the ESP32 by 0.2mm because the heatmap has some congestion in that quadrant that's unrelated to that component, the loop adds noise with no benefit. Spatial scoping to modified-bottleneck regions makes the feedback targeted.

**Confidence:** 75%
**Complexity:** Medium (~60 LOC: spatial diff + masked loss)

---

### 5. Asymmetric loss: penalize bottleneck violation more steeply than reward clearance

**Description:** The current congestion loss is symmetric — moving toward a bottleneck costs the same as moving away from a bottleneck. Use an asymmetric loss function: entering a bottleneck region costs heavily (e.g., quadratic penalty), staying in one costs moderately, and leaving one costs nothing (no reward gradient, only penalty removal). This prevents the "rebound" effect where the placer overshoots past the bottleneck boundary because the clearing gradient pulls components past the optimal position.

**Axis:** Damping and step-size control

**Basis:** `reasoned:` asymmetric loss functions (Huber loss, quantile loss) are standard in robust statistics and control theory when you want to penalize one direction more than the other. In this case, the risk is overshoot: the optimizer should avoid entering bottlenecks but doesn't need to maximize distance from them — once clear, further movement adds no value and may create new bottlenecks elsewhere.

**Why it matters:** Symmetric loss creates a "slingshot" effect — the gradient away from a bottleneck pulls hard when a component is near it, but the gradient doesn't vanish once the component is clear. The component keeps moving past the minimum-useful-distance, potentially entering a different bottleneck on the other side.

**Confidence:** 75%
**Complexity:** Low-Medium (~40 LOC: custom asymmetric loss function)

---

### 6. Stage-declared bottleneck_report as a mandatory pipeline contract

**Description:** Formalize `bottleneck_report.json` as a required Stage output (not optional enrichment), using the existing `Stage` protocol pattern (`declared_writes`/`declared_reads`). After routing, the router MUST write a `bottleneck_report.json` sidecar; the placer MUST consume it on the next iteration. This makes the sidecar a first-class pipeline artifact — the system can't silently ignore routing feedback.

**Axis:** Architectural

**Basis:** `direct:` `pipeline/feedback.py:129,132` — existing TODOs where adjustments should be applied but aren't. `direct:` `deterministic/stages/base.py` — Stage protocol with `name` and `run()` already exists; adding `declared_writes`/`declared_reads` contract fields completes the sidecar pattern. The Stage protocol pattern is documented in `docs/brainstorms/2026-06-22-unified-stage-protocol-requirements.md`.

**Why it matters:** The current feedback loop is optional — no pipeline stage declares that it needs bottleneck data, no stage declares that it produces it. Making it a contract means the pipeline runner enforces the handoff: if the router stage didn't write `bottleneck_report`, the placer stage fails with a clear error rather than silently running without feedback.

**Confidence:** 85%
**Complexity:** Medium (~100 LOC: Stage protocol extension + pipeline runner enforcement)

---

### 7. Adaptive iteration budget: spend more iterations on nets that failed last time

**Description:** When a net failed to route in the previous iteration, allocate it more A* iterations in the current pass. Conversely, nets that successfully routed with low iteration counts get fewer. This doesn't change the feedback loop's *placement* behavior — it changes the *router's* behavior to give previously-failed nets more compute, making the bottleneck report more accurate. A net that failed because of insufficient search budget (not an actual obstruction) won't produce a false bottleneck report.

**Axis:** Noise reduction

**Basis:** `direct:` `router_v6/astar_pathfinding.py` — iteration budgets are currently uniform. `direct:` `routing/iteration_budget.py` — `IterationBudget` class already exists with `MIN_ITERATIONS` and adaptive logic. `reasoned:` a false bottleneck report from a net that failed due to budget rather than geometry is pure noise — the placer moves components in response to a problem that doesn't exist. Adaptive budgets reduce Type I errors in the bottleneck report, making it a more trustworthy signal.

**Confidence:** 80%
**Complexity:** Low-Medium (~40 LOC: per-net budget tracking + next-iteration allocation)

---

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|----------------|
| 8 | Run multiple stochastic routing passes and use consensus heatmap | High cost (N× routing time per iteration). The better solution is to make one pass more accurate (Idea #7), not average noise |
| 9 | PID controller for placement corrections | Over-engineered. The JAX optimizer already handles gradient-step sizing; momentum damping (Idea #1) achieves the same effect with far less complexity |
| 10 | Monte Carlo placement perturbations to test bottleneck robustness | Too expensive. The placement optimizer is JAX-based and can't easily sample perturbations mid-optimization without restructuring the pipeline |
| 11 | Human-in-the-loop bottleneck review | Scope mismatch. The pipeline is designed for automated CI/closure testing; human review adds latency incompatible with CI gates |
| 12 | Replace JAX placement with learned bottleneck predictor | Research project. Requires training data that doesn't exist and adds a neural network dependency to a deterministic pipeline |
| 13 | Route all nets simultaneously (PathFinder negotiation) | Already rejected in the sequential-routing ideation. Duplicates the feedback loop's intent with a new algorithm rather than improving the loop |
| 14 | Pre-route critical nets, then place around them | Architectural inversion. The pipeline flow is place→route; reversing it is a 2-week refactor with unproven value |
| 15 | Bottleneck heatmap with uncertainty quantification (per-cell variance) | Interesting but high complexity. Requires multiple routing samples to estimate variance. Deferred behind simpler noise-reduction approaches |

---

Composed 2026-06-28 by ce-ideate from codebase grounding against the feedback loop infrastructure in `pipeline/feedback.py` and `pipeline/convergence.py`.
