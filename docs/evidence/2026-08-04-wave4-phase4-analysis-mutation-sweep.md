# Wave 4 Phase 4 — analysis-surface mutation sweep (area sufficiency + violation report)

<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- the originally recorded commit (1ac0ae306c2e11a40a9a0a1ec4b9ec0eccef70cd) does not resolve to any commit object in this repository (dangling, orphaned by rebase/squash) and no persisting equivalent could be identified without guessing. See .evidence-provenance-allowlist. -->

The anti-vacuity campaign for the two Wave 4 Phase 4 analysis-surface
migrations: `temper_placer/analysis/_area_sufficiency.py` →
`temper-geometry` (`src/area_sufficiency.rs`) and
`temper_placer/analysis/_violation_report.py` → `temper-drc-rs`
(`src/violation_report.rs`).  Every mutation was applied to the Rust
source, the crate rebuilt (`uv run --no-sync maturin develop --release`),
and the module's differential + PBT suites run; the source was restored
and the crate rebuilt from the restored source afterwards.

**11 mutants, 0 survived.**  The per-mutant catcher (which assertion
failed) is listed; no discriminating-case additions were required — the
differentials/PBT already caught every mutant on the first run of the
campaign.

| # | Mutant | What caught it |
|---|--------|----------------|
| M1 | `py_sum_neumaier` — naive accumulation (compensation disabled) | `test_py_sum_matches_builtin_sum_bit_exact` — the 1e16/1/-1e16 discriminator (naive 0.0 vs CPython 1.0) |
| M2 | `py_sum_neumaier` — dropped the final `if c && finite(c) f += c` | same discriminator (compensation is only visible through the final add) |
| M3 | `py_sum_neumaier` — `items[0]` instead of `0.0 + items[0]` | `test_py_sum_single_negative_zero_normalises_to_positive` (-0.0 must normalise to +0.0) |
| M4 | `py_sum_neumaier` — dropped the `is_finite(c)` check | corpus case `[1.7976931348623157e308, 1.7976931348623157e308]` (c = -inf; missing check yields `inf + -inf = NaN`) |
| M5 | `area_sufficiency_compute` — `(total*100.0)/usable` instead of `(total/usable)*100.0` | `test_compute_ratio_ordering_matches_oracle_on_overflow_band` (1e308 band: 100.0 vs inf) |
| M6 | `build_report_rows` — dropped the target-rule filter | `test_rows_oracle_vs_shim_basic` (clearance row must be dropped) |
| M7 | `build_report_rows` — dropped the ref sort | `test_rows_oracle_vs_shim_basic` / PBT P2 (unsorted `["D3","C4"]` pair) |
| M8 | `build_report_rows` — ascending instead of descending row sort | `test_rows_sort_order_and_stability` (row order vs oracle) |
| M9 | `render_report` — `overlap >= 0.0` instead of `overlap > 0.0` | `test_render_oracle_vs_shim_basic` (0.0 must render the em-dash, not "0.00") |
| M10 | `render_report` — truncation at 121 instead of 120 chars | `test_render_pipe_escaping_and_truncation` (200-char message) |
| M13 | `render_report` — dropped the `|`→`\|` escaping | `test_render_pipe_escaping_and_truncation` |

Two further render-literal mutations (the join separator and the intro
line's double space after `` `kicad-cli pcb drc`. ``) were considered and
folded into the byte-identical render assertions' class coverage: every
render differential compares the full output byte-for-byte against the
oracle, so any literal drift fails the same assertions M9/M10 exercise.

The campaign's three property-bound corrections (MR1 power-of-two scaling
bounded to the normal float range, MR2 margin monotonicity bounded to
non-negative areas, MR3 bounded to the canonicalised fields; P5's specials
strategy without min/max, which hypothesis rejects with
`allow_nan=True`) were found *before* the campaign, while bringing the PBT
suite green, and are recorded in the suites themselves.

Gate status after the campaign: 165 analysis tests pass (2 deselected:
the kicad-cli integration tests, one of which — production-board DRC
counts — is pre-existing run-to-run noise on `origin/main`); `cargo test
--all-features` and `cargo clippy --all-features --all-targets` clean in
both crates; ruff, import-linter, verdict-coverage, vulture,
extensions-check and physics-soundness-register gates clean.
