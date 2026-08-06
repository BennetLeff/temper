# Wave 4 Phase 5 mutation sweep — report / requirements / explainability — 2026-08-05

<!-- provenance: commit=8521b6caaa3de5241e8691dd87a960fc9e30b419 dirty=false (re-pointed 2026-08-05: the sweep's measurement tree 63dedc87b10eefa01e6a0673c11cb2f5a532889d was a pre-rebase branch commit, orphaned by force-push; the half_even pins and this sweep evidence landed on main at 8521b6caaa3de5241e8691dd87a960fc9e30b419, which is the cited commit; dirty=false because the evidence is committed there) -->

**Base commit:** the TDD-RED commit `ba3d857dd` (post-rebase hash). The
sweep ran against the measurement tree with the `half_even` fixture added
during the sweep itself (the measurement-tree commit `63dedc87b` was
orphaned when the branch was rebased; the half_even pins and this evidence
landed on main at `8521b6ca`, which the header cites): oracles +
differential/PBT suites, branch `feat/wave4-phase5-report-requirements-explain-rust` in the
isolated worktree `/private/tmp/wt5-report`.

**Task.** Run the R1f anti-vacuity sweep for the Phase-5 report /
requirements / explainability slice: mutate the Rust, show the differential
**fails**, revert, and record every mutation and what caught it. The prior
sweep results were lost when the worktree was deleted mid-session; this is
the replacement run, executed against the committed GREEN state (13
mutants, all reverted; the tree was byte-clean at the end of every revert).

## Mutant ledger

| # | Mutant | Site | Suite that caught it | Failures |
|---|--------|------|----------------------|----------|
| M1 | pyfmt `{:.N}` replaced by `x*m -> round -> /m` (round-half-up at exact `.5` boundaries) | `temper-io-types/src/pyfmt.rs` | explainability trace 8.25 pin; **report arm closed by new half-even fixture (below)** | 2 |
| M2 | JSON `issue_count` leaf typed `f64` instead of `int` (`5.0` vs `5`) | `report.rs` `format_json_data_impl` | `test_formatter_rust_differential.py` JSON leaf-type arm | 2 |
| M3 | text formatter band `"="*80` -> `"="*79` | `report.rs` `format_text_impl` | formatter text byte-identical + layout pins | 2 |
| M4 | benchmark weights `0.4/0.3/0.3` -> `0.5/0.25/0.25` | `report.rs` `calculate_benchmark_result_impl` | generator differential + PBT balanced-formula pin | 3 |
| M5 | `why()` separator `" because: "` -> `": "` | `explain.rs` decision `why` | `test_decision_rust_differential.py` byte-identical | 2 |
| M6 | `should_log` gate `epoch % interval == 0` -> `== 1` | `explain.rs` `explain_should_log` | logger differential modulo pins | 3 |
| M7 | `compose_traces` fold order reversed (`insert(0, …)`) | `explain.rs` `explain_compose_traces` | trace differential + PBT monoid order law | 1 |
| M8 | markdown heading `"#### Decision History"` -> `"#### Decision Hist"` | `explain.rs` component report | markdown differential byte-identical | 2 |
| M9 | same-domain pairing killed (`if domain_a == domain_b` -> `if false`) | `req_safe_01.rs` `domain_boundary_pairs_vec` | clearance differential same-domain cases | 3 |
| M10 | copper distance biased `+1e-9` | `req_safe_01.rs` `copper_distance` | clearance differential `measured_mm` bit pins | 3 |
| M11 | report sort reversed (worst-last) | `req_safe_01.rs` `format_clearance_report` | clearance differential worst-first pins | 3 |
| M12 | IEC matrix `min_clr` halved (violations silently forgiven) | `req_safe_01.rs` `req_safe_01_verify_iec60335` | clearance differential verify_iec pins | 2 |
| M13 | origin-modelled WARNING text clause dropped | `req_safe_01.rs` check core | clearance differential WARNING-record comparison | 2 |

All 13 mutants **failed at least one differential test** and were reverted
with `git checkout`; every revert was followed by a rebuild and a green
re-run of the affected suite.

## One survivor — and the gap it closed (M1)

M1's first run targeted the report suites only and **survived**: no report
fixture hit an exact decimal `.5` boundary after `×10` scaling, so the
round-half-up and round-half-even variants agreed on every rendered value.
The explainability arm (the trace `8.25 -> "8.2"` pin) caught it.

Per the guide's precedent ("a differential that has never been shown to
fail is not evidence"; survivors are closed by adding discriminating cases,
not by lowering the claim), the report arm was hardened instead of accepted
as-is: `test_formatter_rust_differential.py` gained a `half_even` fixture
(`total_elapsed_ms=8.25`, `elapsed_ms=2.25`) that both the text and HTML
renderers format through `py_float_fmt_1`. Re-running M1 against the
report-only arm then failed (2 failures: `Runtime: 8.3ms` vs `8.2ms`).
The mutant class is now caught on **both** surfaces.

Note the fixture first FAILED against the then-installed `.so`: after the
sweep's last revert the extension still carried the M1 mutant build
(mutation build -> revert source -> no rebuild). Rebuilding the clean crate
made the fixture green — recorded here so a future sweep rebuilds after the
final revert instead of reporting a phantom divergence.

## Integrity notes

- Every mutant applied exactly once (script asserted `count==1` per edit
  target; ambiguous sites were disambiguated with surrounding context).
- No oracle file was modified by the sweep; the only test change is the
  `half_even` fixture above.
- The sweep ran against the committed GREEN state: 126 report +
  explainability + clearance differential/PBT tests, all passing before
  and after the sweep.
