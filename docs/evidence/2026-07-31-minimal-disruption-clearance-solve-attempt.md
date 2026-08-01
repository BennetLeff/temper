# Minimal-disruption clearance solve attempt: pinned-refs API added, board still not placement-solvable to 0

<!-- provenance: commit=4a387393ec9e4626fa2ebbf044ecc029ec9e003d dirty=true (base commit = origin/main at the time of measurement; the numbers below are produced on branch codex/repair-generated-plan-index on top of this base) -->

**Date:** 2026-07-31
**Scope:** `pcb/temper.kicad_pcb` read-only throughout. Candidate placements written to
`/var/folders/.../T/w513-solve-*/` scratch only, never to `pcb/`. The one code change that landed
(``solve_placement(fixed_positions=...)``, a hard-pin API) is a **capability addition** for
issue #504's minimum-displacement loop, tested in
`packages/temper-placer/tests/placer/cp_sat/test_fixed_positions.py`; it changes nothing when
unused.

**Base:** branch `codex/repair-generated-plan-index` (PR #513) at `f350f4daa`, origin/main
`4a387393e` merged in (post-#460 copper-aware bbox constraint). `make netlist` run;
`elec/build/default.net` digest `736b01f0e07e…`.

---

## 0. Why this session exists

PR #513 is red on `Requirements Tests` because the real board carries
**123 REQ-SAFE-01 violations across 86 pairs at the enforced 12.6mm reinforced creepage** (PD3;
the PD2/8.0mm exception is not earned until the enclosure prerequisite is verified — see
`docs/evidence/2026-07-30-pd2-enclosure-decision.md` and the `clearance.py` module comment).
Issue #504 asks for a **minimum-displacement or route-aware placement/re-routing loop**, and
explicitly warns *"Do not write the existing free CP-SAT reshuffle into the routed PCB: it clears
movable placement pairs but reproducibly increases routed shorting_items and unconnected_items."*

The prior evidence (`docs/evidence/2026-07-30-copper-aware-domain-resolve.md`) identified the
unattempted next step: *"pinning every component not involved in a domain-crossing violation to
its current position and re-solving only the violating neighborhood… was not attempted here…
the CP-SAT encoder has no exposed 'fix these refs, free those' API today."*

This session adds that API and runs the experiment.

---

## 1. What was added

`solve_placement(..., fixed_positions: dict[str, (x_mm, y_mm, rot_0_3)] | None)` — **binding**
equality constraints (`x_center == pin`, `y_center == pin`, `rot == pin`), unlike
`hint_positions` (soft `AddHint`). Unknown ref raises `ValueError` (a silent skip would freeze
nothing and fake "minimal" displacement). Four tests pin the behaviour:
`test_fixed_positions.py` (pinned ref stays exactly at its position; two pinned refs keep
relative placement; unpinned refs may move; an off-board pin reports `infeasible`, not ignored).
Encoder/domain-clearance/model suites still pass (64 tests, plus the 4 new).

## 2. Baseline (reproduced)

```
123 REQ-SAFE-01 violations across 86 pairs (11 records intra-footprint)
80 refs involved in violations; 159 components matched; 10 unclassified
full-set (54-net) violations: 123
```

Matches CI exactly.

## 3. Experiment A — minimal-disruption solve (pin non-violating refs, free the 80 violators)

Full classified-domain constraint set (11,856 domain-clearance + 696 keep-away = **12,552
constraints**), 89 refs pinned at current positions with real board rotations, 80 violators
free, `hint_positions` = current positions, `seed=0`, `timeout=300s`.

**Result at BOTH 12.6mm (enforced) and 8.0mm (PD2 target): `status=infeasible` in ~0.7s,
empty unsat core.**

### Root cause, measured (not assumed)

The current board is **not a feasible point of the CP-SAT box model at all**, with or without
clearance constraints:

- **Pin-everything, zero extra constraints → `infeasible`** (verified with real rotations, 99
  refs at 90/180/270).
- Direct geometry check at current positions: **12 refs' copper-aware boxes fall outside the
  board bounds** (the model enforces a 0.5mm edge margin), and **32 box pairs overlap** —
  59 refs total, of which **35 are in the 89-ref pinned set** (`C3`, `C4`, `C8`, `C10`, `C14`,
  `C24`, `J1`, …).

Why: the post-#460 box is the *whole-component* copper-aware envelope (courtyard ∪ pads),
computed to *contain* all of a part's copper — deliberately conservative. Two adjacent real
parts can have overlapping envelopes while their true copper does not touch, and an edge
connector's envelope can legitimately reach the board edge. The model therefore cannot hold the
current physical layout as a feasible point; pinning any subset that includes such refs is
infeasible by construction. **The "pin non-violating refs, free the violators" loop cannot run
until the encoder can exempt pinned refs from NoOverlap2D/edge bounds** (or until a per-pad /
per-domain copper model replaces the whole-component box — the higher-cost option #460's doc
already names).

## 4. Experiment B — full reshuffle at the enforced level (re-confirming #504's warning)

Same constraint set, **no pins** (hint-only, the 2026-07-30 methodology), 12.6mm matrix:

```
status=optimal  solve_time=32.1s  placed=169/169
free-ref displacement: min=8.6  median=121.5  max=235.1mm  (full-board reshuffle)
```

**Validator, gate fixture pointed at the candidate: 123 → 11 violations.** The 11 remaining
records are **all intra-footprint**:

| ref | metric | measured | required | note |
|---|---|---|---|---|
| C6 | creepage | 8.00 | 12.6 | intra |
| K1 | creepage | 8.00 | 12.6 | intra |
| K2 | creepage | 3.56 | 12.6 | intra (also fails 6.3 basic creepage + 6.0 clearance) |
| K3 | creepage | 3.56 | 12.6 | intra (same) |
| T1 | creepage | 9.10 | 12.6 | intra |
| U3 | creepage | 8.56 | 12.6 | intra |
| U7 | creepage | 8.10 | 12.6 | intra |

Every inter-component pair the validator can see is cleared at the enforced level. The residue
is exactly the placement-irreducible isolator set — the same parts `find_intra_footprint_domain_
conflicts` flags and the handoff doc's Phase-2 part selection addresses (C6 placeholder Y-cap,
K1–K3 relay family, T1 CT, U3/U7 optocoupler packages). **No placement can fix these** (a
component cannot be separated from itself).

**DRC (kicad-cli, single runs; shorting scatter is documented ±15, median-of-5 in the prior
doc): baseline shorting=83, candidate shorting=125 (+42).** Unconnected=0 both (this harness
counts; the prior doc's +30 unconnected was measured on the then-current board). This **reconfirms
issue #504's central warning**: the reshuffle that clears the movable pairs strands/shorts real
routing copper on this fully-routed board (2,338 segments / 48 vias / 96 zones). It is not a
landable board without a re-route pass.

At 8.0mm (PD2 target) the same free solve hit `status=unknown` at 300s (not proven infeasible;
CP-SAT simply did not finish). At 8.0mm the intra-footprint floor shrinks (K1 8.00 / T1 9.10 /
U3 8.56 / U7 8.10 / C6 8.00 all pass at 8.0) but **K2/K3 at 3.56mm still fail**, so even the
PD2 architecture leaves placement-irreducible isolator records until the relay footprints change.

## 5. Answer to the designated question

**Is there a solve/reroute path that produces a board meeting REQ-SAFE-01 at 8.0mm PD2 without
breaking the netlist/board gates? No, with the current machinery:**

1. The minimal-disruption (pinned) variant is **structurally blocked**: the current board is not
   a feasible point of the CP-SAT box model, so non-violating refs cannot be frozen at their
   current positions (Sec 3).
2. The free reshuffle clears every placement-fixable pair (123 → 11 at 12.6mm; the same
   mechanism clears the inter-component set at 8.0mm modulo K2/K3's footprint) but is a
   full-board reshuffle (median ~121mm) that **regresses routed DRC shorting (+42)** — the exact
   failure mode issue #504 documents. No re-route pass exists in this repo's committed
   machinery that operates on the real routed board (router_v6 builds a *minimal* PCB from the
   netlist, not a re-route of the existing 2,338-segment board).
3. Even a perfect solve leaves the **intra-footprint isolators** — 11 records at 12.6mm,
   K2/K3 at any threshold ≤3.56mm. Those require part/footprint selection (handoff doc Phase 2),
   not placement.

**Nothing was written to `pcb/temper.kicad_pcb`.** This session therefore does NOT commit a
board, and `power_pcb_dataset/drc_ceiling.json` is untouched (no board change → no re-measurement
trigger). The Requirements Tests check remains red on PR #513 for the documented, issue-tracked
reason (#504, #517, #518): the board's clearance debt is real, partially placement-fixable only
at the cost of routing integrity, and fully resolvable only via isolator part selection +
domain-first floorplan + re-route (handoff doc Phase 2–4).

## 6. What is needed next (the missing pieces, stated plainly)

1. **Encoder: pinned-ref exemption from NoOverlap2D and board-edge bounds.** The pinned
   positions are physically legal; the whole-component box model cannot represent them. Either
   exempt pinned refs from the base box constraints (they are, by construction, already-placed
   parts) or move to a per-pad / per-domain copper box model (#460's "higher-cost option").
2. **A re-route pass on the real routed board** — router_v6 currently routes a synthetic minimal
   PCB; nothing re-routes the existing 2,338-segment board after a placement change.
3. **Isolator part selection** (C6, K1–K3, T1, U3, U7) per the handoff doc Phase 2 — the only
   way to remove the intra-footprint floor.

## 7. Reproduction

```bash
git fetch origin && git checkout codex/repair-generated-plan-index
uv sync --all-packages --inexact && make netlist
# API tests:
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_fixed_positions.py -v
# Experiment A (pinned): scratch_solve_driver.py (session scratch, driver at repo root)
uv run python scratch_solve_driver.py --timeout-ms 300000          # 12.6mm pinned -> infeasible
uv run python scratch_solve_driver.py --timeout-ms 300000 --margin 8.0  # 8.0 pinned -> infeasible
# Experiment B (free reshuffle, enforced level):
uv run python scratch_solve_driver.py --timeout-ms 300000 --free-all
# pin-everything / model-feasibility probes (Sec 3): inline snippets in session log
```

`scratch_solve_driver.py` is session scratch at the branch root (not committed); the repo-root
`git status` shows it as untracked, and it is excluded from the commit.
