<!-- provenance: commit=f5e32cfda1b43f37a53034b8e770997a0820856d dirty=false -->

# run-B audit-lie reproduction and current-board state verification (2026-08-01/02)

**Date:** 2026-08-02 (measurements at base `f204007097e76f96827c76257afb3f72c35f1fb9`; board `pcb/temper.kicad_pcb` byte-identical to origin/main, sha256 `cf161bee832d…`).
**Branch:** `spike/gap2-runb-repro` (worktree `.claude/worktrees/agent-gap2-runb`).
**Context:** independent reproduction of the documented "audit lie" that motivated issue #523 gap 2 — the placer's scoped solve for K3/tank3 ("run-B", PR #564 / `docs/evidence/2026-08-01-k3-runb-not-validator-clean.md`) PASSED the solver's post-solve audit (`audit_domain_clearance`, center-to-center Euclidean distance) while FAILING the real REQ-SAFE-01 gate (`verify_iec60335_compliance`, exact copper-to-copper on pad geometry): 3 → 12 violations (C27 landed 0.32mm from U24; K3 violated C3/R60/C24) while the audit reported 0.

## TL;DR

- **Recovered:** the run-B candidate targets — K3 → board-file `(at 63.52 51.97)` rot 90, C27 → board-file `(at 44.44 236.56)` — plus the coordinate frame that makes them consistent with the doc's own measurements (board-file `(at x y)`; the parser's local frame subtracts board origin (20,20) and adds each footprint's rotated pad-bbox center offset).
- **Reproduced bit-exactly:** the headline lie. On the reconstruction (only K3/C27 moved, everything else at committed positions), C27/U24 center-to-center distance is **15.360mm** (≥ 8.0 bar → `audit_domain_clearance` reports NO violation for the pair) while C27/U24 **copper-to-copper is 0.320mm** (< 8.0 bar → the validator fires) — matching the documented "C27 landed 0.32mm from U24" to sub-micron precision. 7 of the 12 documented violation records (all C27-side pairs) reproduce to ≤ 0.001mm.
- **Reproduced structurally:** the documented "audit_domain_clearance 0 violations" is exactly what the *scoped* constraint generation the solve used produces — with `component_refs = {K3, C27}` (the FREE set), exactly one domain-clearance constraint is generated (C27<->K3 at 8.0mm), whose center distance is huge, so the audit returns 0 while the validator reports 27 records / 12 pairs on the same placement.
- **NOT fully recoverable:** the full run-B placement. The doc records only the two FREE targets; the "nothing hard-pinned, min-displacement" recipe may have moved other refs. Empirically the three K3-side documented pairs (C3/K3 5.94, K3/R60 5.07, C24/K3 4.971) are mutually inconsistent with any single K3 position at committed C3/R60/C24 positions (grid-searched over the local frame × all 4 rotations), so those refs moved in the real solve and their run-B positions are lost. The reconstruction therefore cannot reproduce the doc's exact 12-record / 9-pair tally.
- **Current-board state (task 3): all handoff claims verified.** REQ-SAFE-01 = 3 records / 1 pair / 3 intra, all K3-intra (G5LE-1 coil↔contact 3.5588mm vs the 4.0/6.0/8.0 bars); K3 at board-file (69.72, 29.0) rot 90; C27 staged off-board at (20, 272.75); board hash `cf161bee…`.

## 1. Method

1. `scripts/assert-base.sh origin/main` → OK (`f20400709`), then `uv sync --all-packages --inexact` + `make extensions` (11/11 fresh after freeing disk: the shared `target-shared` hit "No space left on device"; `uv cache prune` reclaimed ~20G).
2. Loaded the real board with the shared fixture (`tests/requirements/safety/_real_board_fixture.py::load_real_board_placement` → `parse_kicad_pcb(pcb/temper.kicad_pcb)` + `elec/domain_manifest.yaml` via `scripts/check_domain_partition.py`'s loader, compiled netlist via `make netlist`).
3. Applied the documented run-B targets to the placement copy (K3/C27 positions only; rotation for K3 unchanged at 90, C27 at 0).
4. Ran BOTH checks on the same placement:
   - `generate_domain_clearance_constraints` + `audit_domain_clearance` (the solver's post-solve audit path, mirrored from `placer/cp_sat/clearance_repair.py`), under both the scoped FREE-set `component_refs={K3,C27}` and the unscoped full-ref set.
   - `verify_iec60335_compliance` (the REQ-SAFE-01 gate).
5. Cross-checked every measured pair against the doc's table; scanned the K3 local-position space (35.0–70.0 × 15.0–55.0mm, 0.2mm grid, all 4 rotations) for a position reproducing the doc's three K3-side values with C3/R60/C24 fixed.

### Coordinate-frame trap (confirmed)

The handoff §6 warning is real and matters here: `Component.initial_position` is the pad-bbox CENTER in the local frame (board origin (20,20) subtracted, plus the footprint's rotated center offset), NOT the board-file `(at x y)`. The run-B targets are in board-file frame: K3 raw `(69.72,29)` → parsed `(56.82, 9.0)` (offset +7.1,0 rotated into +X at rot 90); C27 raw `(20, 272.75)` → parsed `(20.0, 252.75)` (symmetric pads, offset 0). The evidence that the run-B targets are board-file frame: the raw-frame reconstruction reproduces the doc's C27 pair measurements to 4 significant digits; the local-frame interpretation does not (it puts C27 ~40mm from U24, which cannot be 0.32mm copper).

## 2. Old-audit vs validator side-by-side (the lie)

Same reconstruction placement, both checks. Two audit rows are shown because the constraint set the audit runs on depends on how the solve scoped generation:

| check | constraints audited | result |
|---|---|---|
| `audit_domain_clearance` (scoped, `component_refs={K3,C27}` — what the run-B solve used) | 1 constraint (C27<->K3 @ 8.0mm) | **0 violations** — reproduces the documented claim |
| `audit_domain_clearance` (unscoped, all 159 classified refs) | 12,022 constraints | 3 violations: C27/R10 6.245, C27/U22 7.443, D2/K3 1.425 (center) |
| `verify_iec60335_compliance` (REQ-SAFE-01 gate) | — | **27 records / 12 pairs / 3 intra** |

The mechanism, confirmed in code: `audit_domain_clearance` recomputes `math.dist` between **centers** (documented in its own docstring as "a cheaper, weaker check"), while `verify_iec60335_compliance` measures **exact copper-to-copper** through `_CopperModel` on rotated pad geometry. A center-distance check cannot see a large-footprint component whose copper extends toward its neighbor.

### Headline pair — C27/U24

| quantity | value | bar | verdict |
|---|---|---|---|
| center-to-center distance | 15.360 mm | 8.0 | audit PASS (no violation) |
| copper-to-copper distance | **0.320 mm** | 8.0 | validator FAIL — documented 0.32, exact |

C27 is the axial tank cap (40mm pin pitch); its copper extends ~20mm from its center toward U24. `audit_domain_clearance` passes; `verify_iec60335_compliance` fires. This is the documented headline, reproduced.

## 3. Per-pair table — reconstruction vs documented run-B

Reconstruction = committed board with K3→(63.52,51.97) raw, C27→(44.44,236.56) raw, everything else at committed positions; validator measured (min over records for the pair). Doc column = the evidence doc's measured values.

| pair | recon (mm) | doc (mm) | delta | status |
|---|---|---|---|---|
| C27<->U24 | 0.3204 | 0.32 | +0.000 | **EXACT** |
| C27<->R1 | 1.5280 | 1.528 | +0.000 | **EXACT** |
| C27<->D4 | 4.6300 | 4.63 | −0.000 | **EXACT** |
| C27<->Q1 | 5.1226 | 5.123 | −0.000 | **EXACT** |
| C27<->R48 | 5.6750 | 5.675 | −0.000 | **EXACT** |
| C27<->R63 | 6.6829 | 6.683 | −0.000 | **EXACT** |
| C27<->U10 | 6.8704 | 6.87 | +0.000 | **EXACT** |
| C3<->K3 | 3.7300 | 5.94 | −2.210 | NOT reproduced (C3 moved in real solve) |
| K3<->R60 | 6.3229 | 5.07 | +1.253 | NOT reproduced (R60 moved) |
| C24<->K3 | ≥ 8.0 (not flagged) | 4.971 | — | NOT reproduced (C24 moved) |
| D2<->K3 | 3.3721 | n/a | — | extra in recon (D2 moved in real solve) |
| K3<->R74 | 7.6178 | n/a | — | extra in recon (R74 moved in real solve) |
| K3<->K3 (intra) | 3.5588 | n/a (not in doc's 12) | — | present in recon |

- 7 of the 10 documented pairs reproduce to ≤ 0.001mm — all C27-side. This is the honest core of the reproduction: the doc's most damning rows (C27 0.32mm from U24, and the five other C27 creepage breaches) are exactly reproducible from the documented targets alone.
- The 3 K3-side pairs are NOT reproducible from committed positions alone: a 0.2mm-grid scan over K3's local position × all 4 rotations found no single position satisfying C3/K3=5.94, K3/R60=5.07, C24/K3=4.971 simultaneously with C3/R60/C24 fixed (best-fit error ≥ 3.17mm). Conclusion: in the real run-B solve, C3/R60/C24 (and D2/R74) were displaced by the min-displacement objective; their run-B positions are not recorded anywhere in the repo (the branch was reset to origin/main after the finding; no board or script artifact survived). They are not fabricated here.
- The doc's "12 / 9" tally is therefore not fully reproducible: the reconstruction yields 27 records / 12 pairs (the 3 unrecoverable K3 pairs differ, and D2/R74 appear only because they stayed put in the reconstruction but moved in the real solve). What is reproducible — and asserted in the committed test — is the *class* of the lie and 7 of its 12 records.

## 4. Current-board state verification (handoff §3, measured vs claimed)

All measured at base `f20400709` (2026-08-02) on the committed board.

| claim (handoff §3, 2026-08-01) | measured | verdict |
|---|---|---|
| REQ-SAFE-01 = 3 violations / 1 pair, all K3-intra | 3 records / 1 pair / 3 intra, all K3<->K3 intra (DC_BUS<->LV_CONTROL: BASIC creepage, REINFORCED clearance, REINFORCED creepage) | **verified** |
| K3 G5LE-1 gap 3.559mm vs 4.0/6.0/8.0 bars | 3.5588mm; basic clearance 3.0 passes (3.559 > 3.0), the three bars 4.0/6.0/8.0 fail | **verified** |
| K3 at board (69.72, 29.0) rot 90 | raw `(at 69.72 29 90)` (parsed local (56.82, 9.0) rot 90) | **verified** |
| tank.c_tank3 (C27) staged off-board at (20, 272.75) | raw `(at 20 272.75)` (parsed local (20.0, 252.75)) | **verified** |
| Board hash `cf161bee…` | sha256 `cf161bee832d…` | **verified** |
| 159 classified components / 54 nets (fixture) | 159 of 169 (94.1%) / 54 of 162 | consistent |

One observation for the handoff: the fixture reports 159 classified components on 54 nets (full manifest) — the doc's "3/1 all K3-intra" holds on both the legacy boundary set and the full manifest set (verified identically on both).

## 5. Files

- `packages/temper-placer/tests/requirements/safety/test_runb_audit_lie.py` — 4 pytest cases: (1) scoped audit returns 0 on the run-B candidate; (2) C27/U24 fires at 0.320mm with center ≥ 8.0 (the lie in one pair); (3) all 7 documented C27 pairs reproduce to ±0.001mm; (4) the candidate's validator pair count exceeds the committed board's 1 pair. Ruff-clean. Requires the real board + netlist (skips with `RealBoardUnavailable`).
- `packages/temper-placer/tests/requirements/safety/_runb_reproduction_measurement.py` — the measurement script this doc's tables came from (runs both audits + the validator and prints the per-pair table). Ruff-clean; not collected by pytest.
- No changes under `packages/temper-placer/src/` — validation-only, per the task's standing constraint.

## 6. Honest limits

- The full run-B placement is not recoverable; only K3/C27 targets and 7 of 12 documented records reproduce. Everything else in this doc is labeled reconstructed vs recovered.
- The reconstruction's audit (unscoped) reports 3 violations — the real run-B solve's audit was run on its own scoped constraint set over its own solved positions (where R10/U22/D2 were kept farther by the box constraints), so the reconstruction's unscoped-audit rows are informative about the mechanism, not a claim about what the real solve's audit printed.
- No claim is made that run-B "should" have been accepted: the opposite. The reproduction's purpose is to pin down, with bit-exact numbers, why the solver's audit cannot substitute for the validator — the exact motivation for issue #523 gap 2.
