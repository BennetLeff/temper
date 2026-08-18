# DRC ceiling re-baseline: closing the `silk_overlap` and 120-sample methodology gaps

**Status: COMPLETE.**

**Headline answers:**
- **`silk_overlap` true count: 12,873**, obtained and validated entirely via
  kicad-cli (no reimplemented geometry) — see Gap 1. The double-counting is
  explained structurally: `silk_overlap` has no DRU rule to isolate by (it's
  a single global board-setup scalar, `min_silk_clearance`), so it can't use
  clearance's disjoint recursive bisection; its fallback (bucket-pair sweep)
  both combinatorially over-counts and silently truncates saturated cells.
- **`creepage` is still nondeterministic today**, live-measured on
  `kicad-cli 10.0.5`: 125 independent pinned samples, spread 2 (109/110/111,
  minority state 0.8%). KiCad issue #20048 is unfixed upstream; the
  2026-08-04 survey's Rust-backend recommendation was not adopted (confirmed
  from current source, not inherited). Every other measured category is
  deterministic at N up to 125 — see Gap 2.
- **Per-category sampling table**: §2.4. `creepage` needs ≥120 (and that is
  a floor, not a guarantee, given today's measured 0.8% tail); everything
  else needs 3-5 confirmatory samples, structurally, and gets more for free
  from the same campaign.

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

## Gap 2 — the 120-sample bar: per-category requirement, derived from measured spread

### 2.0 Method

Ran the **real production measurement path**, not a hand-rolled substitute:
`temper_placer.validation._drc_api.run_drc()` (imported from this worktree's
own freshly-built `.venv` — `temper_placer.__file__` verified to resolve
inside `agent-aaad9bbfda4c0ef0a` before trusting any number, per the
fifth-venv-mode hard rule), which carries the real single-thread pin
(`_single_threaded_kicad_env`, `MaximumThreads=1`, PR #722) and the real
`--all-track-errors --format json` invocation. Each of the 125 samples below
is a fully independent process launch (fresh scratch `KICAD_CONFIG_HOME`,
fresh kicad-cli subprocess) against a scratch copy of the **committed**
board + regenerated `.kicad_dru`, never the committed file itself. No
`--refill-zones` (matches the current runner default / CI protocol).
`kicad-cli 10.0.5`.

### 2.1 Is `creepage` still nondeterministic today? Yes — measured live, not inherited.

125 independent pinned samples, board sha256
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`:

| value | count | frequency |
|---:|---:|---:|
| 109 | 1 | 0.8% |
| 110 | 13 | 10.4% |
| 111 | 111 | 88.8% |

**Spread = 2 (three consecutive integers), exactly the pattern documented
since #602** (`docs/evidence/2026-08-11-creepage-noise-headroom-guard-fix.md`
§2: six independent historical campaigns, 564+ combined samples, every one
converging on a 3-value support once past creepage's very first narrow
regime). This is a live, first-party reproduction of that exact pattern on
today's board and today's `kicad-cli 10.0.5` — **the KiCad issue is not
fixed upstream.**

**It also reproduces the specific failure mode PR #1027 flagged**: that PR's
own partial 20-sample run saw only 2 of the 3 known values and would have
under-stated the true spread. My first 35 samples (run before extending to
125) *also* saw only `{110, 111}` — the rare `109` state (0.8% frequency)
only appeared once the sample crossed ~90. **A 35-sample measurement here
would have silently missed the true spread, exactly as #1027 documents
happened before.** This is direct evidence for *why* a large N matters for
this specific category, not an assumption carried over from that PR.

**Root cause unchanged, confirmed by reading the current source, not by
inheriting the 2026-08-04 claim:** `packages/temper-drc-rs/src/rules/safety/creepage.rs`
(current `main`/this worktree) states in its own header comment that it
**does not measure creepage** — it is a component-bounding-box sanity check,
unrelated to the DRU `creepage` constraint kicad-cli enforces, and its
comment explicitly names `scripts/generate_kicad_dru.py`'s generated
`.kicad_dru` `(constraint creepage ...)` rules, verified against kicad-cli's
real surface-path solver, as "the real, IEC-60335-cited, currently-enforced
creepage check for this board." **The 2026-08-04 survey's recommendation to
move creepage to the Rust backend was not adopted** — confirmed
independently by `DrcRatchet.__init__`'s default (`backend="rust"`) never
being what CI actually uses: `scripts/ci_check_drc.py --backend` defaults to
`"kicad-cli"`, documented in its own `--help` text as *"kicad-cli (default,
KiCad truth gate) or rust (temper_drc_rs diagnostic)"* — the Rust backend is
explicitly a diagnostic path, not the enforced measurement. `creepage` is
still measured by kicad-cli's DRU-constraint surface-path solver today, and
is still subject to KiCad issue
[#20048](https://gitlab.com/kicad/code/kicad/-/issues/20048) (pointer-keyed
dedup, unfixed upstream as of `kicad-cli 10.0.5`).

### 2.2 Every other category: deterministic, confirmed at N up to 125

Across all 125 samples, **every one of the other 16 measured categories
(10 error + 7 warning, minus `creepage`) had spread exactly 0**:

`clearance` (238), `copper_edge_clearance` (12), `courtyards_overlap` (1),
`drill_out_of_range` (6), `hole_clearance` (26), `shorting_items` (53),
`solder_mask_bridge` (15), `track_width` (120), `tracks_crossing` (8),
`lib_footprint_issues` (13), `lib_footprint_mismatch` (26),
`missing_courtyard` (5), `silk_edge_clearance` (1), `silk_over_copper` (42),
`silk_overlap` (199, capped — stable *as a capped reading*, see Gap 1 for
the true count), `via_dangling` (106).

This matches this project's own multi-month record for the *same*
categories: PR #1027's table shows zero deviation across 564+ cumulative
historical samples for every category except `creepage`. **`clearance` and
`shorting_items` were historically unstable too — before PR #722's thread
pin landed** (§ of `docs/evidence/2026-08-04-drc-measurement-determinism.md`:
unpinned `clearance` wobbled 377/378, `shorting_items` 199/200, both
race conditions in kicad-cli's shared worker-thread pool, both fully
resolved by `MaximumThreads=1`). Today, pinned, both are rock solid at
N=125.

*(Side finding, not this task's scope but worth flagging: my very first,
ad-hoc-pinned sweep — using `measure_uncapped_drc.py`'s `_single_thread_env`,
which does **not** seed the scratch `KICAD_CONFIG_HOME` with copies of the
real library tables, unlike `_drc_api.py`'s real
`_single_threaded_kicad_env` — read `lib_footprint_issues=165,
lib_footprint_mismatch=1`, wildly different from the real-protocol
`13`/`26` above. This is an **environment artifact of which pin
implementation is used**, not board nondeterminism — the real
`_drc_api.run_drc` protocol is what CI and the ceiling actually use, and it
is what §2.1/§2.2's numbers come from. This plausibly also explains the
earlier declined-approval doc's unexplained `lib_footprint_issues 13 → 168`
"regression" — worth a follow-up check against the same protocol before
treating it as a real board defect.)*

### 2.3 Derivation: why 120(ish) for `creepage`, and why 3-5 would suffice for everything else

**The mechanism determines the sample-count requirement, not a flat
convention.**

- **Categories with no known nondeterminism mechanism** (everything in
  §2.2): once thread-pinned, these are pure functions of committed,
  content-addressed inputs (`pcb/temper.kicad_pcb` + the regenerated
  `.kicad_dru`) — there is no known source of run-to-run variation left
  (the *only* documented KiCad-internal nondeterminism mechanism in this
  project's history, the pointer-address-keyed `std::set` dedup, is
  confirmed in `docs/evidence/2026-08-04-drc-measurement-determinism.md` §4
  to affect specific DRC providers' *reported-pair* caches — creepage's
  provider primarily, with a documented but count-invisible residual on
  `clearance`'s *set* only, never its *count*, post-pin). Structural
  confidence, not just statistical confidence, is available here: there is
  no plausible mechanism left for these to vary. **3-5 samples is a
  reasonable confirmatory floor** — repeat-testing that a category is what
  the structural argument already predicts, not searching a distribution
  for a tail. (In practice, sampling fewer than whatever `creepage`
  requires costs nothing: they are read off the *same* DRC runs.)

- **`creepage`: nondeterministic via a named, understood mechanism**
  (KiCad #20048) that behaves like drawing from a fixed discrete
  distribution over 2-3 adjacent integers, with mixing dominated by
  process-level pointer-allocation entropy (independent of the board, not
  reduced by the thread pin). The sampling question is not "is it
  deterministic" (no) but "have I seen every state with high confidence,
  including the tail." For a minority state with true probability `p`, the
  chance of missing it entirely in `N` independent samples is `(1-p)^N`;
  solving `(1-p)^N <= 0.05` (95% confidence of seeing it at least once)
  gives `N >= ln(0.05) / ln(1-p)`. This project's own empirical minority-
  state frequencies, across every characterized campaign:

  | source | N | minority-state frequency | `N` needed for 95% detection at that rate |
  |---|---:|---:|---:|
  | pre-#602 (`_march`) | 120 | — (spread 1, no 3rd state) | — |
  | 2026-08-04 doc, pinned | 120 | 185×27/120 ≈ 22.5% | 13 |
  | `8e92559e2` `_march` | 134 | 182×5/134 ≈ 3.7% | 79 |
  | **this doc, live, 2026-08-17** | **125** | **109×1/125 ≈ 0.8%** | **≈372** |

  **The rarest tail state this project has ever measured is the one
  measured today**, at 0.8%. A flat 120-sample floor gives only
  `1-(1-0.008)^120 ≈ 62%` confidence of seeing a state that rare — meaning
  **the historical "120" convention is itself a heuristic compromise, not a
  guarantee, and by today's measured tail rate it is arguably still
  short.** This matches PR #1027's own honest caveat verbatim: *"no finite
  sample size can rule out an arbitrarily-rare fourth value."* The
  defensible statement is not "120 is enough" but **"120 is the number that
  has, in practice, recovered every state this project has characterized
  down to ~1% frequency in six independent campaigns to date — including
  today's — and lower N (20-35) has repeatedly and reproducibly missed
  known tail states."** That is the reason worth citing going forward, not
  the number by itself.

### 2.4 The per-category sampling table

| category | mechanism | observed spread (this pass, N=125) | required N | why |
|---|---|---:|---:|---|
| `creepage` | KiCad #20048, pointer-keyed dedup (upstream, unfixed in 10.0.5) | 2 (109/110/111, minority 0.8%) | **≥120, and treat as a floor not a guarantee** | tail-detection problem; empirically the only way this project has ever recovered rare (~1-4%) states is with N in the 100s; lower N has repeatedly under-observed the true support (this pass's own first 35 samples, and PR #1027's 20-sample partial run) |
| `clearance` | none (post-#722 thread pin); pre-pin was a worker-pool race, fully resolved | 0 | 3-5 confirmatory, already covered for free by creepage's campaign | structural: pure function of pinned-thread + content-addressed inputs |
| `shorting_items` | none (post-#722 thread pin); pre-pin was the *same* race as clearance (correlated, #722 §5) | 0 | 3-5 | same |
| `copper_edge_clearance`, `courtyards_overlap`, `drill_out_of_range`, `hole_clearance`, `solder_mask_bridge`, `track_width`, `tracks_crossing` | none known; no history of ever varying | 0 | 3-5 | same |
| `lib_footprint_issues`, `lib_footprint_mismatch`, `missing_courtyard`, `silk_edge_clearance`, `silk_over_copper`, `via_dangling` | none known; **sensitive to which `KICAD_CONFIG_HOME` seeding is used, not to run-count** (§2.2 side finding) | 0 (with the real `_drc_api` pin) | 3-5, **using the real `_single_threaded_kicad_env` protocol specifically** | same structural argument; the historical `lib_footprint_issues` "regression" this task's brief cites should be re-checked against this exact protocol before being treated as a board defect |
| `silk_overlap` | capped at 199 by kicad-cli's `ERROR_LIMIT`; the *capped reading* is deterministic even though the *true count* (Gap 1: 12,873) cannot be read this way | 0 (of the capped value) | 3-5 for the capped-value stability; N is irrelevant to recovering the true count — that needs the Gap-1 method, not more samples | saturation is a property of the board content, not of sampling |

**Practical recommendation for the next re-baseline**: run one campaign at
`N=120` (or more, given §2.3's honest caveat) as today's floor for
`creepage`; every other category's ceiling can be certified from the *same*
campaign's repeated reads at zero extra cost — there is no category for
which under-sampling is a live risk once `creepage`'s own requirement is
met. Do not apply a 120-sample bar as a blanket justification without
naming `creepage` as the reason; per `_ceiling_raise_evidence.py`, the
current machine gate already requires `sample_count >= 120` for the *whole*
board provenance record whenever *any* category is declared nondeterministic
— which is operationally fine (everything is read from the same runs) but
should be understood as "creepage's floor, inherited by the record," not as
a number each category independently needs.

---
