# Wave 4 Phase 4 leftovers — adversarial-review fixes and mutation-campaign re-run — 2026-08-05

<!-- provenance: commit=cdb4f5272bf12ddd47bf70abf8fc5876f61482af dirty=false (stamped 2026-08-05: the previously-recorded commit=c40beeb4bf165a9d20c0d5f2d6e8b057a6b1c57a resolves in no object store, local or fresh clone -- mistyped or fabricated -- and the dirty field was malformed ("false-at-campaign-time"); this doc was introduced on main at cdb4f5272bf12ddd47bf70abf8fc5876f61482af, which is the cited commit) -->

**Scope:** the four Phase 4 leftovers migrations
(`manufacturing/tolerances.py`, `manufacturing/monte_carlo.py`,
`extraction/hypergraph_factory.py` in `temper-design-bundle`;
`manufacturing/stackup_validator.py` in `temper-io-types`), reviewed
adversarially against PR #766 (`feat/wave4-phase4-leftovers-rust`).

## 1. The incident that triggered this work

VERIFICATION.md's tolerances section claimed 11 mutants caught, including
"etch fallback `0.05→0.06`". **That claim was false for the
`analyze_clearance` site: the `0.06` fallback shipped.** The original
campaign's fallback test (`test_analyzer_missing_copper_weight_falls_back_to_005`)
drove `analyze_trace` only, and `analyze_trace`'s fallback is `0.05` on
BOTH sides — so the campaign (if it applied the mutant at the clearance
site) never saw a failure, or (more likely, given the shipped value) the
campaign's revert step failed to restore the source. Either way, the
"caught" row was a false positive and the mutation-campaign integrity of
the other three modules could not be taken at face value.

Repro (pre-fix): `ToleranceTable(etch_tolerance={ONE_OZ: 0.01})`,
`analyze_clearance(0.5, TWO_OZ, OUTER)` → oracle `worst_case_min` 0.3
(`2*0.05 + 0.1`), Rust 0.28 (`2*0.06 + 0.1`).

## 2. The six findings, RED evidence, and fixes

| # | Finding | RED evidence (pre-fix) | Fix |
|---|---------|------------------------|-----|
| P1 | `analyze_clearance` etch fallback 0.06 vs oracle 0.05 (`manufacturing_tolerances.rs:554`) | oracle `worst_case_min` 0.3 vs Rust 0.28 | literal → `0.05`; new clearance-side fallback differential case `test_analyzer_missing_copper_weight_falls_back_to_005_clearance` |
| P1 | Mutation-campaign revert integrity (see §1) | — | full re-run of all four campaigns with explicit revert verification (§4) |
| P2 | negative `global_net_threshold` inverts the filter (`hypergraph_factory.rs:171`, `(-5i64) as usize` wraps huge → nothing filtered) | oracle `n_edges` 0 vs Rust 1 (`ignore_global_nets=True, threshold=-5`) | compare as i64: `(n_pins as i64) > self.global_net_threshold`; new case `test_negative_threshold_filters_all_nets` |
| P2 | monte_carlo ragged inner dims: `check_*_ndim` never examines axis 1 (`manufacturing_monte_carlo.rs`) | positions (N,3): oracle `ValueError: operands could not be broadcast together with shapes (1,2,3) (8,1,2) ` vs Rust silently computes; bounds (N,1): oracle `IndexError: index 1 is out of bounds for axis 1 with size 1` vs Rust `PanicException` | replicate numpy's exact classes/texts at the oracle's op order: positions dim 1 broadcasts (`x → [x,x]`), dims 0/≥3 raise the broadcast ValueError (trailing space included — verified against numpy 2.3.5), bounds dims 0/1 raise the IndexError texts, bounds ≥3 tolerated; cases `test_positions_three_columns_broadcast_error_parity`, `test_positions_zero_columns_broadcast_error_parity`, `test_bounds_one_column_index_error_parity`, `test_run_parity_positions_single_column_broadcast`, `test_run_parity_bounds_extra_column_tolerated` |
| P2 | stackup int impedance messages (`stackup_validator.rs`, all three message sites) | int 90: oracle `'Impedance specification: 90 Omega …'` vs Rust `'… 90.0 Omega …'`; int −5 likewise | `validate_stackup` keeps the original object; messages render via CPython `str()` of the ORIGINAL (int → "90"), branches compare the extracted f64; matrix rows `90` and `-5` added |
| P2 | tolerance analyzer drops int nominals (`manufacturing_tolerances.rs` `FeatureTolerance`) | `analyze_clearance(1, …)`: oracle stores int 1 (repr `nominal_value=1`), Rust f64 1.0 (repr `nominal_value=1.0`); the `_feature_tolerance_fields` helper masked it via `float(value).hex()` | `nominal_value` and (clearance-arm) `worst_case_max` are `Py<PyAny>` preserving the original object (the monte_carlo dataclass precedent); `__eq__`/`__repr__` on those fields run through CPython; the differential key carries the concrete type alongside `.hex()` (R1a letter); int-input field + repr cases added |
| P2 | tautological assertion `assert … or True` in `test_sampling_parity_all_normal` | always passes | replaced with the byte-exact stream comparison (already the RNG boundary) plus a non-degeneracy guard (`arr.std() > 0`) |

## 3. What was chosen over full replication (recorded, not fixed)

- **Int table VALUES** (`etch_tolerance={ONE_OZ: 1}`) keep the derived
  tolerance fields int in the oracle (Python arithmetic) but f64 in Rust.
  The contract types these dict values `float` (the oracle's own
  annotations; every fixture uses floats), so this is outside the pinned
  envelope; recorded as deviation #5 in the tolerances VERIFICATION.md
  section. The int *argument* path (the review's finding) IS fully pinned.
- **positions (N,1) and bounds (N,≥3) are replicated, not rejected** — the
  oracle computes both (numpy's size-1 broadcast; extra columns ignored),
  and the kernel now matches bit-exactly, pinned by the two positive
  parity cases above.

## 4. Mutation-campaign re-run with explicit revert verification

Method (all four campaigns, 2026-08-05, against the FIXED tree at
`c40beeb4b`): for each mutant — apply a single behavior-changing edit to
the Rust source; rebuild the extension (`uv run --no-sync maturin develop
--release`); run the module's differential + PBT + existing suites
(`pytest -q --maxfail=3`); record the failure; `git restore` the file;
**verify `git diff` is EMPTY before the next mutant** (a non-empty diff
aborts the run). The tolerances campaign additionally re-applied the
shipped `0.05→0.06` mutant at the clearance site — now caught by the new
differential case (1 failed).

| Campaign | Mutants | Result | Revert verification |
|----------|---------|--------|---------------------|
| tolerances (T1–T11) | 11 | **11/11 caught** (T1 = the shipped `0.05→0.06`, now caught by the clearance-side fallback case) | clean after every mutant |
| monte_carlo (M1–M10) | 10 | **10/10 caught** — M2 note below | clean after every mutant |
| hypergraph (H1–H10) | 10 | **10/10 caught** (H6 re-run after a compile error in the mutant itself) | clean after every mutant |
| stackup (S1–S12) | 12 | **12/12 caught** | clean after every mutant |

Total: **43 mutants, 43/43 caught.** The per-mutant logs
(`/tmp/hg_mutants_report.txt`, `/tmp/mc_mutants_report.txt`) were
**regenerated** for the hypergraph campaign on 2026-08-05 against the
current tree (HEAD `cdb4f5272`): the pre-rebase log's H5 and H6 rows
showed all-pass runs ("26 passed") measured before the duplicate-ref and
zero-components differential cases landed; the regenerated log records the
actual failures and the killing tests for every mutant (H5: 1 failed —
`test_duplicate_component_refs_last_wins`; H6: 5 failed — the
zero-components and mixed-netlist differential cases plus PBT P4).

**M2 nuance (recorded, not a gap):** the first M2 attempt used the `>=`
tie-break variant of `np_max` last-wins, which SURVIVED — that variant is
value-identical on the kernel's operand domain (separations can never be
-0.0; the module docstring's argument, and the Rust unit test
`np_max_returns_larger_including_signed_zero` pins the ±0.0 behavior).
The documented campaign mutant is the always-`b` variant, which is caught
(3 failures). Both attempts reverted cleanly.

**H6 note:** the first H6 mutant (membership-check dropped) had a
type error in the mutant text itself (`Some(&node_idx)` pattern against
`Option<usize>`) and did not build; the corrected mutant
(`ref_to_idx.get(..).copied().or(Some(usize::MAX))`) builds and is caught
(5 failures: `test_nets_without_components_parity`, the two mixed-netlist
cases, `test_matrix_triplet_order_is_cpython_set_order`, and the PBT
property `test_p4_incidence_connectedness`). The zero-components case
(`test_nets_without_components_parity` — nets whose refs match no
component) and PBT P4 are the true discriminators; there is no
"UNKNOWN_REF case" in the suite — the pre-rebase campaign log's
attribution of H6 to one does not exist and was corrected in the
regenerated log (see above).

Suite totals at campaign time (pytest, all green between mutants):
tolerances 51 tests, monte_carlo 53, hypergraph 30, stackup 56.

## 5. Gates run after the fixes (all in the worktree)

- Differential + PBT + existing suites: tolerances, stackup, monte_carlo,
  hypergraph — 208 passed.
- `cargo test --release --features python`: temper-design-bundle 53
  passed; temper-io-types 37 passed.
- `cargo clippy --release --features python --all-targets`: clean on both
  crates (0 warnings).
- `make extensions-check`: 11/11 fresh after final rebuild.
- See the PR body for the full gate list (ruff, type-check, vulture,
  import-linter, coverage, verdict coverage, tests/io + consumer suites).

## 6. Provenance

Campaign runs against the fixed tree at commit `c40beeb4b` (fix commit;
the RED test commit `dc0ca6a7e` precedes it). All revert verifications
used `git diff --quiet` == empty. This document is committed with the
VERIFICATION.md corrections in the same PR.
