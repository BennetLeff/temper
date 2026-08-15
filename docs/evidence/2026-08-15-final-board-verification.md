---
module: temper-placer
tags: [router, route, verification, connectivity, ampacity, pd3, net-batching, capstone, drc, 6-layer]
problem_type: capstone-verification
---

# 2026-08-15: Final board verification — capstone route (4-layer and 6-layer)

Capstone question: does the board route end-to-end with ALL fixes in place,
and is the result fabricable? This document records **two** full batched
routes:

- **Run A** — `origin/main` head `54b6169ca` (**4-layer** board, sha
  `6928b7c8…`): the state when this session began.
- **Run B** — `origin/main` head `84cc526fd` (**6-layer** board, sha
  `d2f795bc…`): **PR #1178 (the 6-layer stackup decision) merged mid-session**,
  so the capstone was re-run on the new main — the state "with ALL fixes in
  place" that the dispatch asked for.

**Bottom line:** the 6-layer stackup delivered the routing-capacity fix it
was designed for. Run B routes **97/107 nets (90.7%)** vs 65/104 (62.5%) on
4-layer; fully pad-connected rises **27→60** of 139 (committed→routed) vs
29→53 on 4-layer; unconnected items fall to 329 (best ever). The cost is
DRC: the routed 6-layer board carries **1877 errors / 510 creepage** — the
price of routing far more HV copper into proximity with LV. The board is
**still not fabricable**: no zone-fill pass exists (0/231 zones filled), the
OCP-02 subsystem (T2/R65/C37) is still absent, the FinePitch 0.127 mm
conflict persists (873 segments), and 485 PD3 creepage violations lie
outside T1/T2/U6.

## 0. PR triage outcome (Step 2 of the dispatch)

Four PRs targeting `main` were `MERGEABLE` when checked (#1225, #1237,
#1238, #1239), all `BLOCKED` with genuinely failing PR-head checks. **None
were force-merged** — the project rules forbid bypassing gates (a labelled
red beats a green that means nothing), and force-merging would have put
`main` red. Three of them (**#1237, #1238, #1200**) merged on their own
during this session; #1200 (the pad-connectivity audit fix) landed in time
for Run B, so Run B's audit is the fixed metric **built into main** (no
workaround needed).

| PR | content | status this session |
|---|---|---|
| #1178 | 6-layer stackup decision | **merged mid-session** → Run B |
| #1200 | pad_connectivity_audit 3 metric defects | merged mid-session → Run B |
| #1201 | ZCD removal resync | merged mid-session → Run B |
| #1237 | ci(unsilence) batch 2 | merged mid-session |
| #1238 | functional-insulation tier + PD2→PD3 retarget | merged mid-session |
| #1225 | tank↔bus creepage test structural fix | still open, red |
| #1239 | delete 9 pure-delegation shims | still open, red |

## 1. Recipe and environment

```
# Run A
git worktree add /tmp/opencode/agent-final-route -b verify/final-route-2026-08-15 origin/main  # 54b6169ca
make venv-isolate
.venv/bin/python scripts/route_board.py --net-batching --batch-size 10 --output /tmp/opencode/final-route-output.kicad_pcb

# Run B
git worktree add /tmp/opencode/agent-final-6layer -b verify/final-route-6layer origin/main       # 84cc526fd
make venv-isolate
.venv/bin/python scripts/route_board.py --net-batching --batch-size 10 --output /tmp/opencode/final-route-6layer-output.kicad_pcb
```

- Board sha256: Run A `6928b7c8950a732f…` (4-layer: F.Cu/In1.Cu/In2.Cu/B.Cu),
  Run B `d2f795bc1d3b0da9…` (6-layer: F.Cu/In1.Cu/In2.Cu/In3.Cu/In4.Cu/B.Cu).
  Both verified unchanged before/after; **no board file was modified by this
  session**.
- Both runs used an isolated worktree venv (`make venv-isolate`): 10/10
  extensions fresh, `check_venv_integrity.py` PASSED. **The shared `.venv`
  was not used** — it fails `check_venv_integrity.py` (5 direct_url entries
  to `/tmp/.tmp*` wheels) and `check_stale_extensions.py` (4 stale crates).
- DRU: `scripts/generate_kicad_dru.py` in-tree; **33 rules, PD3 (12.6 mm)**
  at both heads (byte-identical output between heads — verified by
  regenerating at `7f6a6bd5c`).
- kicad-cli 10.0.5 via the repo's `_drc_api.run_drc` (thread-pinned
  `MaximumThreads=1`, `--all-track-errors` — the reproducible convention).
- Memory: 33 GB free before Run A; 27 GB available before Run B (several
  other agents active). No competing `route_board.py`/`pumpkin_engine`
  processes at either launch. Peak RSS ~0.9 GB both runs.

## 2. Route results

```
Run A (4-layer): Result: 65/104 nets (62.5%)  segments=3320 vias=28 zones=139  wall=634.4s
                  [net-batching] 14 batch(es), 14 solved, 0 crashed
Run B (6-layer): Result: 97/107 nets (90.7%)  segments=6012 vias=74 zones=231  wall=747.3s
                  [net-batching] 14 batch(es), 14 solved, 0 crashed
```

- **No OOM in either run** — the Stage 3 selective-SAT net filter holds.
- Run B's route genuinely uses the new layers: segment layers F.Cu 2025,
  **In3.Cu 1366, In4.Cu 1465**, B.Cu 1156 (In1/In2 are power layers —
  no signal segments, as declared).
- Routed outputs (scratch, NOT committed):
  `/tmp/opencode/final-route-output.kicad_pcb` (sha
  `ed761fb6…`), `/tmp/opencode/final-route-6layer-output.kicad_pcb`
  (sha `dce71bbf…`). The route auto-propagates `.kicad_pro`/`.kicad_dru`
  sidecars per the `_drc_api` fail-closed project-context convention.

## 3. Connectivity — the 6-layer stackup is the fix that works

Fixed audit (`fix/pad-connectivity-audit-metric` @ `575f1ba8f` for Run A —
loaded by path against main's parser; **built-in on main** for Run B via
#1200). 139 pad-bearing nets:

| board | fully connected | zone-dependent | broken |
|---|---|---|---|
| committed 4-layer (`6928b7c8`) | 29 | 14 | 96 |
| routed Run A (4-layer) | 53 | 10 | 76 |
| committed 6-layer (`d2f795bc`) | 27 | 13 | 99 |
| **routed Run B (6-layer)** | **60** | 9 | **70** |

- **Run B: 27 → 60 fully pad-connected (2.2×)** — the largest single gain
  measured on this board. The 4-layer route's plateau (53) was the
  routing-capacity ceiling #1178 was created to break; it broke.
- Built-in (main, fixed) audit on the 6-layer output: 60/139 — identical
  to the route's own PRIMARY metric printout (no fake-completion gap beyond
  the reported 66/13 split).
- 101/162 nets carry copper in Run B (vs 71/162 in Run A).
- Unrouted nets fell from 39 (Run A) to **10** (Run B).

Key nets (Run B, built-in fixed audit):

| net | class | category | pads conn/total | notes |
|---|---|---|---|---|
| `power_in.ntc-no` | HighVoltage | zone_dependent | 2/4 | **62 segments, all 5.0 mm** + 23 zone outlines; RT1.2/U1.2 rely on zone fill |
| `tank-out` | HighVoltage | **connected** | 2/2 | 26 segs @ 5.0 mm |
| `tank.c_tank1-p2` | HighVoltageTank | zone_dependent | **2/4** | **47 segs @ 5.0 mm** (was 2 segs/1 pad in Run A — major gain) |
| `w1_2` | HighVoltage | zone_dependent | 2/3 | 26 segs @ 5.0 mm |
| `ac_l` | ACMains | connected | 1/1 | single-pad net |
| `ac_n` | ACMains | zone_dependent | 1/3 | pour |
| `+170V_BUS` | — | zone_dependent | 1/11 | pour net |
| `PWR_RTN` | — | zone_dependent | 1/15 | pour net |
| `gnd` | Power | broken | 1/88 | no copper emitted |
| `GATE_HS` / `GATE_LS` | GateDriveHV | broken | 1/2, 1/3 | segments present, pads not joined |

Zone-dependent verdicts are **"cannot measure"**, not "connected": 231 zone
outlines, **0 filled** in Run B. A real KiCad zone-fill pass is still
required before any zone-dependent net (including the zone half of
`power_in.ntc-no`) can be called connected.

**Toolchain note.** Run A's committed-board reading (29/14/96) differs by 2
nets from the previous session's (27/13/99) because Run A used main's newer
parser with the fixed audit module; the board sha was identical. Run B is
entirely in-tree (fixed audit built in), so its numbers carry no toolchain
caveat.

## 4. Ampacity — trace-level achieved; net-level still zone-dependent

Run B width histogram (segments only, strict per-line):

```
5.0000: 334  3.0000: 1  2.0000: 106  1.0000: 210  0.5080: 141
0.5000: 138  0.4000: 280  0.2000: 3929  0.1270: 873
```

- **`power_in.ntc-no`: 62 segments, ALL at 5.0 mm** (strict per-line; an
  earlier regex pass flagged two thin segments — an `(net 88)` matching
  `(net 988)` artifact, disproved). IPC-2221B kernel
  (`temper_drc_rs.ipc.estimate_trace_current`, k=0.048 external, 2 oz):
  5.0 mm = **17.2 A @ 20 °C / 23.3 A @ 40 °C**; required for 15 A, 2 oz,
  40 °C external = **2.729 mm** → **1.55× margin**.
- `tank-out` (26), `w1_2` (26), **`tank.c_tank1-p2` (47 — up from 2)**,
  `DC_BUS_RTN` (4) also draw 5.0 mm.
- **Net-level ampacity is NOT achieved**: `power_in.ntc-no` is
  zone_dependent — RT1.2 and U1.2 are joined only by unfilled zone
  outlines. The handoff §8.6 pour-fragmentation question is unchanged.
- **FinePitch conflict worsened**: 873 segments at 0.1270 mm (Run A: 499)
  — the 6-layer route routed more FinePitch nets at the declared 0.127 mm
  against the board setup's 0.2000 mm minimum. Same pre-existing
  netclass-SSOT vs board-setup conflict; owner decision open.

## 5. DRC — routed beats committed on unconnected; creepage is the 6-layer cost

kicad-cli 10.0.5, `--all-track-errors`, PD3 DRU (33 rules, identical at
both heads), thread-pinned:

| board | errors | warnings | creepage | unconnected items |
|---|---|---|---|---|
| committed 4-layer (`6928b7c8`) | 1572 | 490 | 379 | 428 |
| routed Run A (4-layer) | 1392 | 582 | 330 | 353 |
| committed 6-layer (`d2f795bc`) | 1474 | 380 | 323 | 426 |
| **routed Run B (6-layer)** | **1877** | 485 | **510** | **329** |

- **Unconnected items: 329 — the lowest measured on any board.** The 6-layer
  route connects more pads than any previous state.
- **Creepage 510 — the highest measured.** Breakdown: HV to LV 307,
  HighVoltageSignal to LV 100, HighVoltageTank to LV 50, HighVoltageIsolated
  to LV 25, AC Mains to LV 20, HighVoltageTank functional 8. Top components:
  U24 32, RT1 23, K2 22, U6 21, U27 21, L1 17, K3 16, U14 15. **485 of 510
  violations do not involve T1/T2/U6.** This is the direct cost of the
  routing-capacity win: far more HV copper routed into proximity with LV
  copper. These are placement-domain fixes (re-place, shields, slots), not
  router-correctness bugs — but they are the new dominant DRC category.
- The 6-layer committed board is a better baseline than the 4-layer
  committed (1474 vs 1572 errors; 323 vs 379 creepage) — #1178's stackup
  declaration and #1201's ZCD removal improved it.
- Saturation note: `clearance` (499), `solder_mask_bridge` (199),
  `hole_clearance` (199), `shorting_items` (199) and `track_width` (199)
  are at/near kicad-cli's caps in the 6-layer routed column — those cells
  are lower bounds. `creepage` is not capped and is the honest count.
- Run A vs the previous session's routed run (1392 vs 1335 errors, 330 vs
  307 creepage) is route nondeterminism, not a DRU change (DRU verified
  byte-identical between heads); both beat their committed board.

## 6. Fabricability verdict — NOT fabricable yet; the biggest single win measured

**The capstone question "does the board route end-to-end" now has a clear
yes at the net level** — 97/107 nets (90.7%), the 6-layer stackup working
as designed, no OOM, PD3-correct widths. But fabrication remains blocked by:

1. **No zone-fill pass** — 231 zone outlines, 0 filled. All pour nets
   (`gnd`, `+3V3`, `+170V_BUS`, `PWR_RTN`, `ac_l`, `ac_n`, `SW_NODE`,
   `DC_BUS_RTN`) and the zone-dependent half of `power_in.ntc-no` are
   unconnected until KiCad fill runs; the handoff §8.6 documents
   `power_in.ntc-no`'s pour fragmenting into 47+ islands under DRC-aware
   fill.
2. **OCP-02 subsystem absent** — `T2` is not on the board; `R65` sits at
   (5.08, 0) and `C37` at (0, 0) (staged at origin, not placed). The
   overcurrent-protection path is physically missing. Re-verified on the
   6-layer board.
3. **PD3 creepage 510 on the routed board** (485 outside T1/T2/U6) — the
   new dominant blocker, a direct consequence of the routing win. Needs
   placement-domain work (re-place / shields / slots), not routing.
4. **FinePitch 0.127 vs 0.200 mm** conflict — 873 segments; owner decision
   open.
5. **70 broken nets** — dominated by power/ground/HV pours that emit no
   copper (`gnd` 1/88) plus signal-net gaps (GATE_HS/GATE_LS, sclk/sdi/sdo,
   vbias, vcc).

**Is the board fabricable? No.** But this session's measurement is the
strongest evidence yet that the pipeline is honest and converging: the
6-layer route is the first to break 90% net completion, and every remaining
blocker is a known, named, non-router issue.

## 7. Artifacts

- Route logs: `/tmp/opencode/final-route.log` (Run A),
  `/tmp/opencode/final-route-6layer.log` (Run B)
- Routed scratch boards: `/tmp/opencode/final-route-output.kicad_pcb`
  (Run A), `/tmp/opencode/final-route-6layer-output.kicad_pcb` (Run B),
  each with propagated `.kicad_pro`/`.kicad_dru` sidecars
- DRC JSONs: `/tmp/opencode/committed-drc-raw.json` (4L committed),
  `/tmp/opencode/raw-drc.json` (Run A routed)
- Audit/analysis runners: `/tmp/opencode/run_audit.py`,
  `/tmp/opencode/run_audit_builtin.py`, `/tmp/opencode/analyze_route.py`,
  `/tmp/opencode/check_ampacity.py`, `/tmp/opencode/run_drc_measure.py`
- Committed boards untouched: `6928b7c8…` (Run A), `d2f795bc…` (Run B).

## 8. Non-goals / not measured

- No zone-fill pass was run on either output (KiCad fill is a separate
  stage; the audit explicitly does not point-in-polygon).
- No multi-run spread (`--runs N`) — one run per board, matching the
  previous capstone methodology; routed-DRC noise (±23 creepage on 4-layer)
  inferred from the two single-run capstones, not measured directly.
- `power_in.ntc-no` ampacity verified at trace level only; net-level
  requires the zone-fill question resolved.
- The still-open red PRs (#1225/#1239) remain for their owners; #1237/#1238
  merged during the session and are included in Run B's code.
