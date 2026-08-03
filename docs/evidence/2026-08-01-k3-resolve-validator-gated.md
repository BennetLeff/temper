<!-- provenance: commit=87df36a223472967624648372bde8a21c61ba02a dirty=false -->

# K3/tank3 resolve — validator-gated solve + gate verification (issue #523 re-solve)

**Date:** 2026-08-02
**Branch:** `feat/k3-resolve-validator-gated-2` (worktree `.claude/worktrees/agent-resolve-gated-2`),
from `origin/feat/validator-aligned-solve-audit` (`19e02653b`, the gap-2 PR #584 tip).
**Issue:** #523 — the K3 RT314012 relay landing; this step is the issue's
**re-solve**: wire the gap-2 validator-aligned audit at the production repair
caller, run the production repair recipe, and gate-verify the solved
placement. **Board write (pcb/**) and the `drc_ceiling.json` re-measurement
are deliberately NOT done — they await the owner's GO per the evidence docs'
GO/NO-GO convention.**

## 1. Salvaged-wiring status

Two prior dispatches of this task died to provider stream errors; the second
left an uncommitted caller-wiring patch (`/tmp/a5_wiring.patch`, 2 files:
`cli/__init__.py` +10, `placer/cp_sat/clearance_repair.py` +81) staged in this
worktree.

**Salvage verdict: the patch applied cleanly against the pre-rebase gap-2 tip
(the gap-2 branch's #578 rebase did NOT touch these two files — `git apply
--3way` was unnecessary; the staged diff was byte-identical to the patch).**
Review found the wiring correct against the contract:

- `validator_input={"placement": placement, "voltage_domains":
  voltage_domains}` reaches `solve_placement` from
  `run_clearance_repair_solve` (both names are in scope as function
  parameters; call site ~line 352).
- `cli/__init__.py`'s optimize path carries a **precise TODO, not a
  half-wiring**: that path builds only netlist/board/constraints from
  `parse_kicad_pcb` and does not construct the validator-shape placement +
  voltage_domains map, so passing `validator_input` would raise `ValueError`
  on the missing keys. Half-wiring deliberately not done (contract: "else a
  precise TODO — don't half-wire").
- The classified result (hard/intra/coverage-gap buckets) surfaces on
  `ClearanceRepairReport` (`validator_audit` + convenience counts).
- The center-distance audit (`audit_domain_clearance`) stays untouched.

**One defect found and fixed in review (committed as a separate follow-up):
the unconditional wiring made the loop re-raise the audit's hard-failure
`RuntimeError`, which preempted the loop's own `gap` status for the
constraint-model-gap class — two existing synthetic tests
(`test_repair_reports_constraint_model_gap_honestly`,
`test_max_rounds_caps_loop`) went red. Fixed by converting the audit hard
failure into the loop's documented `gap` status (§3).**

## 2. Behavior decision — round-abort hard failure (explicit in code + docstrings)

**Decision: fail-closed and round-aborting, carried on the report as `gap`**
(the handoff's option (b), chosen because the loop's `gap` status exists for
exactly this class and the two existing synthetic tests assert it):

- The REQ-SAFE-01 validator audit runs inside every `solve_placement` round
  (via `validator_input`), and a HARD failure (a constraint-covered inter
  pair the exact-copper validator still flags on a feasible/optimal solve)
  **raises `RuntimeError` inside `solve_placement`** — preserved, so any
  caller that does not catch it fails closed by construction.
- `run_clearance_repair_solve` **catches** that raise, terminates with
  `status="gap"` naming the offending pair(s), and attempts **no further
  rounds** — a round-1 hard failure aborts the whole repair. The report is
  loud and never claims repairability; the caller gets the evidence on the
  report instead of an exception.
- Intra-footprint straddlers and coverage gaps are **reported, never
  raised** (`validator_audit` buckets on the report).

This is documented in the module docstring, the report docstring, and the
`Raises` section of `run_clearance_repair_solve`.

## 3. Wiring change (this branch's delta over the gap-2 tip)

| commit | change |
|---|---|
| `3f1a5663d` | Salvage + review of the dead dispatch's wiring: `validator_input` wired unconditionally into `run_clearance_repair_solve`'s `solve_placement` calls; `ClearanceRepairReport` gains `validator_audit` + `validator_hard_failures` / `validator_intra_footprint` / `validator_coverage_gaps` / `validator_geometry_trusted`; CLI optimize path gets the precise TODO. |
| `9d03c1cd7` | Round-abort decision: catch the audit hard-failure `RuntimeError` in the loop, convert to `status="gap"` naming the pair(s), stop the repair (fail-closed). Fixes the two synthetic tests regressed by the unconditional wiring. |

Tests after the fix (`tests/placer/cp_sat/test_clearance_repair.py` +
`test_validator_audit.py`): **42 passed, 1 failed** — the 1 failure is the
documented pre-existing `test_checker_copper_distance_is_lower_bound_on_origin_distance`
(fails identically on origin/main per the gap-2 evidence doc).

## 4. Recipe used (and which variant)

Two runs, both on the committed board (read-only), both with
`validator_input` from the real board (full-classification placement +
full voltage-domain map via `_real_board_fixture.load_real_board_placement`):

**Run A — production caller wiring verification** (`k3_resolve_gated_solve.py`):
`run_clearance_repair_solve(pcb, full, full_vd, timeout_ms=180000, seed=0,
max_rounds=4, max_displacement_mm=60.0, chain_exempt_pairs=None)`. 12,022
domain-clearance + 530 keepaway constraints, nothing hard-pinned,
min-displacement to current, ≤60mm cap, fixed rotations. **Note:
`run_clearance_repair_solve` does not accept `fixed_copper`** (not part of
its interface), so this run omits the fixed-copper piece of the run-B recipe.

**Run B — the exact wall-spike-proven variant (the candidate)** (`k3_resolve_gated_variantB.py`):
direct `solve_placement` replicating `gap2_wall_measure.py`'s variant B
**exactly** — nothing pinned, min-displacement to current,
`max_displacement_mm=60.0`, every ref's rotation pinned, `fixed_copper`
WITHOUT zone items (`free_refs={K3,C27}`, margin 0.05), full 12,022 +
530 constraint set, seed 0, 180s, hints = current positions — **plus
`validator_input`** (the gap-2 wiring under test). This is the variant the
wall spike (`docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md`) proved
feasible and validator-clean, and the handoff said to prefer if ambiguous.

**The candidate is Run B.** Run A is reported as the wiring-verification run
through the production caller (validator audit fires and buckets surface on
the report), but its placement differs because the loop caller cannot express
fixed-copper — hoisting fixed-copper into the repair loop is a documented
follow-up (§8).

## 5. Candidate table

### 5.1 Solved positions (Run B — exact spike reproduction)

| ref | current board | solved | Δ | rot |
|---|---|---|---|---|
| K3 | (56.82, 9.0) | (58.08–59.22, 11.18) | ~2.7–3.5mm | 1 (90°) |
| C27 | (20.0, 252.75, staged off-board) | **(28.62, 222.0)** | ~34mm, **ON-BOARD** | 0 |

C27 lands exactly at the spike's predicted (28.62, 222.0) — **verified**.
K3's x shows the documented run-to-run `feasible`-solve objective variation
(58.08 first run, 59.22 second; the spike recorded 58.08); C27 is stable at
(28.62, 222.0) in both runs. Total displacement 5504–6839mm across all refs
(feasible, not proven-optimal).

### 5.2 Validator audit buckets (Run B, the candidate)

| bucket | expected | measured |
|---|---|---|
| `hard_failures` | `[]` | **[]** ✓ |
| `coverage_gaps` | `[]` | **[]** ✓ |
| `intra_footprint` | 3 records, all K3 | **3 records, all K3<->K3** (G5LE-1 3.5588mm vs 4.0/6.0/8.0 bars) ✓ |
| `covered_pair_count` | — | 11,571 |
| `validator_violation_count` | 3 | 3 |
| `geometry_trusted` | True | **True** (no pad-less components, 0 pairs origin-modelled) |
| `clean` | True | True |

Same 3 K3-intra records as current main — 0 new inter-component REQ-SAFE-01
violations. (Run A through the production caller reports identical buckets:
hard=0, intra=3 K3, gaps=0, geometry_trusted=True, `status=intra_only`.)

### 5.3 Gate figures vs required (all measured with the named tool)

DRC gates measured with `temper_placer.validation._drc_api.run_drc`
(kicad-cli **10.0.4**, `--all-track-errors`, N=5 samples; the reproducible
invocation per `_drc_api.py` — the same tool the run-B doc and the
drc_ceiling protocol use). Candidate written to a **/tmp copy** of the board
(`write_placements_to_pcb` with `board.origin` added — CP-SAT local frame →
absolute, the pd2-resolve write convention; re-parse round-trip verified:
C27→(28.62, 222.0), K3→(59.22, 11.18) exact). `pcb/**` untouched.

| gate | baseline (unmodified board) | candidate | required | verdict |
|---|---:|---:|---:|---|
| REQ-SAFE-01 (validator, exact copper) | 3 / 1 (K3-intra) | **3 / 1** (K3-intra only) | ≤ 3/1 | **PASS** |
| `courtyards_overlap` (kicad-cli DRC) | 11 | **10** | ≤ 11 | **PASS** |
| `shorting_items` (kicad-cli DRC) | 199–200 | **198** | ~200 (ceiling 202) | **PASS** |
| `solder_mask_bridge` (kicad-cli DRC) | 169 | 152 | — (informational) | improved |
| `hole_clearance` (kicad-cli DRC) | 138 | 111 | — | improved |
| `clearance` (kicad-cli DRC) | 499–503 | 339 | — | improved |
| `total_errors` (kicad-cli DRC) | 1043–1048 | 838 | — | improved |
| fixed-copper audit (shorting proxy for free refs) | — | **0 violations** (K3/C27 pads vs fixed copper, no zones) | 0 | **PASS** |

The candidate **improves every DRC category** vs the current board — no
regression in any measured gate. (A shapely `check_overlap` courtyard proxy
in `k3_resolve_gated_gates.py` overcounts vs kicad-cli — baseline 34 by the
proxy vs 11 by `run_drc` on the same board — so it is reported with the tool
named as a pre-write sanity check only; the kicad-cli figure is the gate.)

### 5.4 The 4 consistency gates (board untouched → main's values)

| gate | value |
|---|---|
| `check_copper_net_consistency.py` | **PASSED** — 0 violations across 2482 copper item(s) and 515 pad(s) |
| `check_footprint_drift.py` | **PASSED** — 0 violations across 169 matched component(s) |
| `check_domain_partition.py` | **PASSED** — 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects, 0 board-interface contract violations |
| `check_pad_orientation.py` | **PASS** — no unrotated pad bodies, no intra-footprint copper overlaps |

Plus `check_measurement_provenance.py`: **PASSED** (board hash matches the
recorded ceiling hash — measurements are on the committed board).

## 6. What remains (owner decisions)

- **Board write + `drc_ceiling.json` re-measurement** — deliberately NOT
  done (pcb/** read-only, GO/NO-GO convention). The candidate placement here
  is a solved placement, not a written board. When the owner gives GO: write
  Run B's positions, re-measure DRC (120 samples, ceiling protocol) and
  update `drc_ceiling.json` in the SAME PR per AGENTS.md. Expected: no
  ceiling rise (candidate improves every category; the recorded ceiling
  categories shorting 202 / courtyards 11 / solder_mask 169 / clearance 415 /
  hole_clearance 129 are all comfortably cleared by the measured candidate
  values 198 / 10 / 152 / 339 / 111).
- **run C / gap 1 (zone-inclusive fixed-copper solve)** — still open. The
  run-B recipe drops zone items; the zone-inclusive variant is infeasible
  even with the #567 polygon-exact zone encoding. Until gap 1 lands, the
  written board would carry the documented courtyards/zone caveat (the
  candidate's improved numbers are with zones excluded from fixed-copper).
- **run-C/gap-1 + the K3 RT314012 elec unblock** — the actual relay swap is
  still pending; this solve re-places the G5LE-1-carrying K3, it does not
  swap the part.
- **Hoist `fixed_copper` into `run_clearance_repair_solve`** (or wire
  `validator_input` at a direct `solve_placement` caller) so the production
  caller can express the full run-B recipe — Run A vs Run B differ only by
  the fixed-copper piece.
- **CLI optimize path** — TODO in place (`cli/__init__.py`): pass
  `validator_input` once that path constructs a validator-shape placement +
  voltage-domain map (hoisted into a shared production loader).

## 7. Files

- `docs/evidence/k3_resolve_gated_solve.py` — Run A (production caller,
  repair loop) measurement; `k3_resolve_gated_solve_summary.json` (output).
- `docs/evidence/k3_resolve_gated_variantB.py` — Run B (exact wall-spike
  variant, `validator_input` wired) measurement;
  `k3_resolve_gated_variantB_summary.json` (output incl. full placement).
- `docs/evidence/k3_resolve_gated_gates.py` — REQ-SAFE-01 re-run,
  courtyard-overlap proxy (sanity), fixed-copper audit, 4 consistency gates.
- `docs/evidence/k3_resolve_gated_drc.py` — kicad-cli DRC baseline +
  candidate (N=5) on a /tmp copy of the board.

## 8. Reproduction

```bash
make netlist && make extensions
cd packages/temper-placer   # for fixture import resolution
uv run --no-sync python ../docs/evidence/k3_resolve_gated_variantB.py   # Run B solve
uv run --no-sync python ../docs/evidence/k3_resolve_gated_gates.py      # validator + consistency gates
uv run --no-sync python ../docs/evidence/k3_resolve_gated_drc.py        # kicad-cli DRC baseline + candidate
# expected: status=feasible; C27 -> (28.62, 222.0); hard=[], gaps=[],
# intra=3 (K3); courtyards_overlap 11->10; shorting_items 199-200 -> 198
```
