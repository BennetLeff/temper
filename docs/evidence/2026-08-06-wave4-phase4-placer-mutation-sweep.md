# Wave-4 Phase-4 placer (non-cp_sat) mutation sweep

Date: 2026-08-06
Branch: `feat/wave4-phase4-placer-rust` (rebased onto `origin/main`, base
`091203fd7`)
Kernel under test: `packages/temper-io-types/src/placer_core/placer_compute.rs`
(735 LOC, the pure-Rust home of `placer/adjustment.py`,
`placer/deterministic.py`, `placer/template.py` compute) exposed through
`temper_io_types.placer_*` in `src/placer_core/pybridge.rs`.

## Purpose

R1a/R1c/R1d are differential-and-property suites; this sweep answers the
anti-vacuity question those suites cannot answer for themselves: does any
of them actually break when the kernel is wrong? Ten mutations were applied
to the Rust kernel, each rebuilt into the installed extension, run against
the four placer suites (75 differential + 16 property/metamorphic tests,
plus the unit/PBT arm), and the failure confirmed before the source was
reverted. A mutation the suites do not catch is a suite gap, not a
disposition: the sweep's discipline is "close the gap by tightening the
differential, never by weakening the claim."

## Methodology (per mutant)

1. Apply a single-edit mutation to `placer_compute.rs` via an exact-string
   replace that asserts the target text occurs the expected number of times
   (a mutation that stops matching fails loudly instead of silently doing
   nothing).
2. `maturin develop --release` into the isolated worktree venv.
3. Run the four suites; classify by pytest exit code (CAUGHT = exit 1,
   ALL_PASS = bit-equivalent/survived and inspected).
4. Revert via `git checkout -- <file>` (never stash; the repo's stash guard).
5. Rebuild, re-run, and verify `git diff` is EMPTY (0 lines) and the suites
   are green again — the driver ends pristine, no infra-as-kill.

## Results

| ID | Kernel site | Mutation | Result | Discriminating failures (examples) |
|---|---|---|---|---|
| M1 | `apply_component_template` / `apply_parametric_template` rotation | R(−θ) → R(+θ) (both occurrences) | **CAUGHT** | `test_component_template_apply_matches` (all nonzero rotations), `test_p1_component_apply_is_bit_identical_to_the_oracle`, `test_mr2_rotation_periodicity_360k` |
| M2 | `apply_component_template` rotation bypass | `if rotation != 0` → `if true` (always rotate) | **CAUGHT** | `test_component_template_zero_rotation_signed_zero_pins_bypass` (the −0.0 edge only an always-rotate kernel destroys) |
| M3 | `py_mod` | floored modulo → Rust's truncated `%` | **CAUGHT** | `test_component_template_apply_matches` (negative rotations), `test_parametric_template_apply_matches`, `test_component_template_kernel_matches_oracle`, P3/P4/P1 arms |
| M4 | `apply_component_template` anchor offset | `rel = comp − anchor` → `rel = comp` (offset dropped) | **CAUGHT** | `test_component_template_anchor_is_not_first`, `test_p2_anchor_lands_exactly_at_the_anchor_point`, `test_p1_component_apply_is_bit_identical_to_the_oracle` |
| M5 | `apply_parametric_template` missing-anchor fallback | `0.5 * target` → `target` | **CAUGHT** | `test_parametric_template_default_anchor_center`, `test_parametric_template_kernel_default_anchor_matches_oracle` |
| M6 | `place_by_proximity` angle step | `2π / max(len,4)` → `2π / len` | **CAUGHT** | `test_place_by_proximity_no_zone` (all `max_distance` arms), `test_place_by_proximity_ref_not_in_netlist`, `test_place_by_proximity_board_center` |
| M7 | `place_by_proximity` spiral distance | `8.0 + (i//4)*3.0` → `8.0` (ring term dropped) | **CAUGHT** | `test_place_by_proximity_many_refs` (9 refs, multiple rings) |
| M8 | `place_by_proximity` zone clamp | lower bound dropped (`py_max(x0,·)` removed) | **CAUGHT** | `test_place_by_proximity_zone_clamp_fires` (added in this PR — see below) |
| M9 | `adjust_for_congestion` influence boundary | `dist < influence_radius` → `dist <= influence_radius` | **BIT-EQUIVALENT** (not catchable; see analysis) | — |
| M10 | `adjust_for_congestion` dtype chain | `if is_f32` → `if true` (f32 chain computed in f64) | **CAUGHT** | `test_normalized_push_within_radius`, `test_distance_just_inside_radius_pushed`, `test_multiple_bottlenecks_accumulate` (the f32 arms), `test_float32_normalized_chain`, `test_float32_exact_spot_store_semantics` |

Every CAUGHT mutant was reverted and the rebuilt pristine extension passed
all suites (99 tests: the four suites + the pre-existing placer unit tests +
`test_mcu_subsystem`), with `git diff` confirmed EMPTY before the next
mutant. The driver and the full per-mutant log are the evidence; the
per-mutant discriminating test names above are the heads of each run's
failure list.

## M9: the bit-equivalent boundary (recorded, not a gap)

M9 changes the influence-radius comparison from `<` to `<=`. At the exact
boundary (`dist == influence_radius == 10.0`) the oracle's normalized push
computes `force = push_strength * (1.0 − dist/influence_radius) =
2.0 * (1.0 − 10.0/10.0) = 2.0 * 0.0 = 0.0` exactly (both the division and
the subtraction are exact on the double 10.0). The displacement is then
`force * dx / dist = ±0.0`, and `px + ±0.0` is bit-identical to `px` for
every reachable value (the only IEEE sign-flip is `-0.0 + +0.0 = +0.0`,
which requires a −0.0 position *and* a specific dx sign — not reachable
from the differential fixtures, and pinned by reasoning rather than by
adding a −0.0-at-boundary fixture that the oracle's own arithmetic would
make indistinguishable anyway). So `<` and `<=` are behaviorally identical
on every input the suites drive: the push the `<=` mutant enables is an
exact-zero displacement. The suites correctly report the two kernels
bit-identical; this is a *finding* (the boundary distinction is
IEEE-invisible given the force formula), recorded rather than chased.

## Anti-vacuity gap found and closed during the sweep

The RED-committed differential drove zone clamping only with fixtures whose
grids/spirals stayed inside the zone bounds — the "clamps" assertions were
vacuous for the clamp code path. Two fixtures were added so clamping
provably fires:

- `test_place_by_proximity_zone_clamp_fires` — a 5×5 mm zone whose spiral
  distances (≥ 8 mm) overflow every bound; asserts both arms equal, all
  positions within [0,5], and the i=0 placement lands exactly on the
  clamped upper bound. M8 (lower clamp dropped) fails this test.
- `test_place_in_zone_center_grid_clamp_fires` — a 20×20 mm zone whose
  centered grid spills the lower-left corner; asserts the i=0 placement
  lands exactly on (0,0).

The sweep caught M8 only after these fixtures landed; before them the
clamp-mutant class would have survived. This is the second time the
sweep's discipline ("a mutation the suites do not catch is a suite gap")
paid for itself.

## Oracle drift found and corrected (also in this PR)

While validating the sweep's fixtures, a verbatim-copy defect was found in
the RED commit: `_placer_adjustment_py_oracle.py` carried a duplicate
`from __future__ import annotations` (a copy artifact; the pinned source at
`17553437d` has one). The duplicate was semantically inert (the
differentials were green) but violated the oracle's verbatim contract. It
was removed; `scripts/oracle_hashes.json` was regenerated (the adjustment
pin moved). The deterministic and template oracles were verified byte-verbatim
against `17553437d`.

## Pristine-rebuild evidence

After the last mutant (M10) was reverted:

```
$ git diff --stat packages/temper-io-types/src/placer_core/placer_compute.rs
(0 lines — empty)

$ pytest <the four suites + unit tests + test_mcu_subsystem>
============================== 99 passed in 2.71s ==============================
```

The driver ends with the source pristine and the extension rebuilt from
that pristine source.
