---
title: "Pattern: DPP-Diversified Multi-Seed Initialization with Triage Gating"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "Gradient-based optimizers are sensitive to initial conditions and single-seed runs exhibit high variance in final cost"
  - "A pool of candidate initial placements can be generated cheaply through hyperparameter variation but full optimization per seed is too expensive"
  - "Maximally-diverse seed selection matters more than exhaustive evaluation — you need to cover distinct regions of the solution landscape"
  - "A cheap proxy (triage) correlates with full optimization quality well enough to serve as a promotion gate"
tags:
  - dpp-diversification
  - determinantal-point-process
  - multi-seed-initialization
  - triage-gating
  - spectral-hyperparameter-variation
  - permutation-invariant-kernel
  - farthest-point-fallback
  - spearman-validation
---
# Pattern: DPP-Diversified Multi-Seed Initialization with Triage Gating

## Context

The Temper placer's gradient-based optimizer is sensitive to initial component
positions — run-to-run variance in final wirelength can exceed 10% depending on
the seed. Running full multi-phase optimization on many seeds is computationally
prohibitive (30-60 seconds per seed on a typical 8-layer board). Naive random
selection from a seed pool wastes budget on nearby, correlated configurations
that explore the same basin.

The pattern needed to:

1. **Generate** a diverse pool of initial placements by varying initialization
   hyperparameters across their cartesian product.
2. **Select** a maximally-diverse subset from that pool, ensuring the chosen
   seeds cover distinct regions of the solution landscape rather than clustering.
3. **Triage-evaluate** the subset with a cheap proxy (30 SGD iterations on a
   reduced loss stack) to estimate relative seed quality.
4. **Promote** only the best seed to full multi-phase optimization, achieving
   variance reduction at the cost of 1 full optimization + K cheap triages.

The risk: naive multi-seed with full optimization on every seed costs O(K)
full-optimization budget; random selection wastes diversity; and a broken
proxy (triage not correlating with full quality) silently promotes suboptimal
seeds.

## Guidance

### 1. Seed Pool Generation via Spectral Hyperparameter Variation

Generate N seeds by sweeping over the cartesian product of initialization
hyperparameters, then randomly subset to `n_generate` (capped at 50). Each seed
is produced by varying:

- **init_method**: `spectral`, `zone_aware_spectral`, `random`
- **normalized_laplacian**: `True`, `False`
- **margin_fraction**: `0.05`, `0.10`, `0.20`
- **perturb_sigma**: `0.0`, `0.02`, `0.05`, `0.10` (Gaussian perturbation scaled
  by board diagonal)

The grid is deterministically shuffled (seed 42) to ensure reproducibility, and
individual seed failures are retried up to `n_generate * 3` times. Post-generation
validation filters seeds with NaN positions, all-identical positions, or
out-of-bounds coordinates.

```python
# seed_generation.py — hyperparameter grid sweep
init_methods = ["spectral", "zone_aware_spectral", "random"]
laplacian_options = [True, False]
margin_options = [0.05, 0.10, 0.20]
perturb_sigmas = [0.0, 0.02, 0.05, 0.10]

grid = [
    (method, laplacian, margin, sigma)
    for method in init_methods
    for laplacian in laplacian_options
    for margin in margin_options
    for sigma in perturb_sigmas
]
_Random(42).shuffle(grid)
```

The grid is a P2 knob — the 7 hyperparameter dimensions (3 methods, 2 laplacian
options, 3 margins, 4 sigmas) are configurable. P0 fixed knobs are `n_generate`
and `n_select`.

### 2. Degenerate Seed Pool Fallbacks

Two fallback levels protect against degenerate seed pools:

- **Insufficient valid seeds** (`len(seeds) < n_select`): fall back to
  `random_init()` to pad the pool up to at least `n_select`. This ensures DPP
  selection always has enough candidates.
- **Zero seeds produced**: raise `RuntimeError` — this indicates a fundamental
  configuration or environment issue that must be diagnosed.

```python
# seed_generation.py — degenerate pool fallback
if len(seeds) < config.n_select:
    logger.warning("Only %d valid seeds (need %d); falling back to random_init().")
    while len(seeds) < max(config.n_select, 1):
        pos = _random_init_positions(netlist, board, key)
        if _is_seed_valid(pos, board):
            seeds.append((pos, {"init_method": "random_fallback"}))
```

### 3. Permutation-Invariant DPP Kernel Construction

DPP requires a similarity kernel over seed pairs. Since component ordering
within a seed is arbitrary (the optimizer only cares about positions, not
assignment order), the kernel must be **permutation-invariant**: swapping two
components within a seed must not change the kernel value.

The solution: sort each seed's component positions by reference ID before
flattening into the kernel vector. Metadata carries `comp_refs` — a list of
component reference identifiers in the same order as the positions rows:

```python
# dpp_selection.py — reference-ID sorted kernel vectors
for positions, md in seeds:
    comp_refs = md.get("comp_refs", None)
    if comp_refs is not None:
        ref_ids = [(r, i) for i, r in enumerate(comp_refs)]
        ref_ids.sort()
        sorted_idx = jnp.array([i for _, i in ref_ids], dtype=jnp.int32)
        positions = positions[sorted_idx]
    vectors.append(positions.ravel())
```

The kernel L is an RBF (radial basis function) over pairwise RMS distances:

```
L[i,j] = exp(-RMS(x_i - x_j)^2 / (2 * sigma^2))
sigma = median(pairwise RMS distances)
```

Using the median as the kernel bandwidth ensures adaptive scaling — the
kernel is neither too concentrated (all similarity values near 1) nor too
spread out (all values near 0), regardless of the absolute scale of
component coordinates.

### 4. DPP Greedy MAP Inference for Subset Selection

Select k seed indices via greedy DPP MAP inference. The DPP probability
P(Y) is proportional to det(L_Y). The greedy algorithm builds Y
incrementally, selecting the seed that maximizes the determinant at each
step.

The algorithm is O(n·k^4) in practice (n ≤ 50 seeds, k ≤ 5), dominated by
the determinant computation at each greedy step:

```python
# dpp_selection.py — greedy DPP MAP inference
selected: list[int] = []
remaining = set(range(n))

for _ in range(k):
    best_idx = -1
    best_det = -float("inf")
    for i in remaining:
        candidate = selected + [i]
        sub_L = L[jnp.array(candidate)][:, jnp.array(candidate)]
        sub_q = q[jnp.array(candidate)]
        Q = jnp.diag(sub_q)
        sub_L_q = Q @ sub_L @ Q
        sign, logdet = jnp.linalg.slogdet(sub_L_q)
        if sign > 0:
            det_val = float(jnp.exp(logdet))
        if det_val > best_det:
            best_det = det_val
            best_idx = i
    selected.append(best_idx)
    remaining.discard(best_idx)
```

An optional quality vector `q` (length n) enables quality-diversity
decomposition: L_ij = q_i * S_ij * q_j. The P0 path uses uniform quality
(`dpp_quality_weight = 0.0`); quality-aware selection with
constraint-violation scores is a P2 knob (`dpp_quality_enabled`).

### 5. Kernel Condition Number Guard with Farthest-Point Fallback

Before running DPP selection, compute the kernel condition number (ratio of
largest to smallest eigenvalue). When the condition number exceeds 10^6,
the kernel is numerically ill-conditioned — eigenvalues near zero create
singularities in the DPP probability that produce degenerate (non-diverse)
selections.

```python
# dpp_selection.py — condition number computation
eigenvalues = jnp.linalg.eigh(L)[0]
lambda_max = eigenvalues[-1]
lambda_min = eigenvalues[0]
condition_number = float(lambda_max / lambda_min) if lambda_min > 0 else float("inf")
```

On ill-conditioned kernels, fall back to **farthest-point sampling**: pick
the first point arbitrarily, then iteratively select the point with maximum
minimum distance to all previously-selected points. This is O(n·k) and
guarantees a diverse selection even when DPP numerics break down.

```python
# dpp_selection.py — farthest-point fallback
if condition_number is not None and condition_number > 1e6:
    logger.info("dpp_selection: kernel condition_number=%s > 1e6, fallback=farthest_point")
    return _farthest_point_sampling(seed_vectors, k)
```

### 6. Triage Evaluation: Cheap 30-Iteration Proxy

Each DPP-selected seed is evaluated through a lightweight triage pass: 30
iterations of simple SGD (no optax, no Gumbel-Softmax) on a reduced
CompositeLoss:

| Loss Term | Weight |
|-----------|--------|
| WirelengthLoss | 1.0 |
| OverlapLoss | 1.0 |
| BoundaryLoss | 1.0 |
| ClearanceLoss | 1.0 |

All weights are fixed at 1.0 — the triage is designed for relative ranking,
not absolute accuracy. The loss functions are the same implementations used
in full optimization, ensuring semantic consistency between triage and full
paths. SGD uses a fixed learning rate of 0.05 with no schedule.

```python
# triage.py — reduced loss stack
loss_terms = [
    WeightedLoss(WirelengthLoss(), weight=1.0),
    WeightedLoss(OverlapLoss(), weight=1.0),
    WeightedLoss(BoundaryLoss(), weight=1.0),
    WeightedLoss(ClearanceLoss(), weight=1.0),
]
composite_loss = CompositeLoss(loss_terms)
```

### 7. NaN Safety: Triage Abort Gate

When more than 20% of triaged seeds produce NaN loss values, the pipeline
raises `RuntimeError` — this indicates a systemic numerical problem
(divergence, gradient explosion) that would corrupt seed ranking:

```python
# train.py — NaN abort gate
if triage_num_nan > len(selected_indices) * 0.2:
    raise RuntimeError(
        f"Triage evaluation aborted: {triage_num_nan}/{len(selected_indices)} "
        f"seeds produced NaN triage loss (>20%)."
    )
```

### 8. Spearman Rank Correlation Validation Gate

Triage is a proxy — it only works if the relative ordering it produces
matches full-optimization quality. A validation gate computes Spearman's ρ
between triage losses and full-optimization losses across a corpus of
seeds, requiring ρ ≥ 0.5:

```python
# test_triage_correlation.py — validation gate
rho, _pval = spearmanr(triage_losses, full_losses)
assert rho >= 0.5, f"Spearman rho ({rho:.3f}) below minimum threshold 0.5"
```

This is a `@pytest.mark.slow` test (30 triage iters per seed, 20 seeds) and
runs in the nightly CI pipeline. The fast-path (3 seeds, 5 iters) verifies
pipeline integrity without asserting the correlation threshold.

### 9. Best-Seed Promotion to Full Optimization

After triage, the seed with the lowest triage loss is promoted. Its
positions seed the initial `PlacementState` for a standard
`train_multiphase()` call:

```python
# train.py — seed promotion
best_positions = seeds[best_seed_idx][0]
initial_state = PlacementState(
    positions=best_positions,
    rotation_logits=jnp.zeros((netlist.n_components, 4)),
)
full_result = train_multiphase(
    netlist, board, loss_factory, context, config,
    initial_state=initial_state,
    callback=callback,
    validation_callback=validation_callback,
)
```

Only 1 full optimization is performed regardless of K — the triage gate
provides cost control by absorbing the exploration cost into cheap proxy
evaluations.

### 10. Pipeline Integration and CLI Flag

The multi-seed pipeline is activated through a `--multi-seed` CLI flag and
returns a `ParallelTrainingResult` (drop-in compatible with
`train_parallel`):

```
optimize --multi-seed --n-generate 50 --n-select 4 --board temper_v1.kicad_pcb
```

When `multi_seed.enabled = False`, the function short-circuits to a direct
`train_multiphase()` call with zero overhead:

```python
# train.py — disabled short-circuit
if not ms_config.enabled:
    result = train_multiphase(netlist, board, loss_factory, context, config)
    return ParallelTrainingResult(best_result=result, ...)
```

### 11. Quality Gate: DPP Outperforms Random K-from-N (SC1b)

A statistical validation gate runs in the nightly A/B pipeline
(`dpp_ab_measurement.py`): DPP selection must outperform random K-from-N
selection on at least 2 of 3 regression corpus boards, measured by final
wirelength variance reduction (F-test, p < 0.05). This gates the claim that
DPP diversity selection provides measurable benefit over naive random
subsampling.

### 12. Config Structure: P0 vs P2 Knobs

The `MultiSeedConfig` dataclass separates knobs by priority tier:

**P0 (fixed, exposed in CLI):**
- `n_generate: int = 50` — seed pool size
- `n_select: int = 4` — DPP subset size promoted to triage

**P2 (configurable, code-level only):**
- `init_methods` — initialization methods in grid
- `laplacian_options` — Laplacian normalization options
- `margin_options` — spectral margin fractions
- `perturb_sigmas` — perturbation sigma magnitudes
- `triage_loss_weights` — per-term triage weights
- `dpp_quality_enabled` — quality-diversity toggle
- `dpp_quality_weight` — quality term weight in DPP kernel

Post-init validation enforces `n_generate ≤ 50`, `n_generate ≥ n_select`,
and `n_select ∈ [2, 10]`.

## Consequences

- **Cost control**: 1 full optimization + K triages (30 iters each) replaces
  K full optimizations. For K=4 with 500-iteration full optimization, this
  cuts seed-exploration cost by ~94%.
- **Variance reduction**: DPP-selected seeds explore distinct basins of the
  solution landscape; farthest-point sampling provides a guaranteed-diverse
  fallback when kernel numerics degrade.
- **Defense in depth**: Three degradation layers — DPP greedy MAP → farthest-point
  sampling → random_init() fallback → RuntimeError abort.
- **32 tests** across 7 test files covering unit (dpp_selection, seed_generation,
  triage, config), integration (A/B comparison, triage correlation), CLI
  (multi-seed flag), and sensitivity (heuristic impact).
- **Statistical gates in CI**: SC1b (DPP outperforms random on 2/3 regression
  corpus boards) and R5 (Spearman ρ ≥ 0.5 validation gate) run in nightly
  pipeline as structural quality guards.
- **Drop-in compatibility**: `ParallelTrainingResult` return type matches
  `train_parallel`, enabling seamless swap in pipeline orchestrators.
