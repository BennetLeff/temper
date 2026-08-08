# Parallel-Session Index: 66 `worktree-agent-*` Branches (+ 1 in-scope, +1 out-of-scope non-matching branch)

**Date:** 2026-08-07 (snapshot taken 2026-08-08T00:34:21Z)
**Status:** navigation aid — indexes and cross-checks unmerged work; makes no code changes.
**Scope:** read-only against git history. No branch was merged, pushed, rebased, or deleted while producing this
index; every merge test below used `git merge-tree --write-tree` (a fully in-memory, working-tree-free merge
simulation available in this repo's git 2.43) rather than `git merge --no-commit --no-ff` + abort, specifically
to guarantee no merge could accidentally be left in progress across 67 trials. Originally scanned
`refs/heads/worktree-agent-*` only; post-review, `fix/drc-ceiling-remeasure-10.0.5` was added as genuine
in-scope session output missed by that filter (see §1), and `feat/rust-hardening-pyany-removal-wave3` is noted
as explicitly out of scope (the maintainer's own branch).

**Provenance of this snapshot** (per `docs/METHODOLOGY.md`'s "a measurement carries the commit it was taken at, or
it is not a measurement"): local `main` = `b31fe01730e171a9b020a2360a49931d404a2de3`; `origin/main` =
`7e1194b776aad76db2f1fd2a323defa0bebd5367`; branch tips captured atomically in one pass via
`git for-each-ref refs/heads/worktree-agent-*` at 2026-08-08T00:34:21Z, and every downstream `git log`/`git
diff`/`git merge-tree` call in this document used that captured SHA, not the live branch name — this repo runs
60+ concurrent agent worktrees against one shared `.git`, and two of the 66 branches (`worktree-agent-a3937a7...`
and `worktree-agent-a988999c...`) were observed to gain new commits between an earlier, unpinned pass and this
one. Anything below attributed to a branch name reflects that branch **at the pinned SHA shown**, not necessarily
its state if read again later.

---

## Executive summary — two findings that override the task's own framing

1. **`main` is not "1 behind `origin/main`" — it has diverged.** `git merge-base main origin/main` = `90d5fd98`,
   not either tip. From that base, local `main` carries **33 commits `origin/main` does not have** (`git
   rev-list --count 90d5fd98..main` = 33), and `origin/main` carries **1 commit local `main` does not have**
   (`7e1194b7`, the last commit before this parallel session started). The 33 are **15 real, already-completed
   merges of `worktree-agent-*` branches** (via `ort` strategy, visible in `git reflog show main`) plus a few
   direct commits — all **local, unpushed**. This means: (a) 15 of the 66 branches are **already done**, not
   open work; (b) "push local `main`" is itself a live decision this index surfaces, not a formality; (c) every
   distance/conflict measurement against "`main`" below means **local `main`**, which is materially different
   from what's on GitHub.
2. **Most of the reported "conflicts" are one baseline issue wearing 46 different names.** Merging `origin/main`'s
   one extra commit into local `main` alone produces conflicts in 9 files (3 add/add + 6 content) inside
   `packages/temper-placer/{core,deterministic,regression,router_v6}` and the `.pyi` stubs. That **exact same
   9-file signature reproduces in 46 of the 66 branches' merge-tree tests** — because virtually every
   `worktree-agent-*` branch was built on top of `origin/main`'s tip, not on top of local `main`'s 33 additional
   commits. Of those 46, **36 have no conflict beyond this one shared signature** — fix it once, and 36 branches
   drop out of "CONFLICT" into "CLEAN" with no further work. Only **10** branches carry a genuine, branch-specific
   conflict on top of it (detailed in the merge-order section). Treating "CONFLICT" as 46 independent problems, as
   a naive branch-by-branch read would, overstates the remaining work by roughly 4x.

---

## 1. Branch inventory

**Scope correction (post-review):** the original pass here enumerated only branches matching
`refs/heads/worktree-agent-*`. Two further branches with unmerged commits exist outside that naming pattern and
were missed by that filter — both verified directly below, not taken on faith:

- **`fix/drc-ceiling-remeasure-10.0.5`** (1 commit, `835474e4`) — re-anchors `power_pcb_dataset/drc_ceiling.json`'s
  provenance (its recorded `measured_at_commit` did not resolve in git history, and its recorded board hash no
  longer matched `pcb/temper.kicad_pcb`) and re-measures 130 samples on the CI-pinned kicad-cli 10.0.5 (prior
  records were all measured on 10.0.4 and hand-patched +1 to guess at the difference). Error side: `error_ceiling`
  1267→1250, all decreases, no approval needed. Warning side: `via_dangling` measured 32/32 against a committed
  ceiling of 15 (+17) and is **deliberately withheld** — `warnings_by_type.via_dangling` and `warning_ceiling`
  stay at their committed values pending a maintainer's `Ceiling-Approval:` trailer, per the R27 monotone
  contract's "do not ratchet past an unexplained rise." This is the real branch behind Decision List item 10 —
  see the corrected write-up there for what its own `_march` entry actually attributes the rise to (not what the
  original claim text said). Merge-tree tested clean against local `main` (`git merge-tree --write-tree main
  fix/drc-ceiling-remeasure-10.0.5` exits 0) — this one is a Step-1-equivalent, independent, clean merge.
- **`feat/rust-hardening-pyany-removal-wave3`** (3 commits, tip `1d45edae`) — **this is the maintainer's own
  active branch, not this session's output.** `git worktree list` shows it checked out at the primary checkout
  path (`/home/bennet/Desktop/temper`, not a `.claude/worktrees/agent-*` path), distinguishing it structurally
  from every branch this session produced. Listed here for completeness only. **Do not merge, sequence, or
  otherwise act on this branch on the maintainer's behalf** — it is out of scope for this index's merge-order
  recommendation entirely.

66 `worktree-agent-*` branches exist, plus the one additional session-relevant branch above
(`fix/drc-ceiling-remeasure-10.0.5`). Against local `main` (`b31fe017`):

| Group | Count | Meaning |
|---|---|---|
| Already merged into local `main` (unpushed) | 15 | 0 commits ahead, tip is an ancestor of `main` |
| Clean, unmerged | 5 | 0 conflicts today, real unmerged content |
| Conflict — baseline signature only | 36 | Would be clean if the `main`/`origin/main` divergence (item 2 above) were resolved first |
| Conflict — baseline + genuine extra conflict | 10 | Needs its own reconciliation beyond the baseline fix |
| Zero unique commits (tip == `origin/main`, i.e. `7e1194b7`) | 4 | `a1087c2ce1ce15224`, `acf6badeed2dfe305` (this session's own branch), `ad6d49136abdf2281`, `ae8fccd26c6009709` — no content to merge |
| **Total** | **66*** | *one branch (`a3937a7`) has commits so it lands in both the "conflict" count and would double as an "empty" branch had it not moved mid-session — see note below |

Distinct commit tips: 66 branch names resolve to **56 distinct SHAs** — 5 groups of duplicates share a tip
byte-for-byte:

- `7e1194b776aa` (= `origin/main`, zero new work): `a1087c2ce1ce15224`, `acf6badeed2dfe305`, `ad6d49136abdf2281`, `ae8fccd26c6009709`
- `07d514f9b8a9` ("perf(router): KD-tree + Kruskal MST island bridging"): `a11904da8310c7be8`, `a1edfc6c42603e6ca`, `abf95b30125935383`, `af448502d9c6417ca`
- `6a5758b856a4` ("measure(router): U5 CNF measurement — OOM"): `a09b73d5391322d6d`, `a14cebd66c9c866e4`
- `6665aa3cdd4b` ("test(ci): drift test for unreferenced router_v6 test files"): `a681a84f1f1282eb8`, `a83609cb5411455d2`
- `979bafe58c6c` ("feat(elec): netlist-stage checks gate"): `aec4a46590b7d9ffa`, `afefd5add15cfaca4`

**`worktree-agent-a3937a7ac5c9edbaf` moved during this analysis**: it was `7e1194b7` (empty) when first sampled,
then gained a commit (`ce91fead`) whose subject — `feat(safety): close clearance and courtyard vacuity gaps in
board-defect corpus` — is byte-identical to the subject of `worktree-agent-a011ebcd156551c61`, one of the 15
**already merged** branches. This looks like a duplicate/re-attempt of already-landed work; flagged for a human
to check for redundancy rather than resolved here (its actual diff was not compared against `a011ebcd`'s, out of
this index's read-only scope for judging content, only reporting the coincidence).

### Already merged into local `main` (unpushed) — 15

In `git reflog show main` merge order (most recent first): `aec27330dae453cf8`, `a5aca7e8513b37a59`,
`a6b63447d842be005`, `aa7807dfb7e22b39d`, `a722e73b1b54f65e2`, `a29ddea7502ada4f9`, `adfbaf643bff63678`,
`a011ebcd156551c61`, `a4b384c0ecba0f83c`, `aeca6c1867f7ee52e`, `aa589e7fbf2227d3e`, `ac631b39bdae6694a`,
`a8323afb0cfc6c282`, `a891b6e219c527e05`, `a42cb017e1efe4d83`. These need no further action beyond the eventual
`main` → `origin/main` push (see Executive Summary item 1).

### Full table (all 66)

| Branch | Tip (short) | Commits ahead | Merge (vs local `main`) | Top commit | Diffstat |
|---|---|---|---|---|---|
| `worktree-agent-a011ebcd156551c61` | `60f38a1d` | 0 | CLEAN (already merged) | feat(safety): close clearance and courtyard vacuity gaps in board-defect corpus | — |
| `worktree-agent-a01e886bc9b262bbd` | `0e792442` | 2 | CONFLICT (baseline only) | fix(router): make the router structurally unable to silently do nothing | 35 files, +1134/-149 |
| `worktree-agent-a09b73d5391322d6d` | `6a5758b8` | 6 | CONFLICT (baseline + `_adapter_convert.py`) | measure(router): U5 production-board CNF measurement — pruning ~0% reduction, both paths OOM before CNF encoding under 8GB gate | 34 files, +1706/-173 |
| `worktree-agent-a0a80b656eee7479f` | `4f0e138b` | 4 | CONFLICT (baseline only) | docs(cp-sat): record the completed Pumpkin differential (108/108 runs, zero soundness disagreements) | 36 files, +5667/-112 |
| `worktree-agent-a1087c2ce1ce15224` | `7e1194b7` | 1 | CONFLICT (baseline only, zero unique content) | fix(ci): unbreak main — codegen drift + dead mutation scaffolding (2 of 8) (#911) | 26 files, +274/-112 |
| `worktree-agent-a11904da8310c7be8` | `07d514f9` | 3 | CONFLICT (baseline + `_adapter_convert.py`) | perf(router): replace O(components²·nodes²) island bridging with KD-tree + Kruskal MST | 31 files, +1110/-156 |
| `worktree-agent-a1334325f3f9a275c` | `c0524515` | 3 | CONFLICT (baseline only) | feat(simulation): ZVS margin sweep across the pan-load envelope, 88uH coil + re-derived in-band pan coupling | 30 files, +4916/-340 |
| `worktree-agent-a145fb5861feb54a0` | `2be59df0` | 1 | **CLEAN, unmerged** | chore(ci): seed R14 BOM<->source backlog so the gate stops blocking main | 3 files, +822/-29 |
| `worktree-agent-a14cebd66c9c866e4` | `6a5758b8` | 6 | CONFLICT (baseline + `_adapter_convert.py`) | measure(router): U5 production-board CNF measurement (dup of a09b73d5) | 34 files, +1706/-173 |
| `worktree-agent-a155a16122a1f08e9` | `7ba25800` | 2 | CONFLICT (baseline only) | measure(ci): establish kicad-cli sustained DRC/ERC throughput baseline for R7 | 27 files, +630/-112 |
| `worktree-agent-a1aa462151b15c5fb` | `5ae30d0a` | 10 | **CLEAN, unmerged** | ci: wire the 7 unmerged gate branches into CI, with dated backlogs | 71 files, +11833/-157 |
| `worktree-agent-a1edfc6c42603e6ca` | `07d514f9` | 3 | CONFLICT (baseline + `_adapter_convert.py`, dup of a11904da) | perf(router): KD-tree + Kruskal MST (dup) | 31 files, +1110/-156 |
| `worktree-agent-a23b6302b2fbc5ef7` | `3c803996` | 2 | CONFLICT (baseline only) | docs(evidence): reconcile creepage authority disagreement and routing_copper_pullback +42 | 27 files, +641/-112 |
| `worktree-agent-a29ddea7502ada4f9` | `b0bf128c` | 0 | CLEAN (already merged) | fix(wasm): make per-net component_refs deterministic across processes | — |
| `worktree-agent-a3922a000cee7fcd7` | `0975613a` | 2 | CONFLICT (baseline only) | measure(wasm): record U8 volume run as BLOCKED — no Cloudflare credentials | 27 files, +395/-112 |
| `worktree-agent-a3937a7ac5c9edbaf` | `ce91fead` | 2 | CONFLICT (baseline only) | feat(safety): close clearance and courtyard vacuity gaps (possible dup of a011ebcd — moved mid-session, see note above) | 32 files, +1072/-131 |
| `worktree-agent-a42cb017e1efe4d83` | `41d73a90` | 0 | CLEAN (already merged) | docs(strategy): correct forward — design work landed, verification integrity is now the critical path | — |
| `worktree-agent-a478ff80bf43617f3` | `d2edc095` | 2 | CONFLICT (baseline only) | feat(firmware): exhaustive state-machine model check and invariant proofs | 45 files, +3466/-112 |
| `worktree-agent-a47ca6b98e5824e78` | `1e932217` | 2 | CONFLICT (baseline only) | feat(cp-sat): build BLOCKER-ORTOOLS equivalence harness + independent verifier | 29 files, +2261/-112 |
| `worktree-agent-a4aa6be2eecbea4e8` | `38158720` | 2 | CONFLICT (baseline only) | fix(router): use int8 occupancy grids in router_v6 test fixtures | 28 files, +304/-115 |
| `worktree-agent-a4af27712ab303bd0` | `77cc3b90` | 5 | CONFLICT (baseline + `docs/plans/README.md`) | docs(plans): implementation-ready plans for WASM tier Phases 2-4 | 30 files, +2302/-115 |
| `worktree-agent-a4b384c0ecba0f83c` | `9dea9105` | 0 | CLEAN (already merged) | docs(evidence): router silent no-op diagnosis — transition commit, invalidated measurements, #871 status | — |
| `worktree-agent-a4d40ed44d5901b8e` | `8102fdb0` | 2 | CONFLICT (baseline only) | test(firmware): harden SIL soft assertions, expand fault-class × origin-state coverage | 47 files, +2640/-211 |
| `worktree-agent-a53680cc11536a678` | `e8495383` | 5 | CONFLICT (baseline only) | Merge remote-tracking branch 'origin/main' — bundles ERC baseline, cp-sat re-check, continue-on-error triage + ERC gate | 38 files, +1146/-168 |
| `worktree-agent-a59426d220cfee077` | `12d0df06` | 1 | **CLEAN, unmerged** | fix(ci): register all 20 firmware test binaries and run the full suite | 3 files, +34/-13 |
| `worktree-agent-a5aca7e8513b37a59` | `63ca7f3c` | 0 | CLEAN (already merged) | fix(router): thread netclass creepage_mm into stage0 NetClassRules | — |
| `worktree-agent-a5c051454a485eee7` | `cba26cb1` | 3 | CONFLICT (baseline only) | fix(router): close the remaining seven vacuous stage validators; add creepage-authority gate | 46 files, +2770/-159 |
| `worktree-agent-a5fe2185471a5f4b9` | `d3f686c0` | 2 | CONFLICT (baseline only) | feat(ci): mechanize the plane-condemnation quantifier bug as a gate | 33 files, +1195/-112 |
| `worktree-agent-a60e66c320b72c098` | `beac01c8` | 4 | CONFLICT (baseline + `test_bottleneck_geometry.py`) | fix(router_v6): reject stage0 NetClassRules instead of silently defaulting | 42 files, +721/-158 |
| `worktree-agent-a671f1b607d4fe283` | `300c4a70` | 3 | CONFLICT (baseline only) | fix(elec): drop ZCD_ISO from the split-board SELV interface contract | 32 files, +645/-320 |
| `worktree-agent-a681a84f1f1282eb8` | `6665aa3c` | 2 | CONFLICT (baseline only) | test(ci): add drift test for unreferenced router_v6 test files | 29 files, +1155/-112 |
| `worktree-agent-a6a351ebefa8e55c0` | `7ed0a5ac` | 2 | CONFLICT (baseline only) | docs(reports): pre-push verification of local main's 32-commit merge vs origin/main | 27 files, +444/-112 |
| `worktree-agent-a6b63447d842be005` | `e58ea868` | 0 | CLEAN (already merged) | feat(router): expose enable_geographic_pruning through route_pcb() | — |
| `worktree-agent-a703dc569258f6c0f` | `a3fc2d1e` | 2 | CONFLICT (baseline only) | docs(reference): verified branch-protection promotion recommendation | 27 files, +560/-112 |
| `worktree-agent-a722e73b1b54f65e2` | `f74dc7fd` | 0 | CLEAN (already merged) | docs(wave4): record KTD8 overturn — bit-exact Rust EDT | — |
| `worktree-agent-a79e198a124568852` | `c3305915` | 2 | CONFLICT (baseline only) | docs(hardware): OCP-02 decision brief — recommend second CT at DC_BUS_RTN | 27 files, +742/-112 |
| `worktree-agent-a7dd06bfdbfd7bd77` | `bacba3a4` | 5 | CONFLICT (baseline + 4 files, largest genuine conflict) | feat(geometry): migrate routability_check.py off scipy.ndimage.label (KTD8 follow-up) | 45 files, +5176/-172 |
| `worktree-agent-a8323afb0cfc6c282` | `4ae6f632` | 0 | CLEAN (already merged) | test(drc): add in-crate coverage for the three safety DRC rules | — |
| `worktree-agent-a83609cb5411455d2` | `6665aa3c` | 2 | CONFLICT (baseline only, dup of a681a84f) | test(ci): drift test for unreferenced router_v6 test files (dup) | 29 files, +1155/-112 |
| `worktree-agent-a891b6e219c527e05` | `f1c24282` | 0 | CLEAN (already merged) | docs(plans): triage all 202 plans for superseded/landed/active status | — |
| `worktree-agent-a8def5ac8f4718109` | `537def67` | 3 | CONFLICT (baseline only) | docs(hardware): low-line AC input overcurrent decision brief | 31 files, +1953/-112 |
| `worktree-agent-a97cdea26fe0b4c1c` | `9f47fbf5` | 5 | CONFLICT (baseline only) | **Meta-merge**: `a1334325` (ZVS sweep) + `aa67f41e` (part-stress audit) reconciled together | 34 files, +6197/-340 |
| `worktree-agent-a988999c6631ea9c2` | `2f24bef6` | 7 | CONFLICT (baseline only) | **Meta-merge**: `a01e886b` (router silent-no-op fix) + `a681a84f`/`a83609cb` (router_v6 drift test) + 3 own fixes (router_v6 differential, vacuous gates, regression-cache atomicize) | 51 files, +2561/-181 |
| `worktree-agent-aa589e7fbf2227d3e` | `2ebf226f` | 0 | CLEAN (already merged) | fix(ci): verify measured_at_commit resolvability, close the dangling-SHA gap | — |
| `worktree-agent-aa67f41e27bcc423b` | `a650659e` | 2 | CONFLICT (baseline only) | docs(hardware): part stress vs abs-max audit, plus re-runnable gate | 30 files, +1555/-112 |
| `worktree-agent-aa7807dfb7e22b39d` | `1efa1cb3` | 0 | CLEAN (already merged) | feat(router): migrate EDT call sites to Rust exact_edt_transform (KTD8) | — |
| `worktree-agent-aaaac157441fa01a8` | `34aba859` | 3 | CONFLICT (baseline only) | docs(hardware): OCP-02 second-CT placement feasibility — fits with a re-place | 28 files, +1041/-112 |
| `worktree-agent-ab3a5bcd917b9e190` | `96fb2f17` | 6 | CONFLICT (baseline only) | docs(hardware): coil pad current rating brief — LitzPad_15A is unfounded | 35 files, +6596/-340 |
| `worktree-agent-abf95b30125935383` | `07d514f9` | 3 | CONFLICT (baseline + `_adapter_convert.py`, dup of a11904da) | perf(router): KD-tree + Kruskal MST (dup) | 31 files, +1110/-156 |
| `worktree-agent-ac1e97849a1e8a54b` | `437dfc84` | 2 | CONFLICT (baseline only) | docs(evidence): confirm all 163 ERC endpoint_off_grid warnings are cosmetic | 30 files, +885/-114 |
| `worktree-agent-ac631b39bdae6694a` | `0b0c4f4a` | 0 | CLEAN (already merged) | feat(wave4): record R1 python-removal verdicts alongside R7's | — |
| `worktree-agent-acca281869a5601ab` | `b2400b67` | 2 | CONFLICT (baseline only) | docs(evidence): WASM tier Phase 2-4 status, R4-R8 evidence map, R8/#871 reachability | 27 files, +896/-112 |
| `worktree-agent-acf6badeed2dfe305` | `7e1194b7` | 1 | CONFLICT (baseline only, zero unique content, this session's own branch) | fix(ci): unbreak main (#911) | 26 files, +274/-112 |
| `worktree-agent-ad6d49136abdf2281` | `7e1194b7` | 1 | CONFLICT (baseline only, zero unique content) | fix(ci): unbreak main (#911) | 26 files, +274/-112 |
| `worktree-agent-ad9ce7411805de565` | `c57101ac` | 2 | CONFLICT (baseline only) | fix(cache): scope, atomicize, and re-key the global EDT disk cache | 28 files, +738/-125 |
| `worktree-agent-add6fe8eba1f890f4` | `404803b3` | 1 | **CLEAN, unmerged** | fix(ci): guard the DRC ratchet's single-sample assumption against measured noise | 4 files, +535/-14 |
| `worktree-agent-adea9e1d805efd923` | `2a2f2fa7` | 2 | CONFLICT (baseline only) | fix(ci): clear evidence-provenance backlog and anchor the reference manifest | 88 files, +674/-146 |
| `worktree-agent-adee024249f564698` | `8abcec24` | 2 | CONFLICT (baseline + `_adapter_convert.py`) | fix(router): open F.Cu/B.Cu to real routing instead of the plane-condemnation fallback | 29 files, +343/-115 |
| `worktree-agent-adfbaf643bff63678` | `0e29a88d` | 0 | CLEAN (already merged) | fix(design-bundle): make BoardState.nets order-preserving, not HashMap-derived | — |
| `worktree-agent-ae8fccd26c6009709` | `7e1194b7` | 1 | CONFLICT (baseline only, zero unique content) | fix(ci): unbreak main (#911) | 26 files, +274/-112 |
| `worktree-agent-aec0cae1c50edf2a0` | `2113b201` | 5 | **CLEAN, unmerged** | docs(hardware): propose BOM<->source reconciliation for the 49-finding R14 backlog | 22 files, +1304/-130 |
| `worktree-agent-aec27330dae453cf8` | `cfc81fab` | 0 | CLEAN (already merged) | feat(ci): add BOM<->source reconciliation gate (R14) | — |
| `worktree-agent-aec4a46590b7d9ffa` | `979bafe5` | 2 | CONFLICT (baseline only) | feat(elec): add netlist-stage checks gate (single-pin nets, unconnected power pins, voltage-domain compatibility) | 31 files, +1858/-114 |
| `worktree-agent-aeca6c1867f7ee52e` | `850fc85e` | 0 | CLEAN (already merged) | fix(types): repair type-check gate — 258 -> 217 errors, baseline held at 217 | — |
| `worktree-agent-af448502d9c6417ca` | `07d514f9` | 3 | CONFLICT (baseline + `_adapter_convert.py`, dup of a11904da) | perf(router): KD-tree + Kruskal MST (dup) | 31 files, +1110/-156 |
| `worktree-agent-afefd5add15cfaca4` | `979bafe5` | 2 | CONFLICT (baseline only, dup of aec4a465) | feat(elec): netlist-stage checks gate (dup) | 31 files, +1858/-114 |

---

## 2. Document index by theme

34 documents were added across the union of all 66 branches plus local `main`'s own 15 already-completed merges
(deduplicated; a document counted once even if two branches independently add it — see divergence notes).

### Router / verification (CP-SAT, router_v6, EDT/geometry correctness)

- `docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` — `a11904da`/`a1edfc6c`/`abf95b30`/`af448502` (dup tips)
- `docs/evidence/2026-08-07-pruned-encoding-measurement.md` — `a09b73d5`/`a14cebd6` (dup tips)
- `docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md` — `a681a84f`/`a83609cb`/`a988999c`
- `docs/evidence/2026-08-07-cpsat-equivalence-harness.md` (+ `.py`/`.json` companions) — `a0a80b656`/`a47ca6b98`
- `docs/evidence/2026-08-07-pumpkin-engine-differential.md` (+ `docs/evidence/2026-08-07-pumpkin-engine/` Rust crate, `docs/evidence/2026-08-07-pumpkin-equivalence-run.py`, `-summary.json`) — `a0a80b656`
- `docs/evidence/2026-08-07-rust-connected-components-spike.md` — `a7dd06bfdbfd7bd77`
- `docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md` — `a155a161`/`a4af2771`

### Rust consolidation (KTD8 / EDT migration)

- `docs/evidence/2026-08-07-exact-edt-rust-spike.md` — already merged (part of local `main`'s 15) and independently added by `a7dd06bfdbfd7bd77`
- `docs/wave4-verdicts.yaml` KTD8-overturn entries — `a722e73b1b54f65e2` (already merged) — recorded "bit-exact Rust EDT" overturning a prior verdict
- EDT call-site migration itself (code, not a new doc) — `aa7807dfb7e22b39d` (already merged)
- `docs/evidence/2026-08-07-pre-push-verification-32-commit-merge.md` — `a6a351ebefa8e55c0`, documents the same local-`main`-vs-`origin/main` divergence this index independently re-derives in the Executive Summary

### WASM tier

- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` — `a4af2771`/`acca2818`
- `docs/evidence/2026-08-07-wasm-tier-u8-volume.md` — `a3922a000cee7fcd7` (records the run as **BLOCKED** — no Cloudflare credentials, not a code or decision gap)
- `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` — `a4af2771`

### Hardware / safety

- `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md` — `aec0cae1c50edf2a0` (clean, unmerged)
- `docs/hardware/PART_STRESS_AUDIT.md` — carried identically (md5-verified by the verification sub-agent) on 5 branches: `a1aa4621`, `a8def5ac`, `a97cdea2`, `aa67f41e`, `ab3a5bcd` — **no draft divergence**, safe to treat any one copy as canonical
- `docs/hardware/COIL_PAD_CURRENT_BRIEF.md` — `ab3a5bcd917b9e190`
- `docs/hardware/LOW_LINE_OVERCURRENT_BRIEF.md` — `a8def5ac8f4718109`
- `docs/hardware/OCP02_DECISION_BRIEF.md` — `a79e198a`/`aaaac157` (byte-identical across both)
- `docs/hardware/OCP02_CT_PLACEMENT_FEASIBILITY.md` — `aaaac157441fa01a8`
- `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md` — `a23b6302b2fbc5ef7`
- `docs/evidence/2026-08-07-erc-off-grid-endpoint-analysis.md` — `a1aa4621`/`ac1e9784`
- `docs/evidence/2026-08-07-zvs-margin-sweep.md` (+ `.json`) — `a1334325`/`a97cdea2`/`ab3a5bcd`
- `docs/evidence/2026-07-30-zcd-optocoupler-removal.md` — `a671f1b607d4fe283`
- `docs/evidence/2026-08-07-clearance-courtyard-corpus-coverage.md` — already merged (`a011ebcd`/`a3937a7`)
- `docs/hardware/RTD_PROBE_INTERFACE_ANALYSIS.md` — `worktree-agent-afefd5add15cfaca4`, commit `3a4431ff` (found
  and committed post-review — see Decision List item 8)
- `docs/hardware/BUS_CAPACITOR_RIPPLE_BRIEF.md` — `worktree-agent-a97cdea26fe0b4c1c` (found post-review; **still
  uncommitted/untracked in that branch's own worktree as of this writing** — see Decision List item 5)

### CI / gates

- `docs/reference/branch-protection-recommendation.md` — `a703dc569258f6c0f`
- `bom-reconciliation-allowlist.yaml` / R14 gate script — `a145fb5861feb54a0` (backlog seed) + `aec27330dae453cf8` (gate itself, already merged)
- (no new standalone doc, but notable) `scripts/check_bom_source_reconciliation.py`, `scripts/part_stress_gate.py` + `scripts/part_stress_limits.yaml` — code, see Decision List item 11
- `power_pcb_dataset/drc_ceiling.json`'s `2026-08-07-oracle-repin-10.0.5` `_march` entry — `fix/drc-ceiling-remeasure-10.0.5`
  (`835474e4`, outside the `worktree-agent-*` naming pattern, added post-review — see §1's scope correction and
  Decision List item 10)

### Planning

- `docs/plans/PLAN_TRIAGE_2026-08-07.md` — already merged (`a891b6e219c527e05`, triages all 202 plans)
- `docs/strategy` update — already merged (`a42cb017e1efe4d83`)
- `docs/evidence/2026-08-07-router-silent-noop-diagnosis.md` — already merged (`a4b384c0ecba0f83c`)

---

## 3. Decision list — findings that need a human call

Verified against source documents (via `git show <branch>:<path>`, not the working tree, since most of these
live only on unmerged branches) by an independent read-only sub-pass. Status legend: **CONFIRMED** (matches
claim as stated), **PARTIALLY CONFIRMED** (real finding, but the cited number differs from the source),
**CANNOT VERIFY** (no matching claim found in any of this session's documents), rated tier where the source
states one.

1. **Bus-discharge resistors — CONFIRMED.** `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md` (`aec0cae1c50edf2a0`)
   §1.1: BOM's `R_DIS1A/1B/2A/2B` at 4.7kΩ → 65.35s discharge (source of "65.4s"); circuit source
   (`elec/src/modules.ato`) uses 3.9kΩ → 56.94s. Target is <60s. **Recommendation:** update BOM to
   3.9kΩ/`AC05000003901JAC00`. Nothing blocked on this beyond the edit itself — a straight BOM fix.
2. **THM-01/THM-02 hysteresis — CONFIRMED.** Same document §1.3: BOM's superseded divider gives 5.6°C
   (THM-01, need 15°C) and 6.6°C (THM-02, need 20°C); current source (post-commit `a4fb15dc`) already gives
   15.2°C/19.9°C. **New finding**, not previously documented elsewhere. **Recommendation:** update 6 BOM rows to
   the post-`a4fb15dc` values (MPNs listed in the doc).
3. **`R_OCP_REF_T` — CONFIRMED.** Same doc §1.2: BOM costs `RC0603FR-073K2L`, not a real E24/E96 part (zero
   distributor hits). Source already uses `RC0603FR-073K24L` (3.24kΩ) since the `a4fb15dc`-era work — no
   residual electrical defect, pure BOM staleness. Low urgency (nobody can order the fake part, so it can't
   silently ship wrong).
4. **Netclass creepage 6.0mm vs 8.0mm — CONFIRMED.** `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md`
   (`a23b6302b2fbc5ef7`): the netclass scalar in `design_rules.py` declares a flat 6.0mm for
   ACMains/HighVoltage/HighVoltageIsolated; the actually-enforced `IEC60335_REQUIREMENTS` matrix (already the
   sole authority consumed by the CP-SAT solve path) carries the correct 8.0mm reinforced figure. **Recommendation:**
   make the matrix the sole authority and raise the netclass scalar to 8.0mm (kept, not deleted — used elsewhere
   as a routing-corridor hint) — a one-line change in `design_rules.py` + `configs/netclass_rules.yaml`, left for
   a maintainer to apply.
5. **Bus capacitors at ~3.6× rated ripple — CONFIRMED, as a revision, not an error to correct toward one side.**
   Two real, sequential documents carry two real, different figures, and both should be cited together:
   `docs/hardware/PART_STRESS_AUDIT.md` §1.1 (identical on all 5 carrying branches) derives **4.2×–5.8×** (central
   4.8×) from an OCP-01-trip-threshold current bound (35.4–40A rms, a proxy, not a direct operating-point figure).
   `docs/hardware/BUS_CAPACITOR_RIPPLE_BRIEF.md` (found on `worktree-agent-a97cdea26fe0b4c1c`, currently
   **uncommitted/untracked** in that branch's own worktree — same at-risk-of-loss pattern as the RTD doc before it
   was committed; not yet safe) revises this to **3.4×–5.2×, central 3.6×**, using the ZVS margin sweep's
   model-derived tank current at the corrected ~46kHz operating point instead of the OCP-01 proxy bound. The
   later document explicitly reconciles against the earlier one (§1.1: "verdict unchanged: still FAILS... smaller
   than the previously-published 4.2×–5.8×... because the corrected tank-current model is lower than the
   OCP-01-trip bound previously used") — this is a genuine model refinement, not a contradiction to resolve by
   picking a side. **Record both, with the later (3.4–5.2×, central 3.6×) as current-best.**
   The more important, independently reproduced conclusion in the later brief: the overload is **topological, not
   part-sizing**, and now quantified further than the original audit did — the 60Hz mains-recharge (line-frequency)
   term is **65% of the quadrature sum** (15.73²=247.4 of 247.4+133.9=381.3), traced to an undocumented,
   unjustified bulk-capacitance target; closing it by widening the doubler's conduction angle alone would require
   **θ≈256°**, which is impossible for a passive cap-input doubler (θ cannot exceed 360°, and reaching anywhere
   near that needs source impedance dominated by a large series inductor — i.e. a different front-end, not a
   smaller capacitor). Even a mathematical floor of zero bulk capacitance still leaves a 2.14× failure from the
   switching-frequency term alone. **Recommendation in the later brief:** do not re-select bus capacitors this
   round; commission the missing doubler/source-impedance SPICE model and pursue a topology-level fix, treating
   part swaps/more-parallel-caps as a secondary, complementary measure once the topology fix is sized. **Blocked
   on:** a human accepting or rejecting that recommendation, and — separately and first — someone committing
   `BUS_CAPACITOR_RIPPLE_BRIEF.md` before it is lost.
6. **`LitzPad_15A` — CONFIRMED, including the derivation.** `docs/hardware/COIL_PAD_CURRENT_BRIEF.md`
   (`ab3a5bcd917b9e190`): the 15A rating is an undocumented bare declaration; the module's own sizing heuristic is
   commented out (applying it to the actual pad geometry implies 50A). Applying this repo's 1.5× margin convention
   to the corrected 46kHz/24.5A rms operating point gives **≥36.75A rms** exactly as stated. **Blocked on:** a
   replacement part/joint decision — the brief recommends a standards-rated screw terminal (Phoenix Contact MKDS
   family) but leaves the specific higher-current variant unresolved.
7. **16A fuse at low-line — CONFIRMED, with an added nuance.** `docs/hardware/LOW_LINE_OVERCURRENT_BRIEF.md`
   (`a8def5ac8f4718109`): 18.1–19.6A through `F1`/`L1` at 108V matches exactly. The NEC-80%-exceeded claim is real
   but more specific: it's NEC 210.23(A)'s 80%-continuous-load rule for cord-and-plug-connected branch circuits
   (12A cap on a 15A circuit) — even **nominal** 120V/15A already exceeds that 12A limit for a >3hr run. Both a
   fuse-rating problem and a separate branch-circuit-code problem are open; neither is resolved in the brief.
8. **RTD probe connector absent → PID-01…04 unreachable — CONFIRMED.** The source document,
   `docs/hardware/RTD_PROBE_INTERFACE_ANALYSIS.md`, existed but was **uncommitted** in
   `worktree-agent-afefd5add15cfaca4`'s own worktree when this index was first drafted (the agent that produced it
   was never instructed to commit) — that is why the first pass found nothing. It has since been committed as
   `3a4431ff` on that branch and is now verified directly: `RTDSensing` (MAX31865) is the dedicated
   pan-temperature probe, with a production firmware driver (`firmware/components/sensors/`) and a mount spec
   (`docs/SENSOR_MOUNT_DESIGN.md`), but **no connector exists anywhere** — not in `elec/src/*.ato`, not in the
   netlist, not on the board — while `docs/CONNECTORS_AND_WIRING.md` independently specifies `J_RTD1` (JST XH
   4-pin, confirmed present in that file at line 15/37) with a pinout matching the MAX31865 FORCE/RTDIN pins
   exactly. Neither NTC can substitute (both measure component temperature — heatsink, coil — not pan/food
   temperature, and the coil NTC isn't even digitized, analog-comparator binary-fault only). The doc notes this
   gap was already recorded twice before and never acted on (`RTD_SAFETY_DUAL_PATH.md:292-299`, a code comment at
   `test_routability_check.py:459-478`). **Recommendation:** implement the existing `J_RTD1` spec rather than
   re-scope the PID gates (re-scoping would ship an unverifiable temperature-control claim). **Blocked on:** a
   human accepting that recommendation and an `elec/` owner implementing the connector.
9. **OCP-02 second-CT placement — CONFIRMED.** `docs/hardware/OCP02_CT_PLACEMENT_FEASIBILITY.md`
   (`aaaac157441fa01a8`): "fits, but only with a re-place — not a drop-in"; legal placements are displaced
   ~40–44mm from `U6`'s `DC_BUS_RTN` pad. Conclusion explicitly reopens Option B (bias-supply scope) as a live
   alternative. `OCP02_DECISION_BRIEF.md` is byte-identical across its two carrying branches — no divergence risk.
   **Blocked on:** choosing between the re-place and Option B.
10. **`via_dangling` ceiling raise needs approval — CONFIRMED as a real, live, pending decision; the specific
    `e5a89b1e` attribution in the original claim is not supported by the source and should be dropped.** The
    original enumeration missed this because the branch it lives on, `fix/drc-ceiling-remeasure-10.0.5`
    (`835474e4`), does not match the `worktree-agent-*` pattern this index scanned (see §1's scope correction) —
    it genuinely is true that no `worktree-agent-*` branch touches `power_pcb_dataset/drc_ceiling.json`, but that
    was the wrong universe to check. Verified directly against that commit and its `_march` entry
    (`2026-08-07-oracle-repin-10.0.5`): `via_dangling` measured 32/32 samples against a committed ceiling of 15
    (+17) and is deliberately withheld pending a maintainer's `Ceiling-Approval:` trailer, per the R27 "do not
    ratchet past an unexplained rise" rule. **However**, `e5a89b1e` is mentioned nowhere in that commit, its diff,
    or its `_march` text (`git show 835474e4:power_pcb_dataset/drc_ceiling.json | grep e5a89b1e` returns nothing).
    The source's own attribution is the **opposite shape** from the claim: it argues the +17 is *very likely the
    kicad-cli 10.0.4→10.0.5 (or platform) oracle-version delta* — cross-checked by finding the identical constant
    "+17 via_dangling" delta on multiple unrelated PRs/pushes regardless of what each touched, which a
    per-commit routing regression would not produce — and explicitly frames this as circumstantial, not proof,
    which is exactly why it's left for a maintainer rather than self-approved. So: the decision is real
    (approve or reject a `via_dangling` ceiling raise from 15 to 32), but it is attributed to **a tool/platform
    version change, not to any specific commit** — `e5a89b1e` does not belong in this claim as sourced. **Blocked
    on:** a maintainer's `Ceiling-Approval:` review of whether the 10.0.4→10.0.5 attribution is correct before
    the ceiling is raised.
11. **`part_stress_gate.py` backlog removal — likely a misattribution.** `scripts/part_stress_gate.py`
    (`ab3a5bcd917b9e190` etc.) has **no backlog/allowlist mechanism** — it's standalone and, per its own
    docstring, **not wired into any CI workflow** (confirmed independently: no reference to it in `.github/` or
    `scripts/manifest.yaml` in the working tree). There is nothing to "remove a backlog" from. The backlog-removal
    pattern that does exist in this session is the **R14 BOM↔source reconciliation gate**
    (`worktree-agent-a145fb5861feb54a0`: "seed R14 BOM<->source backlog so the gate stops blocking main",
    `bom-reconciliation-allowlist.yaml`, 49 seeded findings). Recommend treating this decision as being about the
    R14 allowlist, not `part_stress_gate.py` — easy to conflate since both stem from the same hardware-audit push.
    **Blocked on:** whether to let R14's allowlist expire/shrink (blocking) vs. keep it open-ended.

---

## 4. Merge-order recommendation

### Step 0 — prerequisite, unlocks the majority of the rest

Resolve the local-`main`-vs-`origin/main` divergence (Executive Summary item 1) **before** merging any
`worktree-agent-*` branch. This is a maintainer decision, not a mechanical union: the "four `.pyi` stubs" framing
undersells the work. Verified directly (`git diff main origin/main -- <path>` and `git show <ref>:<path>`):

- 3 files are genuine **add/add** (`deterministic_leaves.pyi`, `kicad_exporter_geometry.pyi`,
  `write_board_geometry.pyi`) — but the two sides are not additive drafts of the same stub, they're **differently
  scoped**: local `main`'s version of `deterministic_leaves.pyi` is 70 lines with precise per-function signatures;
  `origin/main`'s is 20 lines using `*args: Any, **kwargs: Any)` throughout. A plain union produces duplicate,
  contradictory declarations for the same functions, not a merge.
- `__init__.pyi` is a **content conflict**, not add/add, with the same precision-vs-looseness disagreement (e.g.
  `pcl_parse_tier(...) -> ConstraintTier` vs `-> Any`; `ComponentRef.__init__(self, ref: Any)` vs `(self, refdes:
  str)`).
- 5 more content conflicts, not mentioned in the task's four-stub framing at all:
  `packages/temper_placer/{core/manufacturing.py, core/placement_drc.py,
  deterministic/stages/drc_sweep.py, regression/drc_ratchet.py, router_v6/routing_demand.py}`.

**Recommendation:** a maintainer picks the winning typing convention (local `main`'s precise stubs look more
complete and are what 15 already-landed branches were built against) and reconciles all 9 files in one commit,
then decides whether/when to push local `main` to `origin/main`.

### Step 1 — merges cleanly today, independent, no dependency on Step 0

`worktree-agent-a145fb5861feb54a0`, `worktree-agent-a1aa462151b15c5fb`, `worktree-agent-a59426d220cfee077`,
`worktree-agent-aec0cae1c50edf2a0`, `worktree-agent-add6fe8eba1f890f4`. These are genuinely conflict-free against
local `main` right now — safest immediate merges, in any order (no cross-dependency detected between them).

### Step 2 — needs sequencing: unlocked entirely by Step 0

The 36 baseline-only-conflict branches become clean the moment Step 0 lands, with **no further reconciliation**.
Recommend merging in this order:

1. First, the 5 duplicate-tip groups collapse to their single distinct commit each — merge one representative per
   group, not all four/two copies (`07d514f9` group: pick one of `a11904da8310c7be8` / `a1edfc6c42603e6ca` /
   `abf95b30125935383` / `af448502d9c6417ca`; `6665aa3c` group: pick one of `a681a84f1f1282eb8` /
   `a83609cb5411455d2`; `979bafe5` group: pick one of `aec4a46590b7d9ffa` / `afefd5add15cfaca4`). The 4
   zero-content branches at `7e1194b7` need no merge at all.
2. Then the remaining independent single/short-chain branches, in any order — no dependency was found between
   e.g. the WASM-tier branches, the hardware-brief branches, or the CI-gate branches.

### Step 3 — needs sequencing: genuine extra conflicts, beyond Step 0

Four distinct real conflicts remain after Step 0, affecting 10 branch names but really only **4 unique fixes**
(three of the four `_adapter_convert.py` conflicts are the same file inherited down one lineage):

1. `packages/temper_placer/router_v6/_adapter_convert.py` — inherited by the entire `8abcec24 → 07d514f9 →
   6a5758b8` lineage (`adee024249f564698` is the root; `a11904da`/`a1edfc6c`/`abf95b30`/`af448502` build on it;
   `a09b73d5`/`a14cebd6` build further still). Resolve once, at the root, then the chain carries no more of this
   conflict.
2. `docs/plans/README.md` — `worktree-agent-a4af27712ab303bd0` (WASM tier plans index entry); likely a trivial
   line-ordering conflict, lowest priority to resolve.
3. `packages/temper-placer/tests/router_v6/test_bottleneck_geometry.py` — `worktree-agent-a60e66c320b72c098`.
4. `docs/wave4-verdicts.yaml`, `packages/temper-geometry/src/{bridge.rs,lib.rs}`,
   `packages/temper-placer/src/temper_placer/router_v6/routability_check.py` —
   `worktree-agent-a7dd06bfdbfd7bd77`, the largest genuine conflict. Expected: it's KTD8/EDT-era Rust geometry
   work colliding with the KTD8 work local `main` already absorbed via 3 of its 15 already-merged branches
   (`aa7807dfb7e22b39d`, `a722e73b1b54f65e2`, `adfbaf643bff63678`) — needs a maintainer or the branch's own author
   to reconcile against what already landed, not a mechanical resolution.

### Step 4 — meta/reconciliation branches: supersede their sources, verify before merging either

- `worktree-agent-a97cdea26fe0b4c1c` already combines `a1334325f3f9a275c` (ZVS margin sweep) +
  `aa67f41e27bcc423b` (part-stress audit) into one reconciled branch — merge `a97cdea2` in place of both sources,
  not all three.
- `worktree-agent-a988999c6631ea9c2` already combines `a01e886bc9b262bbd` (router silent-no-op fix) +
  `a681a84f1f1282eb8`/`a83609cb5411455d2` (router_v6 drift test) + 3 further original fixes (router_v6
  differential-failure fix, vacuous-gates closure, regression-cache atomicize) — merge `a988999c` in place of
  those sources.
- `worktree-agent-a53680cc11536a678` is a self-contained reconciliation of 3 CI commits (real ERC baseline
  measurement, completed cp-sat re-check, continue-on-error triage + ERC gate) against `origin/main` — still
  needs Step 0 applied on top since it wasn't reconciled against local `main`'s extra 33 commits.

---

## 5. What remains open

### Blocked on a human decision

Items 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 from the Decision List (§3) — each names a specific choice (which BOM
value, which typing convention for the `.pyi` reconciliation, which netclass authority, which coil-pad terminal,
which bus-capacitor remedy (or the topology-level fix instead), whether to implement the `J_RTD1` connector,
which OCP-02 topology, whether to approve the `via_dangling` ceiling raise, whether the R14 allowlist should
shrink to zero). Item 0 (push local `main` to `origin/main`, and how to resolve the 9-file conflict in doing so)
is itself now a human decision this index surfaces, not merely mechanical.

**Two of these (items 5 and 8) are also blocked on a smaller, more urgent action first: committing the source
document.** `docs/hardware/BUS_CAPACITOR_RIPPLE_BRIEF.md` (item 5) is currently uncommitted/untracked in
`worktree-agent-a97cdea26fe0b4c1c`'s own worktree — the same failure mode `docs/hardware/RTD_PROBE_INTERFACE_ANALYSIS.md`
(item 8) was in until a reviewer committed it as `3a4431ff` mid-review. AGENTS.md already documents this exact
class of loss ("agents have lost work this session by holding commits"); this ripple brief is presently exposed
to it.

### Blocked on infrastructure, not a decision

- WASM tier U8 volume run (`worktree-agent-a3922a000cee7fcd7`) — explicitly recorded BLOCKED for lack of
  Cloudflare credentials, not a design or code gap.
- Router U5 CNF measurement (`6a5758b8` group) — recorded both paths OOM under an 8GB gate before reaching CNF
  encoding; this is a measurement result (pruning ≈0% reduction), not a decision — the next step is scoping a
  different approach or a larger gate budget, which is engineering work, not a call for a human to adjudicate.

### Just not done yet (no decision blocking, only unmerged work)

- All of Step 2/Step 3's branches once their conflicts are mechanically resolved — router_v6 vacuity-guard
  closures, netclass creepage-authority gate wiring, plane-condemnation gate, EDT disk-cache scoping, evidence-
  provenance backlog clearing, type-check baseline repair, firmware SIL/state-machine hardening, WASM tier
  Phase 2-4 plans (drafted, not started).
Items 5, 8, and 10 were reclassified out of this section on review (see §3) — all three are real, sourced, and
now confirmed; none turned out to be "not found." What's left genuinely just-not-done in that neighborhood:
implementing the recommendation in whichever direction each is decided (the `J_RTD1` connector, the bus-cap
topology fix or part swap, the `via_dangling` ceiling update) is unstarted engineering work, separate from the
decision itself.

### Flagged: claims in the task brief that could not be verified as given, or needed correction

- **Item 5**: the "~3.6×" figure is real, but only as the *later, revised* number (`BUS_CAPACITOR_RIPPLE_BRIEF.md`,
  central 3.6×); the audit document alone (`PART_STRESS_AUDIT.md`) says 4.2–5.8× (central 4.8×). Citing either
  alone without the other is incomplete — record both, per the corrected item 5.
- **Item 8** (RTD/PID-01…04): real and now confirmed, but the reason the first pass found nothing was that the
  source document was uncommitted, not that the claim was wrong — a scope/timing artifact, not a content error in
  the original claim.
- **Item 10** (`via_dangling`): the ceiling-raise-pending-approval situation is real, but on a branch
  (`fix/drc-ceiling-remeasure-10.0.5`) outside the `worktree-agent-*` pattern this index originally scanned — a
  scope artifact, not a fabricated claim. The specific `e5a89b1e` attribution, however, **is** unsupported by the
  source: the source attributes the rise to a kicad-cli tool-version change, not to any commit, and `e5a89b1e`
  does not appear in it at all. Use the corrected item 10, not the original claim text, going forward.
- Item 11 as literally stated (`part_stress_gate.py`'s backlog) does not correspond to any actual mechanism —
  that script has no backlog to remove; the backlog that does exist and could plausibly be meant is R14's.
- The task's own framing that `main` is "1 behind `origin/main`" is materially incomplete — see Executive
  Summary item 1.
- The original branch enumeration's scope (`worktree-agent-*` only) missed two branches with real unmerged
  content — see §1's scope correction. One (`fix/drc-ceiling-remeasure-10.0.5`) is genuine session output and is
  now folded into this index; the other (`feat/rust-hardening-pyany-removal-wave3`) is the maintainer's own
  branch and is explicitly out of scope for any merge action here.
