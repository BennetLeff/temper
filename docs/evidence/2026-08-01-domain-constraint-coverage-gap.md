<!-- provenance: commit=f204007097e76f96827c76257afb3f72c35f1fb9 dirty=false (measured on a clean origin/main tree; every figure in this doc was taken at f20400709, board pcb/temper.kicad_pcb unchanged) -->

# Gap-2 coverage quantification: domain-clearance constraint coverage on the current production board (2026-08-02)

**Date:** 2026-08-02
**Branch:** `spike/gap2-coverage-gap` (worktree `.claude/worktrees/agent-gap2-coverage`),
from `origin/main` `f20400709` (`scripts/assert-base.sh origin/main` OK; HEAD == f20400709,
tree clean at measurement time).
**Issue:** #523 (gap 2 of the validator-aligned solve audit — classifying each
`verify_iec60335_compliance` violation against the solve's generated
domain-clearance SeparatedConstraint set into HARD / intra-footprint straddler /
COVERAGE GAP).
**Purpose:** quantify the third bucket (COVERAGE GAP) on the *real production board*:
what pairs does the generator never constrain, even unfiltered, and which of those
are currently violating? Also independently verify the handoff's §3 current-state
claims (measured 2026-08-01 at f20400709).

**Method.** The production board is loaded exactly the way the REQ-SAFE-01 gate test
loads it — `tests/requirements/safety/_real_board_fixture.py::load_real_board_placement()`
reused by import (same manifest loader `check_domain_partition.load_manifest`, same
netlist parser, same pad/rotation geometry, same full 54-net manifest classification).
Pair sets are computed with the generator's own functions
(`generate_domain_clearance_constraints`, `find_intra_footprint_domain_conflicts`),
and violations with the validator itself (`verify_iec60335_compliance`) — no
reimplementation anywhere. Measurement script:
`docs/evidence/gap2_measure.py` (committed alongside this doc).

## 1. Pair-set table (current board, f20400709)

| set | definition | constraints | unique unordered pairs |
|---|---:|---:|---:|
| **A** | `generate_domain_clearance_constraints(placement, voltage_domains, component_refs=None)` — full validator-equivalent pair set | **12,022** | 11,571 |
| **B** | same with `component_refs` = the refs the production scoped solve passes to the model (**all 169 PCB refs minus C27** — the tank cap staged off-board; the documented PD2 solve recipe, `docs/evidence/2026-07-31-pd2-clearance-resolve.md` §2.1: "netlist=`<PCB parse minus C27>`", "component_refs=`<all 168 model refs>`") | **11,908** | 11,457 |
| **A − B** | pairs the ref filter excludes | **114** | 114 |
| **B − A** | pairs only the filter adds | 0 | 0 |

- **All 114 A−B pairs involve C27** (the staged tank cap): `C27<->{C11, C12, C13,
  C15, C16, C18, C19, C20, C21, C28, C29, C30, C31, C32, C33, C34, C35, C36, C37,
  C38, C39, C40, R1, R2, R3, ..., U27, J1, SW1, SW2, ...}` — 114 distinct refs, each
  paired with C27 exactly once, all at the 8.0mm reinforced margin. C27 carries a
  classified net (it is in the placement with 159 matched components), so the
  unfiltered generator *does* pair it; the production solve's ref filter is what
  drops it (deliberate: C27 is staged off-board at (20, 272.75) per the documented
  human decision, so no placement-time constraint on it is meaningful).
- **B−A = 0**: the filter only ever removes pairs, never adds.
- **Validator-equivalence of A verified directly, not assumed**: the validator's own
  inter-component candidate set (the union of `_domain_boundary_pairs` over every
  `IEC60335_REQUIREMENTS` row with the same nets_domain map) is **exactly** Set A's
  unique-pair set (11,571 == 11,571, symmetric difference 0 both directions). Set A
  is the complete set of inter pairs the validator can ever flag.

### Margin distribution

| margin (mm) | Set A constraints | Set A unique pairs | Set B constraints |
|---:|---:|---:|---:|
| 1.0 (LV_CONTROL<->LV_CONTROL functional) | 5,988 | 5,565 | 5,988 |
| 8.0 (MAINS/DC_BUS<->LV_CONTROL reinforced; MAINS<->ISOLATED reinforced) | 6,034 | 6,006 | 5,920 |
| total | 12,022 | 11,571 | 11,908 |

No 4.0mm/6.0mm entries survive because every HV<->LV_CONTROL pair matches both the
BASIC (4.0) and REINFORCED (8.0) rows and the generator keeps the max margin (8.0);
the MAINS<->ISOLATED row is never populated (ISOLATED domain unused — documented
loader simplification).

### Duplicate-pair finding (relevant to the audit's HARD classification)

12,022 constraints but only 11,571 unique unordered pairs → **451 duplicate
emissions**, every one of them a pair involving an intra-footprint straddler (C6, K1,
K2, K3, PS1, T1, U3, U7) that appears in BOTH the LV_CONTROL<->LV_CONTROL functional
row (1.0mm) and the DC_BUS<->LV_CONTROL rows (8.0mm) **with reversed (a, b)
ordering** — e.g. `(C11, C6)` at 1.0mm and `(C6, C11)` at 8.0mm. The generator's
per-row ordered-key dict (`pair_margin[(ra, rb)]`) cannot merge them because the
ordering differs between matrix rows, so both constraints are emitted. For the
gap-2 audit this means: (a) classify on the **unordered** pair key, not on `(a, b)`
order, and (b) the "12,022 constraints" figure over-counts unique pairs by 451 —
the pair is still HARD (the 8.0mm constraint is present), so no violation is
misclassified, but any count comparison must use unique pairs, not constraints.

## 2. Violations on the current board — the coverage-gap bucket

`verify_iec60335_compliance(placement, voltage_domains)` on the committed board:

| metric | value |
|---|---|
| violations (records) | **3** |
| violating pairs | **1** |
| intra records | 3 |
| inter records | 0 |

The single violating pair is **K3-intra** (ref_a == ref_b == K3), all three records:

```
K3 creepage  3.559/4.0  DC_BUS<->LV_CONTROL basic
K3 clearance 3.559/6.0  DC_BUS<->LV_CONTROL reinforced
K3 creepage  3.559/8.0  DC_BUS<->LV_CONTROL reinforced
```

(closest pads `K3.1(DC_BUS_RTN) <-> K3.2(discharge.k_dis2-coil1)`; footprint
`Relay_THT:Relay_SPDT_Omron-G5LE-1`.)

### Bucket classification of V

| bucket | pairs | explanation |
|---|---|---:|
| (a) HARD — pair in Set A (solve would have constrained it) | 0 inter | no inter violations on the current board |
| (b) intra-footprint straddler (ref_a == ref_b) | **1** (K3) | placement-independent; generator never emits self-pairs by design |
| (c) COVERAGE GAP — pair NOT in Set A (V ∉ A) | **0 inter** | **the bucket is empty on the current board** |

**V∩A (inter) = 0** — sanity check confirmed: the only violation is the K3-intra
straddler, which is classified intra (ref_a == ref_b), *not* inter, and therefore is
not a HARD-miss. It is also not in A (the generator structurally cannot constrain a
component against itself — `_domain_boundary_pairs` skips self-pairs; this is the
documented, correct behavior, `domain_clearance.py` module docstring "What this
proof does NOT cover").

**V∉A (inter) = 0 — TRUE coverage gaps on the current board: none.** The only
violating pair is the K3 intra straddler, and Set A is proven (Sec 1) to be the
complete inter pair set, so there is no inter violation the generator fails to
constrain. The coverage-gap bucket being empty here is the *expected* outcome of a
board that was re-solved against this exact constraint set (#517/#521): the audit's
bucket (c) is the class that catches *future* solve/board drift (e.g. the run-B
candidate in `2026-08-01-k3-runb-not-validator-clean.md`, where solver-audit-clean
≠ validator-clean because the generator's box model and the validator's exact-copper
measurement disagree on pairs the generator DID constrain — a different mechanism
than bucket (c), but the same audit surfaces it).

**V∩(A−B) = 0** — the ref filter currently drops nothing that is violating. The
114 C27 pairs it removes are all non-violating on the committed board (C27 sits
off-board at y=272.75, board outline y∈[20,254]), so the filter's risk is currently
**latent, not live**. The value/risk of the filter:

- **value**: keeps the solve's model small and honest — C27 is staged off-board by
  human decision, so constraining it against on-board refs would either be vacuous
  (unreachable geometry) or force the solver to keep it off-board that it cannot
  move anyway.
- **risk**: if a future solve ever places C27 on-board (or the staging decision is
  reversed) while still excluding it from `component_refs`, all 114 of its pairs
  would be silently unconstrained — exactly the class gap-2's bucket (c) must flag.
  Recommendation: the audit should treat every ref in the PCB but absent from the
  solve's ref set (currently just C27) as a named, explainable exclusion, not a
  silent filter.

**Intra-footprint straddlers** (generator's own warning list, `domain_clearance.py`
— 8 refs at DC_BUS<->LV_CONTROL, 8.0mm): C6, K1, K2, K3, PS1, T1, U3, U7. Only K3
currently violates (its 3.559mm coil-to-contact gap). These are the bucket-(b)
candidates; the validator's pad-level `_intra_component_boundary_components` is the
authoritative check for them, and the audit must classify them by `ref_a == ref_b`
*before* consulting Set A (they are never in A).

## 3. Handoff §3 current-state verification (measured vs claimed)

Claimed (handoff, measured 2026-08-01 at f20400709) → measured on this worktree at
f20400709 (board `pcb/temper.kicad_pcb` unmodified; content hash unchanged):

| # | handoff claim | measured (this worktree) | match |
|---|---|---|---|
| 1 | REQ-SAFE-01 = **3 violations / 1 pair**, all K3-intra | `verify_iec60335_compliance`: **3 records / 1 pair / 3 intra** (K3), inter = 0 | ✅ |
| 2 | K3-intra = G5LE-1 **3.559mm** vs **4.0/6.0/8.0** bars | K3 creepage 3.559/4.0 (basic), clearance 3.559/6.0 (reinforced), creepage 3.559/8.0 (reinforced); footprint `Omron-G5LE-1` | ✅ |
| 3 | K3 at board position **(69.72, 29.0) rotation 90** | raw board file: `(at 69.72 29 90)` (parser reports (56.82, 9.0) — origin-normalized bbox-center in the local frame; raw KiCad position is the (69.72, 29.0) claimed) | ✅ |
| 4 | tank3 cap **C27 staged off-board at (20, 272.75)** | raw board file: `(at 20 272.75)` (parser reports (20.0, 252.75) normalized); board outline y∈[20,254] → y=272.75 is off-board | ✅ |
| 5 | scoped solve used **12,022 domain-clearance constraints** | unfiltered Set A = **12,022** ✅; with the production ref filter (minus C27) = **11,908** (matches the 2026-07-31 PD2 solve doc's recorded 11,908 exactly) | ✅ (12,022 = unfiltered / validator-equivalent count) |

All five handoff claims verified exactly on the current committed board.

## 4. Interpretation for the gap-2 audit

1. **Bucket (c) is empty on the current board** — there are zero inter violations,
   and Set A == the validator's complete inter pair set, so no violating pair can be
   a coverage gap. The audit's actionable output on this board is: 3 violations /
   1 pair, all bucket (b) K3-intra. The coverage-gap bucket is the *early-warning*
   class for future drift, and this measurement is the baseline it should be
   asserted against (any future V∉A inter pair is a regression by construction).
2. **The ref filter is currently safe but must be audited as a named exclusion** —
   A−B = 114 C27 pairs, all non-violating today; the risk is latent.
3. **The 12,022 figure** (handoff) equals the *unfiltered* constraint count; the
   production solve's actual filtered count is 11,908. Both are reproducible from
   the committed board with the generator's public functions. Note the 451
   duplicate-pair emissions: unique unordered pairs are 11,571 (Set A), not 12,022.
4. **Duplicate emission is a real generator quirk the audit must not trip on**:
   classify on the unordered pair key; a straddler pair like {C6, C11} is covered by
   an 8.0mm constraint even though the constraint list also carries the reversed
   1.0mm duplicate.

## 5. Reproduction

```bash
cd .claude/worktrees/agent-gap2-coverage
make netlist                          # elec/build/default.net (gitignored)
cd packages/temper-placer
uv run --no-sync python ../../docs/evidence/gap2_measure.py
```

The script prints Set A/Set B counts, A−B/B−A, the margin distribution, the
violation records with their bucket classification, the validator-equivalence
check, and the A−B composition. It requires no src/ changes and no board writes.

## Files

- `docs/evidence/gap2_measure.py` — the measurement script (committed).
- `docs/evidence/2026-08-01-domain-constraint-coverage-gap.md` — this document.
