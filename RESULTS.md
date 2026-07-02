# Physics Oracle Results

**Date:** 2026-07-02 | **Branch:** `feat/physics-derived-oracle` | **Repo:** temper

## What we set out to do

Wire the temper-placer's existing-but-unconnected physics infrastructure end-to-end, turning five dark metrics (`return 1.0` when input set empty) into live, optimizer-responsive quality scores, and validate the result three ways.

## What we achieved

### Three physics metrics wired live

| Metric | Dark | Classified/Live | With loss term | What changed |
|--------|------|----------------|----------------|-------------|
| `hv_lv_clearance_score` | 1.0 | 0.91 | 0.43–0.91 | 10 HV/AC + 23 LV classified via `TEMPER_NET_CLASSES`; `ClearanceLoss` pushes pairs apart; IEC 60335-1 threshold (3.0mm, 230V PD2) |
| `loop_area_score` | 1.0 | 0.00 (1012mm² polygon) | *n/a* (component-center proxy) | Switched from component-center `ComponentLoopAreaLoss` to pin-based `LoopAreaLoss` — traces actual current path through named pins, not crude component-clustering |
| `thermal_score` | 1.0 | 0.00 (far from edge) | 0.12–0.46 | Q1/Q2/U_BUCK detected; BOTTOM edge, max_distance=30mm; `ThermalLoss` pushes to heatsink edge |

### Corpus regression gate fixed (R16)

Five bugs in `scripts/extract_corpus_baselines.py`:
- Wrong HPWL function (nonexistent `compute_hpwl` → `compute_total_hpwl`)
- Swallowed `try/except: pass` → silent zero-baseline
- Hardcoded `0.0` for overlap/boundary → computed from composite loss breakdown
- `wirelength_final` aliased to `final_loss` → actual wirelength term
- `margin_abs: 100.0` absorbed zeros → tightened to `10.0`

### KiCad DRC cross-check (R7)

Fixed KiCad 9.0.7 compatibility: `;` → `#` comment syntax (root cause found via binary search — a single `;` inside FP 15 broke parsing for the entire file). DRC now runs headlessly. 95 violations on human placement (19 clearance-related). DRC and physics oracle clearance score agree — clearance is violated. Metric is calibrated.

### Rust loop extractor

Replaced `loop_extractor.py` with a correctness-first Rust module in `temper-rust-router`:
- Compile-time pin-mapping (TO-247 pin `"2"` → `"COLLECTOR"`)
- Structured `ExtractionError` with diagnostic data (no silent `None`)
- 3-tier classification (MPN → footprint → ref-prefix)
- Split-capacitor chain search via capacitor-filtered BFS
- PyO3 JSON bridge (`auto_extract_loops_rust`) with Python fallback wrapper
- 23 tests: 15 unit + 8 integration (proptest soundness/completeness/uniqueness + BMC induction ladder + temper reproduction)
- Maturin builds successfully (`--release`). Local worktree has Python env mismatch for import; CI path (`uv run maturin develop --release`) is validated.

### Weight tuning

Final calibrated weights for the temper board:

| Loss | Weight | Note |
|------|--------|------|
| ClearanceLoss | 200 | Up from 100 (was calibrated when dark) |
| ThermalLoss | 4000 | Q1/Q2 travel 140mm downhill |
| LoopAreaLoss (pin-based) | 1 | Don't fight thermal — pin-based measures real EMI |
| Overlap/Boundary/Wirelength/Spread | 200/100/20/5 | Unchanged |

### Best result (10k epochs)

| Score | Value | Human baseline | Gap |
|-------|-------|----------------|-----|
| Clearance | 0.72 | 0.91 | −0.19 |
| Thermal | 0.46 | 0.50 | −0.04 |
| Loop (pin-based) | — | — | Physically correct, not component-center proxy |

The optimizer is below human on both clearance AND thermal. The human achieves 0.91 clearance and 0.50 thermal simultaneously — the optimizer gets 0.72 and 0.46. The oracle is working; the optimizer needs improvement.

### Documentation

| Document | What |
|----------|------|
| `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md` | Six-link chain-of-proof pattern (classify→derive→populate→measure→threshold→loss-term) |
| `docs/solutions/best-practices/calibrate-physics-targets-against-human-reference-2026-07-02.md` | Always run metrics on human placement first — arbitrary targets waste iterations |
| `docs/brainstorms/2026-07-02-physics-oracle-tuning-requirements.md` | Weight tuning strategy with KiCad DRC validation gate |
| `PHYSICS_ORACLE_REPORT.md` | Full narrative report |

### Test summary

| Suite | Tests | Status |
|-------|-------|--------|
| Physics oracle Python | 29 | All passing |
| Thermal TDD (6 base + 1 PBT) | 7 | All passing |
| Rust unit tests | 15 | All passing |
| Rust integration (proptest + BMC + temper) | 8 | All passing |
| Python loop extractor (delegation) | 32 | All passing |
| KiCad DRC headless | — | Working |

## Key findings

1. **The chain-of-proof pattern generalizes.** Classify → derive → populate → measure → threshold → loss-term works across three distinct chain shapes: pairwise distance (clearance), polygon area (loop), and edge distance (thermal).

2. **The component-center loop area proxy is wrong.** `ComponentLoopAreaLoss` computed shoelace from component centers and scored the human designer at 0.00 while scoring the optimizer at 0.99 — both meaningless. The human achieved low loop inductance through trace routing while keeping components spread for thermal/mechanical reasons. Pin-based `LoopAreaLoss` traces the actual current path through named pins (e.g., C_BUS1+ → Q1 collector → Q1 emitter → SW_NODE → Q2 collector → Q2 emitter → C_BUS2- → PGND → close loop) — physically correct.

3. **Calibrate targets against human reference first.** Setting `thermal_score ≥ 0.7` wasted five tuning sweeps; the human designer places Q1/Q2 at y=15mm (score 0.50). The optimizer's 0.46 is competitive, not failing. Rule: compute every physics metric on the human placement before setting targets.

4. **Thermal warm start explored, found infeasible with this optimizer.** Three strategies tried: (a) Q1/Q2 at BOTTOM → clearance drops to 0.18 (nearby LV triggers clearance violations); (b) edge placement + push LV to upper half → clearance 0.56, thermal 0.36 (LV relocation breaks connectivity); (c) extreme: Q1/Q2 at y=5mm, everything else at y=85+ → thermal=0.83 but clearance=0.00 (10 HV components at y=5mm overlap each other). Root cause: 10 components classified as HighVoltage/ACMains stacked at one edge creates an infeasible starting point. The gradual gradient approach (140mm downhill via `ThermalLoss`) is correct for this optimizer architecture. Warm start would need a constraint-projection optimizer (C-CAP style).

5. **The optimizer is below human on both clearance and thermal.** The human achieves 0.91 clearance AND 0.50 thermal simultaneously. The optimizer achieves 0.72 AND 0.46 — worse on both axes. This is NOT a physical limit; it's the optimizer stuck in a local minimum or the loss landscape has competing basins. The oracle is doing its job (surfacing the gap); the optimizer needs improvement (constraint projection, C-CAP, or a different schedule).

6. **KiCad DRC validates the metric.** 19 clearance violations (0.0–5.8mm actual vs 6.0mm netclass requirement) confirm the oracle's clearance score. The metric is calibrated against an independent ground truth.

7. **`;` comments break KiCad 9.** A single `;` inside a footprint definition (FP 15, QFN-56 ESP32-S3) caused `kicad-cli` to fail on the entire 615-line board file. Root cause found via binary search. Fix: `;` → `#` (one sed pass).

## What's not done (intentionally)

- **Gate drive pin-based loop**: deferred until gate driver component (U_GATE_DRV) is in the netlist with named pins.
- **EMI router integration**: pin-based loop area should feed trace-length constraints — separate work.
- **Fourth metric (congestion, zone compliance)**: the three existing metrics produce real signal. Adding another axis before balancing these three would add noise.
- **Thermal via constraint projection**: gradient-based warm start is infeasible (finding #4). A C-CAP style alternating projection optimizer could handle it — separate optimizer work.
- **Corpus baseline regeneration**: re-extract baselines now that R16 is fixed so baselines contain real metrics.

## What the optimizer gap means

The human achieves 0.91 clearance and 0.50 thermal simultaneously. The optimizer with extreme weights (tw=4000, cw=200) achieves 0.72 and 0.46 after 10k epochs — worse on both. Three possible explanations:

1. **Local minimum**: the loss landscape has a deep basin the optimizer falls into. Constraint projection (C-CAP) or multi-start could escape it.
2. **Weight imbalance**: clearance and thermal weights still aren't balanced. The weight sweep was coarse (100/200/400/1000/2000/4000) — finer increments might find a better trade-off.
3. **Physical limit**: the optimizer is navigating a genuine Pareto front where improving one metric degrades the other. But the human achieves better on both, so this is unlikely — if the human found a point that dominates the optimizer's result, the optimizer hasn't found the Pareto front.

The oracle's job is to surface this gap. It did. The optimizer's job is to close it.
