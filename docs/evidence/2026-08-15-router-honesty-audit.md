---
module: temper-placer
tags: [router, audit, honesty, connectivity, pad-connectivity-audit, kicad-drc, via-semantics, fake-completion]
problem_type: verification-audit
---

# 2026-08-15: Router honesty audit — is "routed" actually connected?

**Question:** of the 97/107 nets the router claims to route and the 60/139 it
claims are pad-connected, how many are ACTUALLY connected by continuous copper?

**Verdict in one line:** the router's own PRIMARY metric (60/139 pad-connected)
is **honest and verified** — but it **under-reports** by 2 nets because the
router emits every via as a THROUGH via (no `blind`/`micro` type token), and
the audit models them as layer-restricted blind vias. The "97/107 routed
successfully" line is A*-found-a-path, not pad connectivity: only **35 of the
97** claimed-routed multi-pad nets are actually pad-connected. The audit's 60
"connected" nets all pass independent verification.

## 1. Object under audit

- Routed board: `/tmp/opencode/final-route-6layer-output.kicad_pcb`
  (sha256 `dce71bbf319ff864ece1e6280695735f7116f7e593389b364821d922b486b7e1`)
- Producer: `scripts/route_board.py --net-batching --batch-size 10` on
  `origin/main` @ `84cc526fd` (6-layer stackup, Run B of
  `docs/evidence/2026-08-15-final-board-verification.md`)
- Router claims (from `final-route-6layer.log`):
  - `Result: 97/107 nets (90.7%)` — Stage 4 A* "routed successfully"
  - `Result (pad connectivity, PRIMARY metric): 60/139 nets fully
    pad-connected fake-completion=66 honest-gap=13`
- Audit under test: `router_v6/pad_connectivity_audit.py` on main (fixed in
  #1200), plus my own fully-independent verifier (own parser, own union-find,
  no temper_placer imports).

## 2. Methodology

1. **Independent verifier** (`/tmp/opencode/indep_connectivity.py`): parses
   the `.kicad_pcb` directly (paren-balanced blocks; own regexes), computes
   pad world positions from raw footprint/pad `(at ...)` transforms with
   KiCad's R(-θ) convention, runs union-find over (point-bucket, layer) nodes
   with segments, vias, THT/SMD pad layers. No temper_placer import at all.
2. **Calibration:** on the committed board, my verifier reproduces the
   evidence-doc numbers **exactly** (27 connected / 13 zone-dependent /
   99 broken) — the "fixed audit" figure. This validates parser + transform +
   union-find as a faithful independent implementation.
3. **Cross-check vs audit:** `audit_pcb_file` from the fixed module on main
   (run from my own worktree venv; the shared `.venv`'s editable install
   points at the main checkout's PRE-#1200 audit — 0 of 3 fix markers — a
   stale-toolchain trap, not a production finding).
4. **KiCad DRC cross-check:** `kicad-cli 10.0.5 pcb drc --format json
   --severity-error` on the routed output → **329 unconnected items**, matching
   the evidence doc's 329 exactly.
5. **Via-semantics empirical probe:** KiCad file-format spec says a via with
   no `blind`/`micro` type attribute is a THROUGH via. I verified with
   synthetic 6-layer boards (gerber export + DRC): an untyped `(layers
   "F.Cu" "In3.Cu")` via flashes copper on ALL six layers and DRC connects a
   B.Cu pad through it; a typed `blind` via flashes only its declared pair.
   All 74 vias in the routed output are untyped → all are THROUGH vias.

## 3. Headline results

| claim | value | verdict |
|---|---|---|
| Router "routed successfully" | 97/107 | **inflated as a connectivity claim** — only 35 of the 97 multi-pad nets are actually pad-connected; 62 are fake completions (copper exists, pads not joined). The log itself labels this line as A*-path-found and prints the pad-connectivity line as PRIMARY. |
| Router PRIMARY metric | 60/139 | **honest, and verified** — my independent verifier reproduces the same 60 connected nets exactly (blind-via model). |
| Audit "connected" count | 60/139 | **trustworthy for the 60 it reports** (all verified real), but **under-reports by 2** (cs_n, RTD_DRDY) under correct through-via semantics → true count 62/139. |
| KiCad DRC unconnected_items | 329 | agrees with through-via interpretation: **0 unconnected items for cs_n and RTD_DRDY** (audit said broken), 0 for tank-out's pads (DRC's 1 tank-out item is a dangling *track*, not a pad). |

### Per-layer honesty verdicts (the task's five questions)

1. **Router's own "routed" count: inflated.** "97/107 (90.7%)" is
   A*-found-a-path. Of the 97 claimed-routed multi-pad nets, only **35 are
   actually connected by continuous copper**; 62 are fake completions. The
   router is not *silently* dishonest — it prints the honest pad-connectivity
   line immediately after ("PRIMARY metric") and the evidence doc
   disambiguates — but the 90.7% headline reads as a completion rate when it
   is not one.
2. **Per-net "completed" status: yes, fake completions exist.** 62 of the 97
   "routed successfully" nets have copper that does not join all their pads
   (the b39b382d shape). #1177 fixed the discharge-relay NO-contact collapse
   (k_dis1-no/k_dis2-no now honestly visible as partial/unconnected), and its
   `find_pin_identity_pad_mismatches` guard is sound — but the fix is **not on
   main** and the general fake-completion population (64-66 nets) is
   structural, not a single-bug artifact.
3. **Pad-connectivity audit: trustworthy post-fix for what it reports, still
   slightly under-reporting.** All 60 "connected" nets verified real by
   independent union-find. BUT it models vias as connecting only their
   declared `(layers ...)` pair, while the router emits untyped vias that are
   **through vias** per KiCad's file format — so the audit misses 2 genuinely
   connected nets (cs_n, RTD_DRDY). This is a 4th metric defect (via-type
   blindness) in the same under-reporting direction as the 3 fixed in #1200.
4. **KiCad DRC unconnected_items: agrees with the through-via truth.** 329
   items across 78 nets; 0 for cs_n/RTD_DRDY (confirming they are connected).
   Reconciliation: 329 items ≠ 70 broken nets — a net with N unconnected pads
   contributes multiple missing-connection items; e.g. `gnd` (1/88) alone
   contributes 174 item-slots. The audit's 70 broken + 9 zone-dependent nets
   and DRC's 329 items measure the same underlying copper but at different
   granularity (net-level vs pad-pair-level).
5. **Zone-dependent nets: correctly classified as "cannot measure", with one
   caveat.** The audit reports 9 zone-dependent; my verifier 7. The 2-net
   delta (power_in.ntc-no, w1_2) is the K1 fab-only pads (K1.13/K1.14,
   `layers "F.Fab"` — no copper): the parser defaults them to "F.Cu" making
   them zone-coverable, my verifier treats them as non-copper. Both agree
   those nets are NOT connected. 0 of 231 zone blocks carry `filled_polygon`
   — zone-dependent means "cannot measure", exactly as labeled, and no zone
   net can be called connected until a real fill pass runs.

## 4. The via-type finding (new, and consequential)

**All 74 vias in the routed output carry no `blind`/`micro` type token.** The
KiCad file-format spec is explicit: *"If no type is defined, the via is a
through hole type."* The router's via writer
(`io/_write_tracks.py::_write_tracks` → kiutils `Via(position, size, drill,
layers, net, tstamp)`) never sets a type, so every `(layers "F.Cu"
"In3.Cu")`-looking via is actually a through via spanning ALL copper layers.

Verified three independent ways:
- **Gerber export** (`kicad-cli pcb export gerbers`): an untyped
  F.Cu-In3.Cu via flashes copper on F.Cu, In1.Cu, In2.Cu, In3.Cu, In4.Cu AND
  B.Cu. A typed `blind` via flashes only F.Cu + In3.Cu.
- **DRC connectivity**: an untyped via at an F.Cu-pad position connects that
  pad even when declared (B.Cu, In3.Cu); removing the via makes the pad
  unconnected (real-board test).
- **Synthetic board**: 6-layer test boards with untyped inner-layer vias
  report 0 unconnected items for pads on layers outside the declared pair;
  the same via typed `blind` behaves layer-restricted.

Consequences:
1. **Audit under-reports 2 nets** (cs_n, RTD_DRDY): pads on F.Cu, tracks on
   In3.Cu, vias at pad positions declared (B.Cu, In3.Cu) — the through-via
   barrel touches F.Cu, so the pads ARE connected. The audit's restricted-via
   model says broken 1/2. KiCad DRC says 0 unconnected items. True: connected.
2. **Physically, the fabricated board has through vias** where the layer pairs
   suggest blind vias were intended — every via barrel passes through the
   In1.Cu/In2.Cu power-plane layers. In this output In1/In2 carry no copper,
   so no short there today; but any future plane pour would be pierced.
3. **16 of 23 via-involved shorting_items are on layers OUTSIDE the via's
   declared pair** — e.g. an (F.Cu, In3.Cu)-declared via at (168.94, 95.25)
   shorting a `power_in.bypass_relay-coil2` track on In4.Cu (verified
   geometrically: via r=0.4mm + track half-width 0.254mm vs 0.61mm center
   distance → overlap). These shorts would not exist if the vias were the
   blind vias the layer pairs imply; they are real shorts on the
   as-emitted (through-via) board.

Whether the router *intends* through vias (its occupancy-grid model
`astar_grid.py:310` already blocks vias on ALL layers "assuming they span the
stackup") or intends blind vias (the layer pairs suggest this), the written
file is unambiguous: through. The audit must treat untyped vias as through.

## 5. Per-net comparison table (abridged; full table in `pernet-table.md`)

Router claim: `routed` = not in the log's FAIL/EXCL lists; audit =
`pad_connectivity_audit.py` on main; indep = my verifier with through-via
semantics; DRC = unconnected-item count (0 = DRC considers net connected).

| net | router | audit | indep (through) | DRC items | note |
|---|---|---|---|---|---|
| tank-out | routed | connected 2/2 | connected 2/2 | 1 | DRC's 1 item is a dangling track at (49.1,124.48), not a pad; both pads connected |
| cs_n | routed | **broken** 1/2 | **connected** 2/2 | 0 | through-via at pad positions touches F.Cu; audit under-reports |
| RTD_DRDY | routed | **broken** 1/2 | **connected** 2/2 | 0 | same mechanism |
| GATE_HS | routed | broken 1/2 | broken 1/2 | 0* | *capped/saturated category; pads genuinely not joined |
| power_in.ntc-no | routed | zone_dep 2/4 | broken 1/4 | 8 | K1.13 is fab-only (no copper); RT1.2/U1.2 need zone fill |
| w1_2 | routed | zone_dep 2/3 | broken 1/3 | 2 | K1.14 fab-only |
| sclk | routed | broken 1/2 | broken 1/2 | 0* | 121 segments, 0 pads touched |
| sdi/sdo | FAIL | broken 1/2 | broken 1/2 | 0* | failed honestly |
| +15V | routed | broken 1/10 | broken 1/10 | 20 | segments exist, pads not joined |
| +3V3 | FAIL | broken 1/50 | broken 1/50 | 98 | no copper emitted |
| ac_l | EXCL | connected 1/1 | connected 1/1 | 0 | single-pad net |

Full 139-row table: `/tmp/opencode/pernet-table.md` (also committed next to
this doc as `2026-08-15-router-honesty-pernet-table.md`).

## 6. Summary

- **Of the 97 claimed-routed nets: 35 are actually connected; 62 are fake
  completions.** The router's own PRIMARY line (60/139) is the honest number,
  and it is printed right next to the 90.7% headline.
- **Of the 60 audit-"connected" nets: all 60 pass independent verification.**
  The audit is not over-reporting; it is slightly under-reporting (true count
  62) because it models the router's through vias as blind.
- **KiCad DRC agrees with the through-via truth** (0 unconnected items for
  cs_n/RTD_DRDY; 329 items total reconciles with 70 broken + 9 zone-dependent
  nets at pad-pair granularity).
- **New defect found: the router emits every via without a type attribute →
  all vias are through vias**, regardless of the layer pairs written. This
  under-reports the audit by 2 nets and creates 16 shorts that would not exist
  under the layer-pair (blind) interpretation.

### Actions suggested (not taken here)

1. Router via writer: decide through-vs-blind intent; if blind is intended,
   emit the `blind` type token (changes shorts + audit); if through is
   intended, emit honest `(layers "F.Cu" "B.Cu")` pairs and treat the 16
   via-inner-layer shorts as router clearance defects.
2. `pad_connectivity_audit.py`: treat untyped vias as through (all copper
   layers), or parse the type token. This is a 4th metric defect in the
   same under-reporting direction as #1200's three.
3. Surface the "97/107" vs "60/139" gap in the route summary with explicit
   wording: "routed" = A* found a path; "pad-connected" = PRIMARY.

## 7. Artifacts

- Independent verifier: `/tmp/opencode/indep_connectivity.py`
- Through-via recomputation: `/tmp/opencode/through_via_connectivity.py`
- Per-net verdicts: `/tmp/opencode/audit-pernet.txt` (audit),
  `/tmp/opencode/indep-pernet.txt` (blind), 
  `...final-route-6layer-output.kicad_pcb.through-via-verdicts.txt` (through)
- Full comparison table: `/tmp/opencode/pernet-table.md`
- DRC JSON: `/tmp/opencode/honesty-drc.json` (kicad-cli 10.0.5, PD3 DRU)
- Routed board untouched; committed board untouched
  (sha256 verified before/after).
