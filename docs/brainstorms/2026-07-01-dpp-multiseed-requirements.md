---
date: 2026-07-01
topic: dpp-diversified-multiseed-with-cheap-eval-gate
focus: Determinantal Point Process seed diversification with fixed-budget triage evaluation to replace single-seed brittle placement optimization
origin: feature request
status: draft
actors: placement optimizer developer, CI system, closure test pipeline, retry loop
---

# Requirements: DPP-Diversified Multi-Seed with Cheap-Eval Gate

## Problem Frame

Placement optimization currently runs from a single seed: one spectral or random initialization, followed by a full 5-phase curriculum (`config.py:375-473`, ~8000 epochs, ~30+ min). This is brittle. A bad seed produces a bad placement with no recovery. The seed quality depends on the spectral embedding's hyperparameters (`normalized_laplacian`, `margin_fraction` in `initialization.py:203-225`), zone-avoidance parameters (`ZoneAwareConfig` in `config.py:159-177`), and random perturbation magnitude — none of which are searched or diversified today.

The existing `train_parallel` (`train.py:1134-1197`) runs 4 seeds with incrementing seed values but uses the same initialization method for all. It selects the best result by `best_loss` after full optimization and computes a `confidence_score` — but it runs every seed through the full cost before deciding. This is wasteful when most seeds will be discarded.

The proposed approach diversifies seeds across initialization hyperparameters, applies a Determinanatal Point Process (DPP) to select a maximally-diverse subset, evaluates only that subset through a cheap triage pass, and promotes the single best seed to full optimization.

The efficiency gain (not running full optimization on all seeds) comes from the triage gate, not the DPP. The DPP's value is purely in seed DIVERSITY — it selects seeds that span distinct regions of the cost landscape, increasing the probability that at least one seed starts near a good local minimum. The triage gate provides the cost savings; the DPP provides the quality insurance. Both are necessary: triage without DPP is random selection; DPP without triage requires full optimization of all selected seeds.

## Actors

- **A1. Placement optimizer developer** — implements DPP selection, triage evaluator, and multi-seed entry point; tunes diversity and cost-function knobs
- **A2. CI system** — runs unit tests for DPP kernel, triage correlation test, and existing closure tests
- **A3. Closure test pipeline** — measures end-to-end `routing_completion_pct`, HPWL, DRC errors on canonical boards; validates that multi-seed quality >= single-seed
- **A4. CLI user** — invokes placement with `--multi-seed` flag; sees DPP selection summary and triage scores

## Key Decisions

- **K1. DPP operates on seed-dissimilarity, not seed-likelihood.** A DPP is defined by a kernel matrix L where `L[i,j]` measures similarity. The DPP probability of selecting subset S is proportional to `det(L_S)`, favoring diverse sets. We construct L from seed-pair distances; a quality term can optionally down-weight low-quality seeds. (Kulesza & Taskar, 2012.)

- **K2. Seed generation varies spectral initialization hyperparameters, not just PRNG seeds.** Today `train_parallel` only varies `config.seed + i` (line `train.py:1165`). We instead sample from a cartesian product of:
  - `normalized_laplacian` ∈ {True, False}
  - `spectral_margin` ∈ {0.05, 0.10, 0.20}
  - `method` ∈ {"spectral", "zone_aware_spectral", "random"}
  - Random perturbation `sigma` ∈ {0.0, 0.02, 0.05, 0.10} (fraction of board size)
  - This yields up to 2 × 3 × 3 × 4 = 72 seeds; we cap at 50 for practical purposes

- **K3. DPP similarity kernel candidates:**
  - **Position-distance kernel**: `K(i,j) = exp(-||x_i - x_j||^2 / (2σ²))` where `x_i` is a flat vector of all component positions from seed i. Simple, works well when similar component layouts → similar optima. Risk: two seeds with different absolute positions but isomorphic relative structure may score as "similar" only after alignment.
  - **Constraint-violation fingerprint kernel**: For each seed, compute a fixed set of cheap-to-evaluate metrics (overlap count, boundary violations, zone intrusions). Fingerprint vector `f_i` ∈ R^d. `K(i,j) = exp(-||f_i - f_j||² / (2σ²))`. Directly measures what matters for optimization but may miss layout-level diversity.
  - **Spectral embedding-space kernel**: For each seed, use the spectral coordinates in the Laplacian eigenspace (before board scaling). `K(i,j) = cosine_similarity(e_i, e_j)` where `e_i` is the (N × k) eigenvector matrix. Captures fundamental graph-structural similarity.

  Recommendation: start with position-distance kernel for simplicity, validate against spectral kernel, and add constraint-violation fingerprint as a quality term (not similarity term).

- **K4. Triage evaluation is a fixed-budget (30 iterations) run on a subset of the full loss stack.** Evaluated losses: `wirelength` + `overlap` + `boundary` + `clearance`. This lightweight cost is JIT-compiled and runs ~50× faster than full optimization. The selection criterion is lowest triage loss; the winning seed proceeds to `train_multiphase`.

- **K5. Integration point: new `train_dpp_multiseed` function in `train.py`** that orchestrates:
  1. Generate seed pool (`_generate_diverse_seeds`)
  2. Build DPP kernel matrix from position embeddings (`_dpp_kernel_from_positions`)
  3. Select k=3..5 seeds via greedy DPP MAP inference (`_dpp_select`)
  4. Run triage evaluation on each selected seed (`_triage_evaluate`)
  5. Promote best triage seed to `train_multiphase` for full optimization
  6. Return `ParallelTrainingResult` with DPP diagnostics appended

- **K6. No change to `train_multiphase` or the 5-phase curriculum.** The DPP selection and triage are a new outer orchestration layer. Existing single-seed entry points (`train`, `train_multiphase`, `train_parallel`) remain unchanged.

- **K7. DPP subset size k is configurable, default 4.** A larger k increases triage compute cost linearly but improves diversity coverage. 3-5 balances cost vs. benefit for ~30 min full optimization runs.

- **Terminology:** `n_generate`: number of seed candidates to produce. `n_valid`: number of seeds that pass all filters and enter the DPP selection pool. `n_select`: number of seeds promoted to triage evaluation.

## Requirements

**Implementation tiers:** P0 (Core — must ship for approach to work): R1-R5 (seed generation, DPP selection, triage evaluation, promotion). P1 (Integration): R6 (orchestration), R8 (tests). P2 (Polish): R7 (config knobs — expose only n_generate and n_select initially, add remaining 7 after validation), R9 (structured logging — implement after core path is validated).

### R1. Seed Pool Generation

Status: required

A function `_generate_diverse_seeds(netlist, board, config, n_generate=50) -> list[tuple[Array, dict]]` generates a pool of initial positions by varying initialization hyperparameters.

- Sample from the cartesian product described in K2
- Each seed is a tuple of `(positions: (N,2) Array, metadata: dict)` where metadata records the hyperparameters used
- If `n_generate` is smaller than the cartesian product size, randomly subsample without replacement
- Seeds that produce degenerate positions (all NaN, all identical) are discarded and replaced
- `random` method seeds use different PRNG keys; `spectral`/`zone_aware_spectral` are deterministic given hyperparameters → perturbed with additive Gaussian noise (sigma from hyperparameter grid)

### R2. DPP Kernel Construction

Status: required

A function `_dpp_kernel_from_positions(seeds: list[tuple[Array, dict]]) -> Array` builds an (n × n) similarity matrix.

- Each seed's positions are flattened to a vector `x_i ∈ R^(N×2)`
- Pairwise distance: `d(i,j) = RMS(x_i - x_j)` where RMS is the root mean square (RMS) of component-wise position differences
- Kernel: `L[i,j] = exp(-d(i,j)² / (2σ²))` where σ is set to the median pairwise RMS distance

The kernel similarity is computed on POSITION-SORTED component vectors. Before computing the RMS of flat position vectors, components are sorted by their stable reference ID to ensure identical ordering across seeds. This makes the shuffle test (R2c) meaningful — a shuffled order should produce kernel value 1.0 only if the sorted representations are identical.

- Unit test (R2a): kernel is symmetric, positive entries
- Unit test (R2b): two identical seeds produce kernel value ≈ 1.0
- Unit test (R2c): a seed and its randomly-shuffled copy (same positions) produce kernel value ≈ 1.0

### R3. DPP Subset Selection

Status: required

A function `_dpp_select(L: Array, k: int, quality: Array | None = None) -> list[int]` selects k seed indices via greedy DPP MAP inference.

- If quality vector `q` is provided, use quality-diversity decomposition: `L_ij = q_i * S_ij * q_j` where `S` is the similarity matrix. If not provided, `q_i = 1` for all i (pure diversity).
- Greedy algorithm: O(n·k³) with incremental Cholesky updates (implementation detail deferred to planning). A naive implementation using full determinant computation is O(n·k⁴), which is still fast for the target range of n=50, k=5.
- Unit test (R3a): with identity kernel and equal quality, selection is arbitrary but deterministic
- Unit test (R3b): with block-diagonal kernel (two clusters), selected seeds include members from both clusters. The cluster test uses a synthetic seed pool with two known clusters of sizes [n₁, n₂] where n₁ ≥ 1 and n₂ ≥ 1, and both n₁, n₂ ≥ n_select - 1 (ensuring DPP can select from either cluster). With n_select = 3, use cluster sizes [3, 4] — DPP naturally selects at least 1 from each cluster. With n_select = 2, use cluster sizes [2, 2].
- Unit test (R3c): with k=1 and a quality vector, the highest-quality seed is selected
- **Kernel ill-conditioning fallback:** If the DPP kernel matrix has a condition number exceeding 10⁶ (near-singular, making DPP selection numerically undefined), fall back to farthest-point sampling in the original seed embedding space as a diversity proxy. Log the condition number and fallback decision. Farthest-point sampling provides a well-defined, numerically stable diversity selection without requiring kernel inversion.

### R4. Triage Evaluation

Status: required

A function `_triage_evaluate(positions, netlist, board, context, n_iters=30) -> float` runs a short optimization and returns the final loss.

- Loss stack: `wirelength` (weight 1.0) + `overlap` (weight 1.0) + `boundary` (weight 1.0) + `clearance` (weight 1.0). All 4 loss terms use weight 1.0 in the triage CompositeLoss. This provides equal gradient contribution from each term. The weights are NOT configurable in v1 (see Implementation Tiers P2 for config knob exposure).
- Uses `create_value_and_grad_fn_with_breakdown` with a minimal `CompositeLoss`
- Fixed learning rate 0.05, no annealing, no Gumbel-Softmax (rotations locked to default orientation)
- 30 iterations is ~1 second on most boards (JIT-compiled step)
- Returns the final loss value (lower is better)
- Unit test (R4a): triage converges monotonically (loss non-increasing over 30 iters)
- Unit test (R4b): triage produces finite, realistic loss values (not NaN, not Inf)
- If any seed's triage evaluation produces NaN loss (indicating numerical instability in the reduced loss stack), that seed is discarded and replaced via the degenerate seed replacement mechanism (R1). If more than 20% of seeds produce NaN triage loss, abort triage evaluation with a hard error — this indicates a systemic issue with the loss stack configuration rather than unlucky seed generation.

### R5. Triage ↔ Full Optimization Correlation Validation

Status: required

A validation test to ensure the triage cost correlates with final optimization quality.

- Run 20 seeds through both triage (30 iters) and full optimization (`train_multiphase` with `fast_test` config)
- Compute Spearman rank correlation ρ between triage loss and full-optimization loss
- **Success criterion:** ρ ≥ 0.5 (moderate positive correlation)
- If ρ < 0.5, the triage loss stack is insufficient and must be extended (add `congestion` or `thermal`) — log a warning and investigate before shipping
- This is a one-time validation, not a per-run check

### R6. Orchestration Entry Point

Status: required

A function `train_dpp_multiseed(netlist, board, context, config, n_generate=50, n_select=4, n_triage_iters=30) -> ParallelTrainingResult` in `train.py`.

- Calls R1 → R2 → R3 → R4 → `train_multiphase`
- Logs DPP diagnostics at INFO level: seed counts (generated / DPP-selected / triaged), kernel condition number, selected seed IDs and hyperparameters
- Returns `ParallelTrainingResult` with `all_results` containing only the triaged seeds' results (not the full seed pool)
- Must be callable as a drop-in replacement for `train_multiphase` — same return type, same side effects
- If n_generate < n_select, log warning and fall back to selecting all seeds (no DPP filtering)

### R7. Configuration Knobs

Status: required

New fields on `OptimizerConfig` or a new `MultiSeedConfig` dataclass:

- `multi_seed.enabled: bool = False` — master switch; when False, single-seed behavior is unchanged
- `multi_seed.n_generate: int = 50` — total seeds to generate. If set above 50, silently capped to 50 with a log message: 'n_generate capped from {requested} to 50 (maximum).' If set below `n_select`, raised to `n_select` with a log message: 'n_generate raised from {requested} to {n_select} (minimum to satisfy n_select).'
- `multi_seed.n_select: int = 4` — DPP subset size
- `multi_seed.n_triage_iters: int = 30` — triage evaluation iterations
- `multi_seed.dpp_quality_enabled: bool = False` — whether to use constraint-violation quality scores in DPP
- `multi_seed.init_methods: list[str] = ["spectral", "zone_aware_spectral", "random"]` — which init methods to include
- `multi_seed.laplacian_options: list[bool] = [True, False]` — normalized/unormalized Laplacian options
- `multi_seed.margin_options: list[float] = [0.05, 0.10, 0.20]` — spectral margin fraction options
- `multi_seed.perturb_sigmas: list[float] = [0.0, 0.02, 0.05, 0.10]` — random perturbation magnitudes

The initial implementation exposes only `n_generate` and `n_select`. The remaining 7 configuration parameters (`init_methods`, `laplacian_options`, `margin_options`, `perturb_sigmas`, `triage_iterations`, `triage_loss_weights`, `dpp_quality_weight`) are hardcoded with reasonable defaults based on empirical tuning. They are exposed via config only after the core DPP + triage path is validated (see Implementation Tiers P2).

### R8. Unit and Property Tests

Status: required

- **R8a.** `test_dpp_kernel_symmetric` — kernel matrix is symmetric and has positive entries
- **R8b.** `test_dpp_kernel_identical_seeds` — two identical position arrays yield kernel value ≈ 1.0
- **R8c.** `test_dpp_select_maximizes_diversity` — on a synthetic 5-seed pool with 2 tight clusters, DPP selects at least one from each cluster
- **R8d.** `test_dpp_select_respects_k` — selected subset has exactly k elements
- **R8e.** `test_triage_evaluate_monotonic` — loss decreases or stays flat over 30 iterations
- **R8f.** `test_triage_correlation` — Spearman ρ ≥ 0.5 on a 20-seed sample (R5). This test runs in the integration/validation tier, not the CI unit test suite. It is gated on a `--long` flag or equivalent and runs on a schedule (nightly) rather than per-commit. The CI unit test suite includes a fast-path variant that runs 3 seeds × 10 iterations to verify the pipeline executes without error, but does not validate correlation quality.
- **R8g.** `test_generate_diverse_seeds_bounds` — all generated seeds have positions within board bounds, no NaNs
- **R8h.** `test_dpp_multiseed_fallback` — when `n_valid < n_select` (degenerate pool after filtering), falls back to `random_init()` without error. (Contrast with R6's parameter guard: when `n_generate < n_select`, fall back to selecting all generated seeds without DPP filtering.)
- **R8i.** `test_dpp_multiseed_disabled` — when `multi_seed.enabled=False`, behaves identically to single-seed `train_multiphase`

### R9. Observability

Status: required

Emit structured log lines at INFO level:

- `event="dpp_seed_gen"`, `n_requested`, `n_generated`, `n_degenerate` (discarded due to NaN/identical), `elapsed_ms`
- `event="dpp_selection"`, `n_input`, `n_selected`, `kernel_condition_number`, `selected_indices`, `selected_hyperparams` (summary string)
- `event="dpp_triage"`, `n_seeds`, `n_iters`, `scores` (list of {seed_id, triage_loss}), `best_seed_id`, `best_triage_loss`, `elapsed_ms`

(P2 tier — implemented after core DPP + triage path is validated. The core path requires only a single structured log event: 'seed_promoted' with seed_id and triage_loss.)

## Success Criteria

- **SC1.** Mean full-optimization loss (HPWL + constraints) from DPP multi-seed ≤ mean loss from 4-seed `train_parallel` on the temper board (10 runs each, one-sided t-test, α=0.05)
- **SC1b (DPP vs random selection):** Run the same 50-seed triage pipeline with random subset selection (k seeds chosen uniformly without DPP) instead of DPP-based selection. DPP-selected seeds must show measurably lower variance in final placement quality (wirelength, constraint violations) at p < 0.05 on at least 2/3 regression corpus boards. This gates the DPP infrastructure cost on a proven diversity benefit over simple random selection.
- **SC2.** DPP multi-seed wall time ≤ 1.5× single-seed wall time (DPP overhead + triage + 1 full optimization ≤ 1.5 × 1 full optimization). The 1.5× bound permits up to 15 min overhead on a 30 min run.
- **SC3.** Triage Spearman ρ ≥ 0.5 vs. full optimization (R5 validated on temper board and 2 canonical boards)
- **SC4.** The DPP-selected seed SHALL produce a final placement whose wirelength is within 5% of the best single-seed result from the same random key, on at least 90% of runs across the regression corpus. (Absolute 'never worse' guarantees are incompatible with non-deterministic optimization; this criterion provides a statistical bound.)
- **SC5.** Kernel construction and DPP selection together add ≤ 5 seconds CPU time for n=50 seeds on the temper board (~100 components)
- **SC6.** All unit tests (R8a-i) pass in CI; no regression on existing placement tests

## Dependencies

- `packages/temper-placer/src/temper_placer/optimizer/train.py:191-205` — `ParallelTrainingResult` dataclass (return type, already supports multi-seed aggregation)
- `packages/temper-placer/src/temper_placer/optimizer/train.py:1134-1197` — `train_parallel` (reference pattern for multi-seed orchestration; DPP multi-seed replaces/augments this)
- `packages/temper-placer/src/temper_placer/optimizer/train.py:1207` — `train_multiphase` (final-stage optimizer entry point)
- `packages/temper-placer/src/temper_placer/optimizer/initialization.py:203-650` — `SpectralInitializer` (seed diversity through `normalized_laplacian`, `margin_fraction`)
- `packages/temper-placer/src/temper_placer/optimizer/zone_aware_init.py` — `ZoneAwareSpectralInitializer` (seed diversity through zone-avoidance parameters)
- `packages/temper-placer/src/temper_placer/optimizer/config.py:180-198` — `InitializationConfig` (init method selection)
- `packages/temper-placer/src/temper_placer/optimizer/config.py:142-177` — `ForceDirectedConfig`, `ZoneAwareConfig` (additional seed diversity levers)
- `packages/temper-placer/src/temper_placer/optimizer/config.py:271-505` — `OptimizerConfig` (new multi-seed fields)
- `packages/temper-placer/src/temper_placer/losses/base.py` — `CompositeLoss`, `LossContext`, `create_value_and_grad_fn_with_breakdown` (used by triage)
- `packages/temper-placer/src/temper_placer/losses/wirelength.py` — wirelength loss (primary triage metric)
- `packages/temper-placer/src/temper_placer/losses/overlap.py` — overlap loss (triage constraint)
- `packages/temper-placer/src/temper_placer/losses/boundary.py` — boundary loss (triage constraint)
- `packages/temper-placer/src/temper_placer/losses/clearance.py` — clearance loss (triage constraint)
- `packages/temper-placer/src/temper_placer/cli/__init__.py:812-814` — CLI entry point that calls `train_parallel`; update for `--multi-seed` flag
- `docs/brainstorms/2026-06-23-seed-filtering-requirements.md` — complementary seed-filtering approach (bottleneck-map-based); DPP multi-seed is orthogonal and composable with this

## Out of Scope

- **GPU-accelerated DPP or batched DPP selection.** For n=50, k=5, the O(n·k³) greedy algorithm on CPU is fast enough. GPU DPP is premature optimization.
- **Online DPP adaptation.** DPP kernel is constructed once from the initial seed pool. Adapting it mid-optimization based on intermediate results is a separate research project.
- **Per-seed JAX JIT parallelization.** Each triage evaluation and full optimization runs sequentially. True parallel execution (pmap/vmap across seeds) is deferred to a follow-up.
- **Alternative diversification methods (k-means clustering, farthest-point sampling, MMD-critic).** DPP is the chosen method. If DPP proves insufficient, these alternatives can be evaluated in a follow-up.
- **Dynamic triage budget allocation.** Triage always runs 30 iterations per seed. Adaptive stopping (stop triage if a seed is clearly losing) is out of scope.
- **Seed quality model (learned predictor of final quality from seed positions).** K2 uses a flat quality vector; a learned quality model is deferred.
- **Modifying the 5-phase curriculum or individual loss functions.** This document only adds an outer orchestration layer.

## Assumptions

1. **DPP greedy MAP inference is implementable in pure numpy/JAX without new dependencies.** The `det(L_S)` computation uses `jnp.linalg.slogdet`. No new Python packages needed.
2. **Position-distance is a reasonable proxy for optimization-path similarity.** Two seeds with similar component layouts tend to converge to similar optima. If this assumption fails (e.g., small position differences amplify into large optimization-path divergence), R5's correlation test will catch it.
3. **30 triage iterations are enough for the cost function to separate good seeds from bad.** This depends on the loss landscape smoothness. If triage loss is too noisy after 30 iters, increase to 50 iters (configurable via `n_triage_iters`).
4. **The existing `CompositeLoss` and `LossContext` are usable as-is for triage.** Triage uses a subset of the full loss stack; all required losses (wirelength, overlap, boundary, clearance) already exist and are JIT-compatible.
5. **Seed generation hyperparameter ranges cover meaningful diversity.** The Laplacian normalization choice, margin fraction, and zone-awareness toggle are the primary levers for seed diversity. If empirical results show insufficient diversity, R1's parameter grid can be extended without architectural changes.

6. **Prerequisite: Triage loss stack feasibility.** Before implementing DPP seed selection, verify that `CompositeLoss` can be instantiated with a minimal subset of loss terms (wirelength, overlap, boundary, clearance only — excluding Gumbel-Softmax-dependent and annealing-coupled losses). The subset must: (a) JIT-compile without errors, (b) complete 30 gradient steps in under 500ms for a 40-component board on reference hardware, and (c) produce gradient fields that move components toward feasible positions (not toward NaN or zero-gradient dead zones). If the minimal CompositeLoss cannot be constructed or JIT-compiled, the triage gate must use an alternative cheap evaluation metric (e.g., static constraint-violation scoring without gradient steps).
7. **JAX random seeding is deterministic and reproducible.** PRNG keys are recorded in seed metadata and the full seed generation can be replayed from a master seed. JAX PRNG determinism is guaranteed within the same JAX version and platform. Cross-platform variation (CPU vs GPU, different JAX versions) may produce divergent seeds. The determinism test (R8i) pins both the JAX version and platform in CI; cross-platform reproducibility is explicitly out of scope.

## Risks

### Risk 1: DPP kernel design does not capture meaningful diversity

**Severity:** Medium. **Likelihood:** Low-Medium.

If the position-distance kernel treats structurally-different seeds as similar, DPP selection devolves to random sampling — no worse than `train_parallel` with random seeds, but no better.

**Mitigation:** Start with position-distance kernel; validate against spectral-embedding kernel (R2's alternate kernel). If position-distance proves inadequate, switch to spectral kernel (which captures graph-structural diversity). The DPP selection API (R3) is kernel-agnostic — only `_dpp_kernel_from_positions` changes.

### Risk 2: Triage cost does not correlate with final optimization quality

**Severity:** High. **Likelihood:** Medium.

If triage loss (wirelength + overlap + boundary + clearance over 30 iters) does not rank seeds in the same order as full 5-phase optimization, the gate promotes the wrong seed. This is the central risk of the proposal.

**Mitigation:** R5 mandates a Spearman ρ ≥ 0.5 validation gate before merging. If ρ falls below threshold, extend triage stack (add `congestion`, `thermal_spread`, `zone` losses; increase iterations to 50). The triage stack is configurable, so this can be tuned per-board if needed.

### Risk 3: Compute overhead exceeds benefit

**Severity:** Low. **Likelihood:** Low.

DPP kernel (n=50, O(n²) = 2500 pairwise comparisons at ~100 comps each = ~250K operations) is negligible. Greedy DPP (O(50·5³) = ~6250 determant computations) is also negligible. Triage runs 4 × 30 iterations at ~0.03 sec/iter ≈ 3.6 seconds. The 1 full optimization takes ~30 minutes. Total overhead: <1% of one full run.

**Mitigation:** SC2 caps total wall time at 1.5× single-seed. If profiling shows unexpected bottlenecks (e.g., JIT compilation time per triage seed), cache the compiled triage step across seeds. JIT compilation is triggered once per unique input shape. For the triage gate, all seeds share the same component count (same netlist), so JIT compilation occurs exactly once regardless of seed count. The compiled function is reused across all triage evaluations. Shape-triggered recompilation is not a concern in the single-netlist, multi-seed use case.

### Risk 4: DPP quality-diversity decomposition is hard to tune

**Severity:** Low. **Likelihood:** Medium.

When `dpp_quality_enabled=True`, the quality vector must be calibrated. A bad quality vector can override diversity and select only "safe" (low-quality) seeds.

**Mitigation:** Default to `dpp_quality_enabled=False` (pure diversity DPP). Only enable quality after R5 correlation is validated and a calibrated quality function (e.g., normalized constraint-violation score) is available. This is a configuration knob, not a hardcoded path.

### Risk 5: Degenerate seed pool

**Severity:** Medium. **Likelihood:** Low-Medium.

If the seed generation step produces too few valid seeds (e.g., due to overly aggressive seed filtering or numerical issues in spectral embedding), the pipeline must handle degenerate pool sizes gracefully.

**Fallback:** If after seed generation, fewer than `n_select` valid seeds remain (degenerate pool), and the regeneration retry limit is exhausted: fall back to a purely random seed from `PlacementState.random_init()` and log a structured warning with the degenerate pool size and the specific filter that caused rejection. If zero seeds survive generation, abort with a hard error rather than silently producing a random placement — zero surviving seeds indicates a systemic issue (e.g., all spectral embeddings produce invalid positions, or the seed filter threshold is misconfigured).

## Unknowns

- **What similarity metric best captures placement-seed diversity?** Position Euclidean distance is the simplest but may miss graph-structural similarity. Spectral embedding-space distance (K3 option 3) is theoretically better grounded but requires storing (N × k) eigenvector matrices per seed. Empirical validation needed.

- **How many triage iterations are needed for reliable ranking?** 30 is a conservative estimate based on 8000-epoch full optimization. The Spearman correlation plateaus at some iteration count — determining where the plateau occurs requires R5 validation.

- **Does DPP pure-diversity selection (without quality term) outperform quality-weighted DPP?** When seeds are generated from the same hyperparameter distribution, pure diversity may suffice. If some init methods consistently produce worse seeds, quality weighting helps. Unknown without empirical data.

- **How does DPP multi-seed compose with bottleneck-map seed filtering?** The existing seed-filtering brainstorm (`2026-06-23-seed-filtering-requirements.md`) pre-filters seeds against a bottleneck congestion map. DPP diversification operates on filtered candidates. The composition order (filter then DPP, or DPP then filter) affects diversity. This is a planning-time decision.
