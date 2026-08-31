<!-- provenance: commit=337f3586d8ca1baad7363ec43238649e30ac16e9 dirty=UNKNOWN -->
# Board-Freeze Merge Sequence — decision record & first landing (2026-08-15)

Status: FIRST LANDING DONE — PR #1201 (ZCD removal) pushed with its
same-PR DRC ceiling re-measurement (260 samples, all three gates verified
PASS locally). Awaiting CI green + owner merge; then the resync (#1134)
lands second.

## 1. Purpose

`pcb/temper.kicad_pcb` has diverged across 77+ open PRs into **at least five
distinct board versions**. Parallel merging of board-touching PRs has
**destroyed content twice** (handoff §6). The owner authorized a board-file
freeze + sequential merge strategy: land one board change, rebase the rest
onto it, repeat.

This document records the data-driven decision on merge ordering, the
branch/board matrix it was derived from, and the execution status of the
first landing.

## 2. Board hashes (sha256, first 8 chars shown; full hashes in §5)

| board | meaning |
|---|---|
| `6928b7c8` | main's board at the freeze start (origin/main @ 8f21d2725) |
| `5e5015f8` | ZCD orphan-footprint removal (fix/zcd-orphan-footprint-removal, PR #1201) |
| `b7d865b7` | board resync vs elec/src (commit 96ebe489c, PR #1134 = the hub) |
| `1b15b274` | resync + stackup declaration (fb00ab4f9) + 6-layer decision (e4eaba1cd) — PR #1178 router trunk |
| `a70e34bb` | resync + DRU scoping/copper strip (2dba7ab41) — PR #1157 et al. |
| `a333cf33` | ancient phaseb/verify merge-only branches (no net change, no open PRs) |
| `7b0dbcf4` | old-lineage PD3 creepage-slot board (no open PRs) |
| various | one-off boards (§4 groups D/E) |

## 3. Methodology

Every remote branch (576 refs) was scanned for commits touching
`pcb/temper.kicad_pcb` relative to `origin/main`
(`git log origin/main..<branch> --name-only -- pcb/temper.kicad_pcb`).
75 branches touch the board. For each: tip board sha256, merge-base board
sha256, merge-base commit, and the board-touching commit subjects were
recorded (`/tmp/opencode/board_matrix_sorted.txt`). Branches were then
joined to open PRs (`gh pr list`) and grouped by tip board hash.

Key identity rule (handoff §6): **refdes are not stable across branches** —
D2/R6/R7/R8/R9/R10/U3 name the ZCD circuit on main but the discharge/buck
circuits on the resync board. Every identification below uses footprint
lib, value, position, and Sheetpath, never refdes alone.

## 4. The full matrix (75 board-touching branches, grouped)

### Group A — `b7d865b7` (34 branches): resync-only, all stacked on PR #1134

Each carries exactly one board change: the 96ebe489c resync
(designator renumber, ZCD removal, OCP-02/J_RTD1 additions). All 34 have
byte-identical board content. Base commit: 810e6194 (board 6928b7c8).

| branch | PR | board change |
|---|---|---|
| fix/board-schematic-resync | **#1134 (the hub)** | the resync itself |
| agent/collision-remediation-plan | #1158 | inherits resync |
| agent/hv-net-classification | #1164 | inherits resync |
| agent/hv4-mid-chain-review | #1165 | inherits resync |
| analysis/clearance-1085-remediation-plan | #1141 | inherits resync |
| analysis/creepage-island-t1-structural | #1160 | inherits resync |
| analysis/edge-slot-through-cut-rescue | #1194 | inherits resync |
| analysis/hv-creepage-pd3-gap | #1152 | inherits resync |
| analysis/slot-creepage-rescue | #1155 | inherits resync |
| chore/inert-code-audit | #1189 | inherits resync |
| docs/ocp02-unplaced-subsystem-options | #1151 | inherits resync |
| docs/t2-aperture-ct-replacement-determination | #1191 | inherits resync |
| fix-creepage-slot-claim-correction | #1163 | inherits resync |
| fix/circle-poly-bounds | #1179 | inherits resync |
| fix/dedup-defect-multiplier | #1181 | inherits resync |
| fix/drc-ceiling-track-silk-uncap | #1150 | inherits resync |
| fix/geometry-kernel-consolidation | #1186 | inherits resync |
| fix/hb-gnd-domain-classification-1786647794 | #1145 | inherits resync |
| fix/hb-gnd-hyphen-boundary | #1187 | inherits resync |
| fix/hyphen-boundary-clearance-creepage | #1174 | inherits resync |
| fix/hyphen-netclass-boundary | #1162 | inherits resync |
| fix/oracle-registry-blindspot | #1184 | inherits resync |
| fix/pad-identity-remaining-sites | #1182 | inherits resync |
| fix/pad-identity-ssot | #1180 | inherits resync |
| fix/pd3-k1-c6-part-swap | #1156 | inherits resync |
| fix/placer-fail-closed-collision-guard | #1171 | inherits resync |
| fix/pyo3-dup-kw-boundary-match | #1185 | inherits resync |
| fix/router-net-batching-silent-drop | #1177 | inherits resync |
| fix/silk-overlap-c2-c3 | #1154 | inherits resync |
| fix/t2-repair-entrypoint | #1144 | inherits resync |
| fix/trace-width-authoritative-source | #1188 | inherits resync |
| geom/dedupe-primitives-a374c69e | #1183 | inherits resync |
| investigate/cst3015-reinforced-isolation | #1146 | inherits resync |
| investigate/t1-isolator-hv-lv-creepage | #1140 | inherits resync |

24 of these 34 PRs have `fix/board-schematic-resync` as their declared
base; the rest are stacked transitively.

### Group B — `1b15b274` (11 branches): the router trunk, PR #1178

Board changes: resync (96ebe489c) + stackup declaration (fb00ab4f9) +
6-layer decision (e4eaba1cd). PR #1178 (`fix/layer-architecture-ssot`) is
the trunk; #1195/#1196/#1197/#1198/#1200/#1204/#1205/#1206 stack on it.

| branch | PR | board change |
|---|---|---|
| fix/layer-architecture-ssot | **#1178 (trunk)** | resync + stackup + 6-layer |
| agent/router-pad-attachment-diagnosis-clean | #1196 | inherits |
| agent/router-primary-grid-and-partial-decline | #1197 | inherits |
| fix/drc-router-clearance-material-group | #1198 | inherits |
| fix/layer-aware-ampacity | #1204 | inherits |
| fix/ntc-no-ampacity-correction | #1205 | inherits |
| fix/pad-connectivity-audit-metric | #1200 | inherits |
| fix/router-nlayer-routing | #1195 | inherits |
| investigate/dormant-native-test-recovery | #1206 | inherits |
| measure/6layer-routing | #1193 | inherits |
| agent/layer-identity-type-v2 | (no PR) | inherits |

### Group C — `a70e34bb` (3 branches): resync + DRU scoping + copper strip

| branch | PR | board change |
|---|---|---|
| fix/clearance-1085-remediation-exec | #1157 | resync + 2dba7ab41 (DRU scoping + strip disconnected copper on 7 nets) |
| agent/full-replace-attempt | #1168 | same |
| agent/routing-diagnosis-40nets | #1172 | same |

### Group D — `5e5015f8` (1 branch): the authorized ZCD removal

| branch | PR | board change |
|---|---|---|
| fix/zcd-orphan-footprint-removal | **#1201** | deletes 7 orphaned ZCD footprints (D2 SOD-123, R6/R7/R8 1206+axial, R9, R10 0603, U3 H11L1 DIP-6); 225 lines, deletions only; nets/tracks/vias/zones byte-identical |

Verified against elec/src pre-deletion circuit by footprint/value/net
topology (commit 8792f9118 message): R6/R7 = r_zcd_top1/top2 divider, R8 =
r_zcd_bot, D2 = d_zcd_clamp zener, R9 = r_zcd_opto, U3 = zcd_opto H11L1,
R10 = r_zcd_pullup. Genuinely orphaned (5842767c2 deleted the circuit from
elec/src).

### Group E — one-off boards

| branch | PR | board change | relevance |
|---|---|---|---|
| fix/pcb-stackup-declaration | #1153 | resync + fb00ab4f9 (stackup only) | stacks on #1134; board subsumed by Group B |
| fix/c2-c3-courtyard-collision | #1176 | resync + courtyard fixes | leaf, post-resync |
| fix/courtyard-collision-remediation-exec | #1173 | resync + 7 courtyard fixes | leaf, post-resync |
| fix/via-annular-ring-floor | #1159 | resync + via annular 0.254mm/DRU hole clr 0.28mm | leaf, post-resync |
| fix/k3-relay-placement | (no PR) | embed-swap + revert (net zero) | dead |
| verify/731-mutation-corpus | (no PR) | merge-only, no net change | dead |
| phaseb/*, resolve/751-into-main, verify/731-gate-rerun (7) | (no PR) | `a333cf33`, merge-only, no net change | dead |
| docs/methodology-loop-discipline, feat/provable-safety-place-and-route (2) | (no PR) | `7b0dbcf4` PD3 creepage slots on old lineage | dead (superseded by #1155/#1194 on Group A) |
| codex/handoff-actionables | CLOSED #498 | old ZCD removal (`019389fb`) | dead |
| feat/board-sync-and-placement | (no PR) | `6ff45e56` old placement | dead |
| feat/rebenchmark-production-board | (no PR) | `d168bd95` ancient skeleton | dead |
| fix/footprint-drift-resync | (no PR) | `7794db92` old resync | dead |
| safety/mains-selv-isolation-barrier | (no PR) | `569056fb` keepout on old lineage | dead |
| feat/gen-schematics | (no PR) | board file DELETED at tip | dead |

## 5. Merge order (decision)

**1. PR #1201 — ZCD orphan-footprint removal** (THIS TASK)
- Smallest change (225 deleted lines, deletions only), explicitly authorized
  (handoff §1/§4), based directly on main (1 commit).
- DRC re-measurement required + being executed in this same PR (§7).

**2. PR #1134 — board resync (96ebe489c) → board becomes `b7d865b7`**
- Revision vs the task brief's "PR #1178's resync commit second": the data
  shows the resync also exists as the standalone hub PR #1134, which is the
  declared base of 24 PRs (Group A). Landing it second makes 34 branches'
  boards byte-identical to main's in one move; Group A's board conflicts
  vanish entirely.
- Empirically verified clean after #1201 (§6): the ZCD-first → resync
  merge produces a board **byte-identical to the resync's own output**
  (b7d865b7), because both sides delete the same 7 ZCD footprints (an
  agreeing deletion) and the resync's renumbering touches regions main did
  not modify.
- Requires its own DRC re-measurement (its board ≠ 6928b7c8) in the same PR.

**3. PR #1178 — 6-layer stackup trunk (→ `1b15b274`)**
- Once the resync is in main, #1178's stackup (fb00ab4f9) + 6-layer
  decision (e4eaba1cd) rebase onto b7d865b7; the now-redundant resync
  commit drops out of the branch. Unblocks Group B (11 branches incl.
  #1195-#1198, #1200, #1204-#1206).
- Blocked on ceiling approval for the de-saturation corrections — another
  agent's task (handoff §7A).

**4+. Remaining board-touching leaves**, ordered smallest-first:
- #1153 stackup declaration (subsumed by #1178 — likely close as dup)
- #1159 via-annular-ring-floor (2 rules)
- #1173/#1176 courtyard fixes (already verified 8/8)
- #1157 DRU scoping + copper strip (Group C)
- Each needs its own re-measurement; all become trivial once they rebase
  onto the new main.

**Explicitly NOT merged in parallel**: any two board-touching PRs at the
same time (handoff §6: hand-resolving board conflicts has destroyed content
twice). The single board-write privilege is the freeze discipline.

**Reverse order is dangerous**: landing the resync (#1134/#1178) BEFORE the
ZCD removal would renumber D2/R6-R10/U3 onto different parts; #1201's
deletion hunks would then target the wrong footprints (handoff §6's
designator-collision class) — this is exactly the reasoning for landing the
smallest, refdes-stable deletion first.

## 6. Empirical merge simulation (#1201 then resync)

Performed in a scratch branch off origin/main:

```
git cherry-pick 8792f9118          # ZCD removal → board 5e5015f8
git merge 96ebe489c                # resync
```

Result: 3 conflict hunks in pcb/temper.kicad_pcb, all of the form
"HEAD deleted X / resync also deleted X (or renumbered X)". Resolved by
taking the resync side (the renumbered footprints R6-R9/R65 exist on the
resync board elsewhere). **Merged board sha256 = b7d865b7... = the resync
commit's own board, byte-identical.** No content invented; the merge result
is exactly what PR #1134's branch already contains and has been reviewed as.

The only other auto-merged file (packages/temper-placer/tests/scripts/
test_r2_serialize_board.py) merged cleanly.

## 7. DRC ceiling re-measurement for #1201 (DONE — landed in the same PR)

- Board change: `6928b7c8` → `5e5015f8` (7 footprints removed; nets,
  tracks, vias, zones unchanged).
- kicad-cli 10.0.5 available; `pcb/temper.kicad_dru` regenerated from
  `scripts/generate_kicad_dru.py` (SSOT) — sha256 a9bce81f...
  (the prior record's measured DRU, bad860a0d..., predates rule changes
  #1110/#1113/#1129, so main's gate is currently red even on the unchanged
  board: 1393 errors / 490 warnings vs recorded ceiling 1298/489 — a
  PRE-EXISTING condition, not caused by #1201).
- **260 samples in two independent 130-sample rounds** (matching the file's
  own documented 260-sample convention) + a 20-sample control on main's
  unchanged board for attribution.
- Round 1 creepage {188: 3, 189: 30, 190: 97}; round 2 {189: 32, 190: 98} —
  combined {188: 3, 189: 62, 190: 195}: true spread 2 (round 2 alone would
  have understated it as 1 — the two-round convention caught the tail
  again, same as the 2026-08-12 record).
- Results: error_ceiling 1298 → 1363 (the only raise is clearance 402→499,
  kicad-cli's report cap, caused by pre-existing main-side rule PRs
  #1110/#1113/#1129 and proven by the main-board control which measures 499
  too); creepage 202→192, courtyards_overlap 11→8, hole_clearance 105→99,
  shorting_items 199→193, solder_mask_bridge 154→147, silk_over_copper
  172→54, warning_ceiling 489→371 (all falls from the removal).
- Provenance: measured-live, measured_at_commit 7f414b568, dirty false,
  sample_count 260, kicad-cli 10.0.5, input sha256 5e5015f8...
- `Ceiling-Approval:` trailer on the ceiling-update commit (2bb63692a),
  `_march` entry `2026-08-15-zcd-orphan-footprint-removal`, and
  `temper_constraints.references.yaml` board hash re-pinned (0 component
  moves, no alias references any removed sheetpath).
- All three gates verified locally and PASS: `ci_check_drc.py --backend
  kicad-cli` (1360/1363 errors, 371/371 warnings, noise-headroom guard
  PASS), `check_measurement_provenance.py` (2/2 fresh), 
  `check_drc_ceiling_approval.py` (raise detected, trailer + evidence
  contract satisfied).

### 7b. CI gate comparison — #1201 introduces ZERO new failures

PR #1201's CI (run 31896199152) fails the same pre-existing set as
code-only PRs #1199/#1210 (Required Python Tests, Fast Gates, Core Tests,
Cross-Source Consistency Gates, Board gates, regression — all red on main
since the #1110/#1113/#1129 rule changes and the 2 drifted oracles).
Per-gate comparison, main board vs ZCD board (same netlist):

| gate | main | #1201 | verdict |
|---|---|---|---|
| check_copper_net_consistency | 347 violations | 329 | improved (pre-existing failure) |
| check_footprint_drift | 13 | 6 | improved (pre-existing failure) |
| check_netlist_board_reconciliation | 125 | 113 | improved (pre-existing failure; resync's job) |
| BOM<->source reconciliation | 8 | 2 | improved (pre-existing failure) |
| Measurement-provenance gate | FAIL (stale) | **PASS** | fixed by this PR |
| DRC ceiling approval gate | FAIL (exit 2) | **PASS** | fixed by this PR |
| Run electronics validation tests | FAIL | **PASS** | fixed by this PR (stale PIN_ZCD_INPUT assertion) |
| DRC ratchet (ci_check_drc) | FAIL (1393>1298) | **PASS** (1360≤1363) | fixed by this PR |

**Known residue (deliberately not touched)**: the board still carries
orphaned copper on the deleted `zcd` net — 145 track segments (of 2290),
plus vias/zones, on net ordinal 162 which no longer exists in the compiled
netlist (5842767c2 deleted the circuit). The authorization for this PR was
footprints-only ("Removed exactly the seven footprints and nothing else:
net declarations 162/162, track segments 2290/2290, vias 48/48, zones
96/96 byte-identical"). Stripping the orphaned copper is the resync
PR's (#1134/#1178) job — it must NOT be mixed into this edit.

## 8. Status

- [x] Branch matrix (75 branches, 5 board families)
- [x] Merge order decision + justification
- [x] Empirical merge simulation (#1201 → resync = clean, byte-identical)
- [x] #1201 rebase verified clean (7f414b568, board 5e5015f8)
- [x] DRC re-measurement (260 samples, two rounds + 20-sample main control)
- [x] drc_ceiling.json update + _march entry + Ceiling-Approval trailer
- [x] references.yaml board hash re-pin (0 component moves)
- [x] Pushed to fix/zcd-orphan-footprint-removal (2bb63692a), PR #1201
      updated (head MERGEABLE; CI re-running)
- [ ] PR #1201 merged by owner after CI green
- [ ] Second landing: #1134 (resync, the hub — 34 branches unblocked)
- [ ] Third: #1178 (6-layer stackup trunk, after its ceiling approval)
- [ ] Fourth+: leaf board changes (#1159, #1173/#1176, #1157, ...)
- [ ] This document committed to chore/board-freeze-merge-sequence
