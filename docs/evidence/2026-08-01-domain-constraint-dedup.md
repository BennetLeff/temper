<!-- provenance: commit=74af50c52b8dcfd08e44aef27e67ff5a549f5809 dirty=false -->

# Domain-clearance constraint dedup: one constraint per unordered pair (2026-08-02)

**Date:** 2026-08-02
**Branch:** `fix/domain-constraint-dedup` (fix commit `306a39255`), continuation
worktree `.claude/worktrees/agent-gen-dedup-2` on
`fix/domain-constraint-dedup-continued` (`scripts/assert-base.sh origin/fix/domain-constraint-dedup` OK).
**Issue context:** #523 gap-2 coverage audit — `docs/evidence/2026-08-01-domain-constraint-coverage-gap.md`
(measured at `f20400709`, board `pcb/temper.kicad_pcb` unchanged since).
**Fix commit:** `306a39255d64968913f7e1b7f31d591d91f6d2b2` "fix(placer): dedupe
domain-clearance constraints to one per unordered pair".
**Measurement script:** `docs/evidence/domain_dedup_measure.py` (committed alongside this doc).

## The wart

`generate_domain_clearance_constraints`
(`packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`)
keyed its per-pair margin dict by the **ordered** `(ref_a, ref_b)` tuple. Two
different `IEC60335_REQUIREMENTS` matrix rows can pair the same two physical refs
in **opposite order**:

- the `LV_CONTROL<->LV_CONTROL` (functional, 1.0mm) row draws both refs from the
  LV_CONTROL group and emits the pair as `(C11, C6)`;
- the `DC_BUS<->LV_CONTROL` (basic 4.0mm / reinforced 8.0mm) rows draw the
  straddler `C6` from the DC_BUS group and emit the pair as `(C6, C11)`.

With an ordered key those land in **two** dict entries, so the generator emitted
the same physical pair twice at two different margins:
`domain_clearance_C11_C6` @1.0mm *and* `domain_clearance_C6_C11` @8.0mm.

The gap-2 audit (§1) measured the production board at 12,022 constraints for
**11,571 unique unordered pairs — 451 duplicate emissions**. Every duplicate
involves an intra-footprint straddler (C6, K1, K2, K3, PS1, T1, U3, U7) that
matches both the same-domain row (1.0mm, ordered one way) and the cross-domain
rows (8.0mm, ordered the other way).

## The fix

Canonicalize the dict key to the lexicographically sorted ref pair:

```python
key = (ra, rb) if ra <= rb else (rb, ra)
```

- **One constraint per unordered pair** — every matching row merges onto one
  dict entry.
- **Max margin across rows wins** (`if margin > pair_margin.get(key, 0.0)`),
  so a pair matched by both a 1.0mm functional row and an 8.0mm reinforced row
  is emitted at 8.0mm.
- **Canonical emitted order + deterministic id** — `a`/`b` are the sorted refs,
  so the id `domain_clearance_{a}_{b}` no longer depends on matrix-row
  iteration order (same id regardless of which row is visited first).
- **`because` now lists every matching row** (deduped list, `"; ".join`),
  naming both the same-domain and the reversed cross-domain rows.
- `component_refs` filtering and the intra-footprint straddler warning logging
  are preserved unchanged.

## Binding-semantics equivalence

The dedup is lossless w.r.t. what the solver could enforce: for every duplicated
pair the pre-fix output contained one weaker (1.0mm) and one stricter (8.0mm)
constraint on the same refs, and the stricter 8.0mm constraint dominated the
1.0mm duplicate in the solver anyway (a `SEPARATED` constraint requiring
≥8.0mm subsumes one requiring ≥1.0mm between the same two refs). Post-fix the
single surviving constraint is exactly the stricter one (8.0mm) — verified
below by the per-pair margin map being **identical** before/after. The unordered
pair set is also unchanged (symmetric difference 0), so no pair lost coverage
and no new pair gained it.

## Measurement (production board, `make netlist` output at digest `860d86cca5c1…`)

`uv run --no-sync python docs/evidence/domain_dedup_measure.py`:

| metric | before (reconstructed pre-fix) | after (fixed generator) |
|---|---:|---:|
| constraints | **12,022** | **11,571** |
| unique unordered pairs | 11,571 | 11,571 |
| duplicate emissions | **451** | **0** |
| pair-set symmetric difference (old ^ new) | — | **0 (UNCHANGED)** |
| per-pair margin deltas (old max != new) | — | **0 (PRESERVED)** |

- The "before" figure is a faithful reconstruction of the pre-fix ordered-key
  algorithm, reimplemented from the `git diff` of `306a39255` (not assumed);
  its 12,022 count matches the independently-measured gap-2 audit figure.
- Margin distribution after (constraints == unique pairs): **5,565 @ 1.0mm +
  6,006 @ 8.0mm = 11,571** — identical to the gap-2 audit's unique-pair
  distribution (5,565 / 6,006), confirming every duplicate pair kept its
  stricter margin and only the redundant weaker emissions disappeared
  (1.0mm bucket 5,988 → 5,565; 8.0mm bucket 6,034 → 6,006 with 28
  same-margin reversed-order duplicates also removed).
- All 451 pre-fix duplicates were pairs emitted under **both** orderings; every
  such pair kept its max margin post-fix (checked explicitly).

## Perf note

The dedup shrinks the solver's domain-clearance input from 12,022 to 11,571
constraints (−3.75%) with identical binding semantics — 451 redundant
`SEPARATED` constraints no longer reach the CP-SAT model. The remaining
11,571 are exactly the validator's own candidate pair set (gap-2 audit §1:
Set A unique pairs == validator candidate set, symmetric difference 0), so
the solver input and the validator's universe of flaggable inter pairs now
coincide one-to-one.

## The 451-delta reference

The 451 is the same quantity the gap-2 coverage audit
(`docs/evidence/2026-08-01-domain-constraint-coverage-gap.md` §1) reported as
the constraint/unique-pair gap for unfiltered Set A: **12,022 constraints /
11,571 unique unordered pairs = 451 duplicate emissions**. It is exactly the
redundancy this fix removes; it is *not* a loss of coverage (pair set and
margin map unchanged, per the measurement above).
