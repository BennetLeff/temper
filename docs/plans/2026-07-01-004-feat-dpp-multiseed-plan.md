---
date: 2026-07-01
type: feat
origin: docs/brainstorms/2026-07-01-dpp-multiseed-requirements.md
status: active
---

# Plan: DPP-Diversified Multi-Seed Placement with Triage Gate

## Problem Frame

Placement optimization runs from a single seed: one spectral or random initialization, followed by a full 5-phase curriculum (~8000 epochs, ~30+ min). A bad seed produces a bad placement with no recovery. The existing `train_parallel` (`train.py:1134-1197`) runs 4 seeds with incrementing seed values but uses the same initialization method for all, then runs every seed through the full cost before deciding — wasting compute on seeds destined for discard.

This plan adds a DPP-based seed diversification and triage-gated selection layer **above** the existing `train_multiphase` entry point. The orchestration generates 50 diverse seeds by varying initialization hyperparameters, selects k=4 maximally-diverse seeds via a DPP over position-distance kernels, evaluates them through a 30-iteration triage pass, promotes the best, and runs full 5-phase curriculum. The existing single-seed entry points (`train`, `train_multiphase`, `train_parallel`) remain unchanged.

The efficiency gain comes from the triage gate (30 iterations vs. ~8000). The DPP's value is in seed diversity — selecting seeds that span distinct regions of the cost landscape, increasing the probability that at least one seed starts near a good local minimum.

---

## Implementation Units

### P0 Tier — Core Path (U1–U8)

These units form the minimal viable feature. All must land before the feature can ship.

---

### U1. MultiSeedConfig Dataclass and Config Wiring

**Goal:** Add a `MultiSeedConfig` dataclass to `OptimizerConfig` with the P0-required knobs, exposing only `enabled`, `n_generate`, and `n_select` initially (remaining 7 knobs deferred to U11).

**Requirements:** R7 (P0 subset)

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/config.py` — add `MultiSeedConfig` and wire into `OptimizerConfig`

**Approach:**

```python
@dataclass
class MultiSeedConfig:
    enabled: bool = False
    n_generate: int = 50  # seeds to generate
    n_select: int = 4     # DPP subset size (promoted to triage)
    n_triage_iters: int = 30  # triage evaluation iterations
    dpp_quality_enabled: bool = False

    # Hardcoded defaults (exposed via config in U11):
    #   init_methods = ["spectral", "zone_aware_spectral", "random"]
    #   laplacian_options = [True, False]
    #   margin_options = [0.05, 0.10, 0.20]
    #   perturb_sigmas = [0.0, 0.02, 0.05, 0.10]

    def __post_init__(self):
        _clamp_n_generate(self.n_generate, self.n_select)
```

New field on `OptimizerConfig`:
```python
multi_seed: MultiSeedConfig = field(default_factory=MultiSeedConfig)
```

`__post_init__` validates: `n_generate` silently capped at 50 (log message), raised to `n_select` if below. `n_select` in [2, 10].

**Test scenarios:**
- `test_default_disabled`: `MultiSeedConfig()` has `enabled=False`
- `test_n_generate_capped`: `n_generate=100` → 50 with log message
- `test_n_generate_raised`: `n_generate=2`, `n_select=4` → `n_generate` raised to 4
- `test_n_select_range`: `n_select=1` or `n_select=11` raises `ValueError`

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_config.py -v`

---

### U2. Seed Pool Generation (`_generate_diverse_seeds`)

**Goal:** Generate a diverse pool of n_generate initial positions by varying initialization hyperparameters (K2 cartesian product), returning `list[tuple[Array, dict]]`.

**Requirements:** R1

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/seed_generation.py` (new)

**Approach:**

```python
def _generate_diverse_seeds(
    netlist: Netlist,
    board: Board,
    config: MultiSeedConfig,
    master_rng_key: Array,
) -> list[tuple[Array, dict]]:
```

Hyperparameter grid (K2):
- `init_methods` ∈ `["spectral", "zone_aware_spectral", "random"]`
- `laplacian_options` ∈ `[True, False]`
- `margin_options` ∈ `[0.05, 0.10, 0.20]`
- `perturb_sigmas` ∈ `[0.0, 0.02, 0.05, 0.10]` (fraction of board diagonal)

Cartesian product yields 2×3×3×4 = 72; subset-randomly to `n_generate` (capped at 50). For each hyperparameter tuple:

1. Instantiate the appropriate initializer with the sampled hyperparameters
2. Compute positions
3. Add Gaussian perturbation with `sigma * board_diagonal` (skip if sigma=0)
4. Validate: discard if all NaN, all identical, or any NaN → replace via retry
5. Record metadata dict with all hyperparameters used

For `random` method: use `PlacementState.random_init()` with distinct PRNG keys, no extra perturbation needed. Metadata records `init_method = "random"` (spectral params are N/A).

**Filtering contract:**
- Degenerate seeds (all-NaN, all-identical positions) are discarded and replaced
- If after regeneration retries, `n_valid < n_select`: log structured warning, fallback to `PlacementState.random_init()`
- If zero seeds survive: abort with hard error (systemic issue)

**Test scenarios:**
- `test_generates_n_seeds`: `n_generate=20` → 20 seeds returned
- `test_all_seeds_within_bounds`: all positions ∈ [0, board.width] × [0, board.height]
- `test_no_nan_positions`: no NaN in any returned seed
- `test_metadata_contains_hyperparams`: each metadata dict has keys matching grid
- `test_diverse_methods_produced`: seeds with different init methods present in pool
- `test_degenerate_fallback`: synthetic netlist producing NaN → falls back to random_init()
- `test_zero_seeds_error`: all seeds degenerate → hard error raised

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_seed_generation.py -v`

---

### U3. DPP Kernel Construction (`_dpp_kernel_from_positions`)

**Goal:** Build an n×n similarity kernel matrix from seed position vectors using RMS distance and RBF transformation.

**Requirements:** R2

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/dpp_selection.py` (new, also houses U4)

**Approach:**

```python
def _dpp_kernel_from_positions(
    seeds: list[tuple[Array, dict]],
) -> tuple[Array, float]:
    """
    Build DPP kernel L from seed positions.
    
    Returns (L, condition_number) where:
      L[i,j] = exp(-RMS(x_i - x_j)^2 / (2 * sigma^2))
      sigma = median(pairwise RMS distances)
    """
```

Algorithm:
1. Sort each seed's components by stable reference ID (from netlist component order, which is deterministic)
2. Flatten sorted positions to vectors `x_i ∈ R^(N*2)`
3. Compute pairwise RMS distance: `d(i,j) = sqrt(mean((x_i - x_j)^2))`
4. Set σ = median of all pairwise distances (ensures scale-invariance)
5. Kernel: `L[i,j] = exp(-d[i,j]^2 / (2*σ^2))` → symmetric, values in (0, 1], diagonal = 1.0

**Condition number**: `kappa = λ_max / λ_min` via `jnp.linalg.eigh(L)`. Log and return alongside L. Threshold: `kappa > 10^6` triggers farthest-point sampling fallback in U4.

**Test scenarios (R2a–R2c):**
- `test_kernel_symmetric`: `jnp.allclose(L, L.T)`
- `test_kernel_positive_entries`: all entries > 0 and ≤ 1
- `test_kernel_identical_seeds`: two seeds with same positions → kernel value ≈ 1.0
- `test_kernel_shuffled_copy`: seed and its component-permuted copy → kernel value ≈ 1.0 (after reference-ID sort)
- `test_kernel_distance_monotonic`: larger RMS distance → smaller kernel value
- `test_kernel_degenerate`: all seeds identical → condition number is inf; handled gracefully

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_dpp_selection.py -v`

---

### U4. DPP Subset Selection (`_dpp_select`)

**Goal:** Select k seed indices from the kernel matrix via greedy DPP MAP inference, with kernel ill-conditioning fallback to farthest-point sampling.

**Requirements:** R3

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/dpp_selection.py` (same file as U3)

**Approach:**

```python
def _dpp_select(
    L: Array,
    k: int,
    quality: Array | None = None,
    condition_number: float | None = None,
    seed_vectors: Array | None = None,
) -> list[int]:
    """
    Select k indices via greedy DPP MAP inference.
    
    DPP probability: P(Y) ∝ det(L_Y)
    Greedy MAP: argmax_Y det(L_Y), built incrementally with Cholesky updates.
    """
```

**Core algorithm — Greedy DPP MAP inference:**

Initialize `Y = []`. For each iteration:
1. For each candidate i not in Y, compute `det(L_{Y ∪ {i}})`
2. Select `i* = argmax det(L_{Y ∪ {i}})`
3. Append i* to Y

Naive O(n·k⁴) is sufficient for n≤50, k≤5 (~2500 determinant computations × ≤5×5 matrices).

**Quality-diversity decomposition** (when `dpp_quality_enabled=True`):
- `L_ij = q_i * S_ij * q_j` where `S` is the similarity matrix
- Extract similarity S and reconstruct L with quality vector q

**Kernel ill-conditioning fallback:**
When `condition_number > 10^6`: log `event="dpp_selection"` with `kernel_condition_number` and `fallback=farthest_point`. Use farthest-point sampling on the original seed position vectors:
1. Pick seed 0 as first
2. For each remaining selection: pick the seed with maximum minimum distance to any already-selected seed
3. This provides numerically stable diversity without kernel inversion

**Test scenarios (R3a–R3c):**
- `test_select_identity_kernel`: identity kernel, k=3 → deterministic selection of first k indices
- `test_select_block_diagonal_clusters`: synthetic 2-cluster pool (cluster sizes [3, 4], k=3) → selected set includes members from both clusters (R3b)
- `test_select_respects_k`: returns exactly k indices
- `test_select_quality_vector_k1`: k=1 with quality vector → highest-quality seed selected (R3c)
- `test_select_no_duplicates`: all indices unique
- `test_select_ill_conditioned_fallback`: near-singular kernel → farthest-point fallback invoked, log message captured

**Property-based tests (Hypothesis):**
- `test_kernel_is_symmetric_psd`: all eigenvalues ≥ 0 (within numerical tolerance)
- `test_kernel_values_in_01`: all entries ∈ [0, 1]
- `test_dpp_subset_size_eq_k`: `len(selected) == k`
- `test_kernel_determinant_ge_0`: `det(L_selected) ≥ 0`

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_dpp_selection.py -v --hypothesis-max-examples=50`

---

### U5. Triage Evaluation (`_triage_evaluate`)

**Goal:** Run a fixed-budget (30 iteration) optimization on a subset of the loss stack and return the final loss value.

**Requirements:** R4

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/triage.py` (new)

**Approach:**

```python
def _triage_evaluate(
    positions: Array,
    netlist: Netlist,
    board: Board,
    context: LossContext | None = None,
    n_iters: int = 30,
    lr: float = 0.05,
) -> float:
    """
    30-iteration cheap evaluation with a minimal loss stack.
    
    Returns final loss value (lower is better). Returns NaN on failure.
    """
```

Loss stack (R4): wirelength (w=1.0) + overlap (w=1.0) + boundary (w=1.0) + clearance (w=1.0) — all weight 1.0, non-configurable in v1.

Algorithm:
1. Construct `CompositeLoss` with the 4 loss terms at weight=1.0
2. Create a minimal `LossContext` from netlist + board, or use provided context
3. JIT-compile a value-and-grad function via `create_value_and_grad_fn_with_breakdown`
4. Use simple SGD with fixed LR=0.05 (no optax, inline gradient descent for simplicity: `pos -= lr * grad`)
5. No Gumbel-Softmax (rotations locked to default orientation), no annealing, no adaptive techniques
6. Run 30 iterations; return final loss value

**NaN handling:**
- If triage produces NaN loss: seed is discarded (U2 replaces it)
- If >20% of seeds produce NaN triage loss: abort with hard error

**Performance profile:**
- ~1 second on most boards (JIT-compiled, single compilation per unique netlist shape)
- All seeds share the same netlist → `CompositeLoss` and `LossContext` structure is identical → JIT compiles once, reused across all triage evaluations

**Test scenarios (R4a, R4b):**
- `test_triage_monotonic`: loss non-increasing over 30 iterations (on easy synthetic board) — R4a
- `test_triage_finite_values`: final loss is finite, not NaN or Inf — R4b
- `test_triage_produces_reasonable_loss`: loss decreases significantly from iteration 0 to iteration 30
- `test_triage_nan_discard`: NaN loss → detected and logged
- `test_triage_mass_nan_abort`: >20% NaN → hard error raised

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_triage.py -v`

---

### U6. Triage ↔ Full Optimization Correlation Validation

**Goal:** Validate that triage loss correlates with full optimization quality (Spearman ρ ≥ 0.5).

**Requirements:** R5

**Files:**
- `packages/temper-placer/tests/integration/test_triage_correlation.py` (new)

**Approach:**

1. Generate 20 seeds via `_generate_diverse_seeds`
2. Run each through triage (30 iters) → record triage loss
3. Run each through `train_multiphase` with `OptimizerConfig.fast_test()` (100 epochs) → record full loss
4. Compute Spearman rank correlation ρ between triage losses and full losses
5. Assert ρ ≥ 0.5

The full test uses 20 seeds and is gated on `--long` flag (nightly). A fast-path variant in CI runs 3 seeds × 10 iterations to verify pipeline integrity without validating correlation quality.

**Test scenarios:**
- `test_triage_correlation_meets_threshold`: ρ ≥ 0.5 (nightly only)
- `test_triage_pipeline_executes`: 3 seeds, triage + full → no crashes (CI fast-path)

**Verification:** `uv run pytest packages/temper-placer/tests/integration/test_triage_correlation.py -v --long`

---

### U7. Orchestration Entry Point (`train_dpp_multiseed`)

**Goal:** Wire U2→U3→U4→U5→`train_multiphase` into a single callable that returns `ParallelTrainingResult`.

**Requirements:** R6

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/train.py` — add `train_dpp_multiseed` function

**Approach:**

```python
def train_dpp_multiseed(
    netlist: Netlist,
    board: Board,
    composite_loss: CompositeLoss | None = None,
    loss_factory: Callable[[dict[str, float]], CompositeLoss] | None = None,
    context: LossContext | None = None,
    config: OptimizerConfig | None = None,
    n_generate: int | None = None,
    n_select: int | None = None,
    n_triage_iters: int | None = None,
    callback: Callable[[TrainingMetrics], None] | None = None,
    validation_callback: ValidationCallback | None = None,
) -> ParallelTrainingResult:
```

Execution flow (K5):
1. Resolve `n_generate`/`n_select` from args or config
2. **Seed generation** (U2): `_generate_diverse_seeds(netlist, board, config, rng_key)` → pool of N seeds
3. **DPP kernel** (U3): `_dpp_kernel_from_positions(seeds)` → L matrix + condition number
4. **DPP selection** (U4): `_dpp_select(L, k, condition_number, seed_vectors)` → k indices
5. **Triage evaluation** (U5): run `_triage_evaluate` on each selected seed → k loss values
6. **Promotion**: pick seed with lowest triage loss, run `train_multiphase` from that seed
7. Return `ParallelTrainingResult` with the full optimization result and DPP diagnostics

**Edge cases (R6):**
- `n_generate < n_select`: log warning, skip DPP filtering, select all generated seeds for triage (subject to U2's fallback)
- `multi_seed.enabled = False`: short-circuit to `train_multiphase` directly
- All seeds degenerate: U2 already handles fallback to `random_init()`

**Structured logging (P0 minimum — R9 P0 subset):**
Emit a single INFO log line `event="seed_promoted"` with `seed_id`, `triage_loss`, and hyperparameters of the promoted seed.

**Test scenarios:**
- `test_disabled_short_circuits`: `multi_seed.enabled=False` → calls `train_multiphase` directly, result identical to single-seed
- `test_happy_path_produces_result`: full pipeline on a synthetic netlist → returns `ParallelTrainingResult`
- `test_n_generate_lt_n_select_fallback`: `n_generate=3, n_select=4` → warning logged, all 3 seeds triaged
- `test_degenerate_pool_fallback`: all seeds degenerate → falls back to `random_init()`
- `test_result_type_matches`: return type is `ParallelTrainingResult` (drop-in compatible with `train_parallel`)

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_train.py -v`

---

### U8. Unit and Property Tests (R8a–i)

**Goal:** Comprehensive test coverage of the DPP multi-seed pipeline.

**Requirements:** R8

**Files:**
- `packages/temper-placer/tests/optimizer/test_dpp_selection.py` (U3+U4 tests)
- `packages/temper-placer/tests/optimizer/test_triage.py` (U5 tests)
- `packages/temper-placer/tests/optimizer/test_seed_generation.py` (U2 tests)
- `packages/temper-placer/tests/optimizer/test_train.py` (U7 tests)
- `packages/temper-placer/tests/optimizer/test_dpp_kernel.py` (U3 property tests)

**Test inventory (R8a–i mapping):**

| ID | Test | Location |
|----|------|----------|
| R8a | Kernel symmetric, positive entries | `test_dpp_kernel.py::test_kernel_symmetric_pd` |
| R8b | Identical seeds → kernel ≈ 1.0 | `test_dpp_kernel.py::test_kernel_identical` |
| R8c | DPP selects from both clusters | `test_dpp_selection.py::test_block_diagonal_clusters` |
| R8d | Selected subset has exactly k elements | `test_dpp_selection.py::test_select_respects_k` |
| R8e | Triage loss monotonic | `test_triage.py::test_triage_monotonic` |
| R8f | Triage correlation ρ ≥ 0.5 | `test_triage_correlation.py::test_correlation_meets_threshold` (nightly) |
| R8g | Seeds within bounds, no NaN | `test_seed_generation.py::test_all_seeds_within_bounds_and_finite` |
| R8h | Degenerate pool fallback | `test_train.py::test_degenerate_pool_fallback` |
| R8i | Disabled → identical to single-seed | `test_train.py::test_disabled_short_circuits` |

**Property-based tests (Hypothesis):**
- DPP kernel is symmetric PSD (eigenvalues ≥ -1e-10)
- DPP kernel values in [0, 1]
- DPP subset size equals n_select
- Kernel determinant ≥ 0

**Additional edge-case tests:**
- `test_kernel_ill_conditioned_fallback`: near-singular kernel → farthest-point sampling invoked
- `test_degenerate_pool_random_fallback`: all seeds rejected → `random_init()` fallback
- `test_rms_kernel_computation`: explicit RMS formula verified against reference computation

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/ -v -k "dpp or triage or seed_gen"`

---

### P1 Tier — Integration (U9–U10)

---

### U9. CLI Integration (`--multi-seed` flag)

**Goal:** Expose multi-seed through the CLI, replacing `--parallel-seeds` logic when `--multi-seed` is passed.

**Requirements:** R6 (CLI entry), A4 (CLI user actor)

**Files:**
- `packages/temper-placer/src/temper_placer/cli/__init__.py` — add `--multi-seed` flag and dispatch

**Approach:**

At `cli/__init__.py:811` (the `parallel_seeds > 1` branch), add a `--multi-seed` flag. When set:
1. Parse `config.multi_seed.enabled = True`
2. Call `train_dpp_multiseed(...)` instead of `train_parallel(...)`
3. Display DPP selection summary (seeds generated / selected / triaged, best triage loss) in CLI output

Default behavior unchanged: `--multi-seed` is off by default. Config-file `multi_seed.enabled: true` also triggers the path even without CLI flag.

**Test scenarios:**
- `test_multi_seed_flag_triggers_dpp_path`: CLI with `--multi-seed` → `train_dpp_multiseed` called
- `test_config_enabled_triggers_no_flag`: YAML config with `multi_seed.enabled: true`, no CLI flag → DPP path
- `test_without_flag_unchanged`: no `--multi-seed` and config disabled → original behavior

**Verification:** `uv run pytest packages/temper-placer/tests/cli/ -v`

---

### U10. Structured Observability (R9, P2-lite)

**Goal:** Emit structured log lines for DPP seed generation, selection, and triage phases.

**Requirements:** R9

**Files:**
- No new files; add logging calls in U2, U4, U5, U7

**Approach:**

Three structured INFO-level log events (JSON-serializable `extra` dict):

1. `event="dpp_seed_gen"`: `n_requested`, `n_generated`, `n_degenerate`, `elapsed_ms`
2. `event="dpp_selection"`: `n_input`, `n_selected`, `kernel_condition_number`, `selected_indices`, `selected_hyperparams`, `fallback_method` (if applicable)
3. `event="dpp_triage"`: `n_seeds`, `n_iters`, `scores` (list of `{seed_id, triage_loss}`), `best_seed_id`, `best_triage_loss`, `elapsed_ms`

**Test scenarios:**
- `test_log_seed_gen_emitted`: capture log; assert `event="dpp_seed_gen"` present with all keys
- `test_log_selection_emitted`: assert `event="dpp_selection"` with indices and condition number
- `test_log_triage_emitted`: assert `event="dpp_triage"` with scores and best seed
- `test_log_fallback_in_selection`: ill-conditioned kernel → `fallback_method="farthest_point"` in selection log

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_logging.py -v`

---

### P2 Tier — Polish (U11–U12)

---

### U11. Full Config Knob Exposure

**Goal:** Expose the remaining 7 hardcoded parameters as `MultiSeedConfig` fields.

**Requirements:** R7 (P2 subset)

**Files:**
- `packages/temper-placer/src/temper_placer/optimizer/config.py`

**Approach:**

Add to `MultiSeedConfig`:
```python
init_methods: list[str] = field(default_factory=lambda: ["spectral", "zone_aware_spectral", "random"])
laplacian_options: list[bool] = field(default_factory=lambda: [True, False])
margin_options: list[float] = field(default_factory=lambda: [0.05, 0.10, 0.20])
perturb_sigmas: list[float] = field(default_factory=lambda: [0.0, 0.02, 0.05, 0.10])
triage_loss_weights: dict[str, float] = field(default_factory=lambda: {
    "wirelength": 1.0, "overlap": 1.0, "boundary": 1.0, "clearance": 1.0
})
dpp_quality_weight: float = 0.0
```

Update U2 to consume these fields instead of hardcoded values. Keep P0-era hardcoded values as the defaults.

**Test scenarios:**
- `test_config_roundtrips`: serializable to/from YAML
- `test_init_methods_validation`: invalid method name → error
- `test_loss_weights_validation`: non-positive weight → warning

**Verification:** `uv run pytest packages/temper-placer/tests/optimizer/test_config.py -v`

---

### U12. A/B Testing Infrastructure and SC Validation

**Goal:** Implement the A/B testing framework and validate success criteria SC1, SC1b, SC2–SC6.

**Requirements:** Success Criteria SC1–SC6, A/B Testing section

**Files:**
- `packages/temper-placer/tests/integration/test_dpp_multiseed_ab.py` (new)
- `tools/measurements/dpp_ab_measurement.py` (new)

**Approach:**

A/B testing variants:
- **Baseline A**: single seed (random init via `train_multiphase`)
- **Baseline B**: random K-from-N selection with triage (no DPP)
- **Variant**: DPP-selected K-from-N with triage

Per-board runs: 10 runs each variant, same master seed per run for reproducibility.

SC1b specific: DPP vs random selection must show lower variance (one-sided F-test, p < 0.05) on ≥2/3 regression corpus boards.

**Implementation:**
- `tools/measurements/dpp_ab_measurement.py` — script to run A/B variants N times per board, output JSON + markdown summary
- `test_dpp_multiseed_ab.py` — CI-gated test that asserts the committed baseline file is not stale (>30 days)

**Test scenarios:**
- SC1b: `test_dpp_lower_variance_than_random` — F-test on DPP vs random selection variance (≥2/3 boards)
- SC4: `test_dpp_within_5pct_of_best_single_seed` — wirelength ≤ 1.05× best single-seed on ≥90% of runs
- Baseline file staleness gate

**Verification:** `uv run pytest packages/temper-placer/tests/integration/test_dpp_multiseed_ab.py -v`

---

## Key Technical Decisions

**K1. DPP operates on seed dissimilarity, not seed likelihood.** DPP kernel `L[i,j]` measures similarity between seeds via RMS position distance → RBF. The DPP probability of selecting subset S is proportional to `det(L_S)`, which is maximized when S contains seeds that are dissimilar (small off-diagonal entries in L). Quality terms can optionally down-weight low-quality seeds (disabled by default in P0).

**K2. Seed generation varies initialization hyperparameters, not just PRNG seeds.** The cartesian product of (init_method × laplacian × margin × perturbation) yields up to 72 seeds, randomly subsampled to n_generate (capped at 50). This creates genuine structural diversity rather than just PRNG-driven randomness.

**K3. Position-distance kernel with component reference-ID sorting.** Before computing RMS distances across flattened position vectors, sort each seed's components by their stable netlist reference ID. This ensures deterministic ordering and makes the kernel invariant to component permutation — a seed and its shuffled copy produce kernel value 1.0.

**K4. Kernel ill-conditioning fallback to farthest-point sampling.** When the kernel matrix condition number exceeds 10^6, DPP selection is numerically undefined. Farthest-point sampling on the original seed position vectors provides well-defined diversity selection without requiring kernel inversion.

**K5. Greedy MAP inference is sufficient.** Naive O(n·k⁴) greedy selection (full determinant at each step) is fast enough for n≤50, k≤5. Incremental Cholesky updates (O(n·k³)) can be deferred. The greedy algorithm is not guaranteed to find the true MAP, but it is a provably good approximation for DPPs with submodular log-det objectives.

**K6. σ is set to the median pairwise RMS distance.** This ensures scale-invariance — the kernel adapts to the board size and component count automatically. The median is robust to outliers compared to the mean.

**K7. Triage is JIT-compiled once per netlist shape.** All seeds in a single multi-seed run share the same netlist (same component count). The `CompositeLoss` structure and `LossContext` shape are identical across all seeds. JAX compilation happens on the first triage call and is reused across all subsequent triage evaluations, keeping overhead minimal.

**K8. Drop-in compatibility with `train_multiphase` and `train_parallel`.** `train_dpp_multiseed` returns `ParallelTrainingResult` — the same type as `train_parallel`. It accepts the same `netlist`, `board`, `context`, `config` parameters as `train_multiphase`. Existing callers of `train_multiphase` do not need code changes; the multi-seed path is a new outer orchestration, not a replacement.

---

## System-Wide Impact

| File | Change |
|------|--------|
| `packages/temper-placer/src/temper_placer/optimizer/config.py` | +~80 lines: `MultiSeedConfig` dataclass, `OptimizerConfig.multi_seed` field |
| `packages/temper-placer/src/temper_placer/optimizer/seed_generation.py` | New: +~150 lines: `_generate_diverse_seeds` |
| `packages/temper-placer/src/temper_placer/optimizer/dpp_selection.py` | New: +~200 lines: `_dpp_kernel_from_positions`, `_dpp_select`, farthest-point fallback |
| `packages/temper-placer/src/temper_placer/optimizer/triage.py` | New: +~120 lines: `_triage_evaluate`, triage loss stack construction |
| `packages/temper-placer/src/temper_placer/optimizer/train.py` | +~120 lines: `train_dpp_multiseed`, `_seed_promotion_log` |
| `packages/temper-placer/src/temper_placer/cli/__init__.py` | +~40 lines: `--multi-seed` flag and dispatch |
| `packages/temper-placer/tests/optimizer/test_seed_generation.py` | New: +~100 lines |
| `packages/temper-placer/tests/optimizer/test_dpp_selection.py` | New: +~250 lines (unit + property tests) |
| `packages/temper-placer/tests/optimizer/test_triage.py` | New: +~100 lines |
| `packages/temper-placer/tests/optimizer/test_train.py` | +~70 lines: orchestration tests |
| `packages/temper-placer/tests/optimizer/test_logging.py` | New: +~80 lines |
| `packages/temper-placer/tests/integration/test_triage_correlation.py` | New: +~120 lines |
| `packages/temper-placer/tests/integration/test_dpp_multiseed_ab.py` | New: +~200 lines |
| `tools/measurements/dpp_ab_measurement.py` | New: +~150 lines |

**No changes to:** `train_multiphase`, the 5-phase curriculum, `initialize_training_state`, individual loss functions, `CompositeLoss`, `LossContext`, the deterministic placer, or the router.

---

## Implementation Order / Dependency Graph

```
U1 (MultiSeedConfig)
 └─┬── U2 (Seed Generation) ───┐
   ├── U3 (DPP Kernel) ────────┤
   └── U4 (DPP Selection) ─────┤
        └── U5 (Triage) ───────┤
             └── U6 (Correlation Validation) ──┐
                  └── U7 (Orchestration) ──────┤
                       ├── U8 (Unit Tests) ────┤
                       │     └── U9 (CLI) ─────┤
                       │          └── U10 (Logging) ──┤
                       │               └── U11 (Full Config) ──┤
                       │                    └── U12 (A/B Testing)
                       │
                       └── (U2 can be parallelized with U3+U4)
```

**Phase 1 (P0, PR-series A):** U1 → U2, U3, U4 in parallel → U5 → U6 → U7 → U8
**Phase 2 (P1, PR-series B):** U9 → U10
**Phase 3 (P2, PR-series C):** U11 → U12

U8 tests accumulate across all prior units; each unit's tests ship with the unit itself.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| DPP kernel doesn't capture meaningful diversity | Medium | Low-Medium | Start with position-distance kernel; validate against spectral-embedding kernel (alternate kernel in R2). DPP selection API is kernel-agnostic — only `_dpp_kernel_from_positions` changes if we switch. |
| Triage cost doesn't correlate with final quality | **High** | Medium | R5 Spearman ρ ≥ 0.5 gate implemented in U6. If ρ < 0.5, extend triage stack (add congestion/thermal) or increase iterations to 50. Test runs nightly; blocks merge. |
| Compute overhead exceeds benefit | Low | Low | DPP O(n²)=2500 comparisons at ~100 comps ≈ negligible. Greedy DPP O(n·k⁴) ≈ 6250 det calls ≈ negligible. Triage: 4×30 iter at ~0.03s/iter ≈ 3.6s. Full optimization ~30min. Total overhead <1% of one full run. SC2 caps total at 1.5×. |
| Kernel ill-conditioning breaks DPP selection | Low | Low | Condition number threshold (10^6) with farthest-point fallback in U4. Logged prominently so operators can investigate. |
| Degenerate seed pool (too few valid seeds) | Medium | Low-Medium | U2: retry, then fallback to random_init(). If zero seeds survive, hard error aborts. U7: n_generate < n_select skips DPP filtering. |
| DPP quality-diversity decomposition hard to tune | Low | Medium | Default `dpp_quality_enabled=False` (pure diversity DPP). Quality only enabled after R5 correlation validated and calibrated quality function available. |
| JIT recompilation per triage seed | None | Resolved | All seeds share the same netlist (same component count). JIT compiles once, reused across all triage evaluations. Shape-triggered recompilation is not a concern. |
| Regression on existing placement tests | Medium | Low | Feature is additive layer above existing code. No changes to `train_multiphase`, `train`, or `train_parallel`. U7's disabled test (R8i) gates this. |

---

## Test Strategy

- **Unit tests (CI, per-commit):** U2, U3, U4, U5 tests — pure functions and state machines with synthetic inputs. Coverage target: ≥95% of new code.
- **Property-based tests (CI, per-commit):** Hypothesis tests for DPP kernel properties (symmetric PSD, values in [0,1], subset size, determinant ≥ 0). max_examples=50.
- **Integration test (nightly, `--long` flag):** U6 — triage correlation validation (20 seeds × full optimization). CI fast-path variant: 3 seeds × 10 iters pipeline integrity check.
- **A/B acceptance tests (nightly, `--long` flag):** U12 — SC1b (DPP vs random variance), SC4 (wirelength within 5% of best).
- **CI gates:** All unit + property tests pass on every commit. No regression on existing placement tests (existing test suites unchanged).

---

## Scope Boundaries

### In Scope

- P0: MultiSeedConfig, seed generation, DPP kernel + selection, triage evaluation, correlation validation, orchestration, unit/property tests
- P1: CLI `--multi-seed` flag, structured observability (3 info-level log events)
- P2: Full config knob exposure, A/B testing infrastructure, SC validation

### Deferred

- **GPU-accelerated DPP or batched DPP selection.** For n=50, k=5, CPU greedy is fast enough.
- **Online DPP adaptation** (updating kernel mid-optimization).
- **Per-seed JAX JIT parallelization** (pmap/vmap across seeds).
- **Alternative diversification methods** (k-means, MMD-critic, farthest-point sampling as primary method).
- **Dynamic triage budget allocation** (adaptive stopping, bandit algorithms).
- **Seed quality model** (ML-learned predictor of final quality from seed positions).

### Out of Scope

- Modifying the 5-phase curriculum or individual loss functions.
- Changing `train_multiphase`, `train`, or `train_parallel` behavior.
- The deterministic placer's seed-filtering pipeline (separate plan: `docs/plans/2026-06-23-004-feat-seed-filtering-plan.md`).
- Firmware, PCB schematics, or router changes.
