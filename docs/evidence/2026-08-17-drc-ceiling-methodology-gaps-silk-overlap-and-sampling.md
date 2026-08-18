# DRC ceiling re-baseline: closing the `silk_overlap` and 120-sample methodology gaps

**Status: IN PROGRESS — stub committed first per working-pattern instructions.**

**Board sha256 pinned for all numbers in this document:**
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(verified via `sha256sum pcb/temper.kicad_pcb` at the start of this task, in
worktree `agent-aaad9bbfda4c0ef0a`, main `ac8dbf7ab`). This agent does not
modify `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`, and
writes no `Ceiling-Approval:` trailer — this task closes measurement
methodology gaps only; the re-baseline itself is a separate owner-ceremonied
act (per `docs/evidence/2026-08-17-drc-ceiling-rebaseline-measurement-and-declined-approval.md`,
commit `3b032eaf7`).

Raw measurement outputs live under
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/drc-gaps/`
(scratch, not committed). `kicad-cli --version`: `10.0.5`. `pcb/temper.kicad_pcb`
sha256 re-verified unchanged (`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`)
before every write to this document.

---

## Gap 1 — `silk_overlap`: obtainable, validated, entirely via kicad-cli. **True count: 12,873.**

No new geometry engine was built. `silk_overlap` turns out not to need one:
the existing `scripts/measure_uncapped_drc.py` tooling already contains a
validated, exhaustive, item-level bisection primitive
(`measure_saturating_footprint_pair` / the `saturating-pair` CLI command,
landed for PR #1150/#1154's `C2xC3`/`C5xC7` investigation). What was missing
was applying proper inclusion-exclusion across the *whole board* instead of
trusting the naive bucket-pair sweep's raw sum. Doing that is what this
section does.

### 1.0 What `silk_overlap` actually is (checked, not assumed)

Reading real violation payloads from a live DRC run on the committed board
(`docs/evidence/.../baseline_detail.py` in scratch) shows every `silk_overlap`
item is:

```
Silkscreen clearance (board setup constraints silk clearance 0.1500 mm; actual 0.1180 mm)
    Segment of C3 on F.Silkscreen
    Segment of C2 on F.Silkscreen
```

So `silk_overlap` is a **minimum-clearance check between silkscreen graphic
primitives** (segments/circles/arcs/polys on the same silkscreen layer), not
a binary "do they touch" test — but it genuinely is, as the task's brief
guessed, **pure geometry with no electrical semantics**: the threshold comes
from `pcb/temper.kicad_pro`'s `"min_silk_clearance": 0.15`, a single global
board-setup scalar, **not a `.kicad_dru` rule** and **not conditioned on net
class** the way `clearance`/`creepage`/`track_width` are.

**This is the structural reason the DRU-band bisection cannot even be tried
for `silk_overlap`, and it is the root of the double-counting**, established
below.

### 1.1 Why the existing bisection double-counts here but not for `clearance` — the reusable reason

`measure_uncapped_drc.py` has two, structurally different partition
strategies:

- **DRU-rule-governed categories** (`clearance`, `creepage`, `track_width`):
  each violating item-pair is a **property of the pair itself** — which
  `.kicad_dru` rule's condition it matches, via last-matching-rule-wins.
  `isolation_dru()` builds a synthetic 2-rule DRU per rule-band that is
  **provably disjoint from every other rule's isolated band by
  construction** (each ranked rule's condition is AND-NOT'd against every
  strictly-higher rule). When a band still saturates, `_measure_pool`
  recursively **bisects a real net-name pool into two disjoint halves**
  (`pool[:mid]`, `pool[mid:]`) and recurses on each half separately — a
  strict binary partition tree. **No leaf's item set is ever re-tested
  against more than one sibling population.** Every pair is counted in
  exactly one leaf, by construction, all the way down.

- **`silk_overlap` has no such axis.** There is no DRU rule to isolate
  because there is no DRU rule at all (§1.0) — the only thing distinguishing
  one violation from another is *which two footprints* it involves. The
  tool's fallback, `measure_by_bucket_pairs`, partitions footprints into `k`
  buckets and runs **every unordered bucket pair `(i,j)`, `i<=j`, including
  the diagonal** — a combinatorial *sweep*, not a recursive *partition*.
  Each bucket therefore appears in `k` separate kicad-cli runs (once against
  every other bucket, including itself), and a run `(i,j)` for `i≠j`
  reports **`intra_i + intra_j + cross_ij`**, not just `cross_ij` — the two
  buckets' own internal violations ride along in every cross-pair run they
  participate in. Summing all `k(k+1)/2` cell counts therefore counts each
  bucket's `intra_i` population `k` times (once as the diagonal, once for
  each of the `k-1` off-diagonal pairs it appears in) instead of once. The
  tool's own CLI output already flags this honestly: *"this raw sum
  double-counts intra-bucket pairs... apply inclusion-exclusion yourself
  before trusting a total."* Nobody had, until now.

  On top of the combinatorial over-count, **any individual cell that itself
  saturates the 199 cap is silently truncated**, which under-counts by far
  more than the combinatorial effect over-counts (§1.3 below: one cell's
  true value is ~12,856 against a 199 cap — a ~12,657 undercount that swamps
  the ~150-count combinatorial over-count from the rest of the board).

  **Reusable rule for the next capped category:** check whether the
  category's violations are attributable to a `.kicad_dru` rule condition
  (`"rule '...'"` appears in kicad-cli's own JSON `description`). If yes,
  use the DRU-rule + real-net-name recursive bisection (disjoint,
  cap-respecting by construction). If no — as with `silk_overlap` and
  `shorting_items` — the only available axis is board content, and the
  bucket-pair *sweep* is a **diagnostic** for finding which cells saturate,
  never a number to sum directly. A true total needs an explicit
  inclusion-exclusion pass (§1.2) with every saturated cell resolved by
  recursive bisection down to non-saturated leaves.

### 1.2 The corrected total, worked out from the same board

8 buckets of 21 footprints each (`scripts/measure_uncapped_drc.py
physical-category silk_overlap --buckets 8`), all 36 `(i,j)` cells measured:

- **Diagonal (`intra_i`) — all 8 unsaturated, exact:** `[2, 2, 1, 5, 2, 2, 6,
  1]`, sum = **21**.
- **Off-diagonal — 27 of 28 cells unsaturated**, and for every one of them
  `cell(i,j) - intra_i - intra_j == 0` exactly (i.e. their true cross term is
  0 — verified for all 27 by direct arithmetic on the raw sweep output).
- **1 saturated cell: `(bucket0, bucket1) = 199`** (capped). `C2` is in
  bucket 0, `C3` is in bucket 1 — the same pair PR #1154 found colliding
  (their bodies genuinely interpenetrate; `courtyards_overlap` still reports
  exactly this pair, count 1, on the current board).

Resolving the one saturated cell by partitioning `bucket0 = {C2} ∪ R0` and
`bucket1 = {C3} ∪ R1` (`R0`/`R1` = the other 20 footprints in each bucket)
and measuring every sub-term directly:

| term | measured |
|---|---|
| `intra(C2)` | 0 |
| `intra(C3)` | 0 |
| `intra(R0)` | 2 |
| `intra(R1)` | 2 |
| `cross(C2, R1)` (keep = `{C2} ∪ R1`, minus `intra(C2)+intra(R1)`) | 0 |
| `cross(C3, R0)` (keep = `{C3} ∪ R0`, minus `intra(C3)+intra(R0)`) | 0 |
| `cross(R0, R1)` (keep = `R0 ∪ R1`, minus `intra(R0)+intra(R1)`) | 0 |
| `cross(C2, C3)` | via `measure_saturating_footprint_pair` (item-level recursive bisection, the already-validated PR #1150/#1154 method) |

`measure_saturating_footprint_pair(C2, C3)` (169s, fully automated recursive
item-list bisection): **`TRUE silk_overlap C2xC3 = 12852`** — matching PR
#1154's figure on a materially different, much-earlier board state exactly.
That is strong independent corroboration: `C2`/`C3` have not moved relative
to each other across all the intervening placement work, so the same
collision, and the same count, persists. Since `intra(C2)=intra(C3)=0`,
`cross(C2,C3) = 12852`.

**Total = `sum(intra_i)` (21) + `sum(cross_ij)` for all 27 unsaturated
off-diagonal cells (0) + `cross(C2,C3)` (12852) = `12,873`.**

### 1.3 Independent validation

Two checks, both against live kicad-cli output, not against each other:

1. **Reproduction of a historical figure not derived from this session's
   methodology**: `C2xC3 = 12852` matches `power_pcb_dataset/drc_ceiling.json`'s
   `saturation_hazard.silk_overlap` note (measured on board `9c1f4a37…`, a
   different commit) and PR #1154's evidence doc exactly, to the integer.
2. **A held-out prediction, checked against a fresh run it was not derived
   from**: the partition arithmetic predicts `board minus {C2,C3}` should
   equal exactly `21` (all the other terms above are 0). A direct kicad-cli
   run of the board with `C2` and `C3` deleted entirely measured **21**,
   confirming the arithmetic independently of the value used to derive it.

Both checks pass. **`silk_overlap` true count = 12,873** on board sha256
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`, fully
grounded in kicad-cli DRC runs (no reimplemented geometry, no unvalidated
method) — every sub-measurement is either directly under the cap or resolved
via the pre-existing, independently-corroborated item-level bisection tool.

This is **not** applied to `power_pcb_dataset/drc_ceiling.json` — per the
hard rules, the re-baseline itself is a separate owner-ceremonied act. It is
reported here as the resolved number for whoever performs that ceremony.
The dominant real finding underneath the number is unchanged from PR #1154:
`C2`/`C3` (both `Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`) still
physically collide; fixing the placement is out of scope here (board-write
authorization required, and per the coordination note a sibling is
re-routing this exact board right now).

---
