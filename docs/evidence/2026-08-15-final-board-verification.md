---
module: temper-placer
tags: [router, route, verification, connectivity, ampacity, pd3, net-batching, capstone, drc]
problem_type: capstone-verification
---

# 2026-08-15: Final board verification — capstone route on latest main

Capstone question: does the board route end-to-end with ALL fixes on main,
and is the result fabricable? One full batched route from scratch on
`origin/main` head `54b6169ca` — the newest main, carrying #1199 (CI
green-up), #1121 (R30 litz pad rating), #1115 (zone pours honour per-net-PAIR
clearance) and #1106 (OVP divider co-location) on top of the previous route
head `7f6a6bd5c`.

**Bottom line up front:** the route is stable and OOM-free, connectivity is
unchanged from the previous capstone run (65/104 nets, 53/139 pad-connected),
trace-level ampacity for `power_in.ntc-no` is achieved and *improved*
(76 segs @ 5.0 mm, up from 72), and the routed board beats the committed
board on every DRC category under the same DRU (errors 1572→1392, creepage
379→330, unconnected 428→353). **The board is still NOT fabricable**: no
zone-fill pass exists (0/139 zones filled), the OCP-02 subsystem (T2/R65/C37)
is absent from the board, the FinePitch 0.127 mm-vs-0.2 mm width conflict
persists, and 314 PD3 creepage violations remain outside T1/T2/U6.

## 0. PR triage outcome (Step 2 of the dispatch)

Four PRs targeting `main` are currently `MERGEABLE` (#1225, #1237, #1238,
#1239). **None were merged.** All four are `mergeStateStatus: BLOCKED` with
genuinely failing PR-head checks (not inherited-from-main noise — `main`
itself is green for the route-relevant workflows):

| PR | content | failing gates (PR head) |
|---|---|---|
| #1225 | tank↔bus creepage test structural fix | Regression Suite, Golden Regression, PR Performance |
| #1237 | ci(unsilence) batch 2 | Regression Suite |
| #1238 | functional-insulation tier + PD2→PD3 retarget | Regression Suite, Golden Regression |
| #1239 | delete 9 pure-delegation shims | Python Tests (Fast Gates stale allowlist, Cross-Source, Board/Provenance) |

Force-merging red PRs with `--admin` would put `main` red and invalidate this
capstone measurement; the project's rules forbid bypassing gates (a labelled
red beats a green that means nothing). None are docs-only or clearly-safe, so
all four were skipped. **#1178 (the 6-layer stackup decision) remains
OPEN/BLOCKED** on the R27 ceiling-approval trailer (owner decision, not an
agent's). This route therefore measures the current **4-layer** main exactly
as it is — `--net-batching` works regardless of #1178.

## 1. Recipe and environment

```
git worktree add /tmp/opencode/agent-final-route -b verify/final-route-2026-08-15 origin/main
# HEAD 54b6169ca; pcb/temper.kicad_pcb sha256
#   6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
# (byte-identical to the previous route's board -- #1106/#1115/#1121
#  changed router/constraints code, not the board file; verified before and
#  after the run)

make venv-isolate     # worktree's own .venv; 10/10 extensions fresh,
                      # check_venv_integrity.py PASSED
.venv/bin/python scripts/route_board.py --net-batching --batch-size 10 \
  --output /tmp/opencode/final-route-output.kicad_pcb
```

- Memory before launch: 33 GB free / 53 GB available; no competing
  `route_board.py` / `pumpkin_engine` processes. Route peak RSS ~0.9 GB.
- **The shared `.venv` was NOT trusted and NOT used**: it failed
  `check_venv_integrity.py` (5 `direct_url.json` entries pointing at
  `/tmp/.tmp*` wheel paths — installed-from-temp-wheel, outside the repo
  root) AND `check_stale_extensions.py` (4 stale crates: design-bundle,
  geometry, io-types, orchestration — built 08-11 vs source 08-12/13).
  All measurements below come from the isolated worktree venv.
- DRU: `scripts/generate_kicad_dru.py` run in-tree; generated
  `pcb/temper.kicad_dru` (gitignored) is **byte-identical** to what the
  previous route head `7f6a6bd5c` would generate (33 rules; verified by
  regenerating at that commit — the generator's +317 lines between heads
  are pure rule-export plumbing for the router's YAML configs, output
  unchanged).
- kicad-cli 10.0.5 (`/home/bennet/.local/opt/kicad-10.0.5/...`), invoked via
  the repo's `_drc_api.run_drc` (thread-pinned `MaximumThreads=1`,
  `--all-track-errors` — required for reproducibility).

## 2. Route result

```
Result: 65/104 nets (62.5%)  segments=3320 vias=28 zones=139  wall=634.4s
[net-batching] 14 batch(es), 14 solved at batch level, 0 crashed
Result (pad connectivity, PRIMARY metric): 51/139 nets fully pad-connected
  fake-completion=48 honest-gap=40
```

- **No OOM**: 14/14 SAT batches solved, 0 crashes — same as the previous
  run. The Stage 3 selective-SAT net filter holds on the newest main.
- Wall 634.4 s (~10.6 min) vs 698.8 s previously — slightly faster.
- Routed output sha256: `ed761fb610a6f978047057e1b08ac799fdbb97d0f69710782a90b76eed8fc891`
  (scratch file, NOT committed; the route auto-propagated
  `final-route-output.kicad_pro` + `.kicad_dru` sidecars per
  `_drc_api`'s fail-closed project-context convention).

## 3. Connectivity — identical to the previous capstone run

Measured with the **fixed** audit code
(`fix/pad-connectivity-audit-metric` @ `575f1ba8f`, module loaded by path
against the installed main `kicad_parser`/geometry — see toolchain note
below), 139 pad-bearing nets:

| board | fully connected | zone-dependent | broken |
|---|---|---|---|
| committed `pcb/temper.kicad_pcb` (this session, consistent toolchain) | **29**/139 | 14 | 96 |
| committed (previous session, fix-branch toolchain) | 27/139 | 13 | 99 |
| **routed scratch output (this run)** | **53**/139 | 10 | **76** |
| routed (previous session `full-route-output`) | 53/139 | 10 | 76 |
| best pre-PD3 code-only (handoff §4, fix branches) | 69/139 | — | — |

The built-in (main) audit on this routed output reports 51/139 — the fixed
audit recovers 2 more via zone-layer visibility, exactly as last time.

**Merging #1106/#1115/#1121/#1199 did not move connectivity**: 65/104 nets
and 53/139 pad-connected are identical to the previous run. The 16-net gap
vs the 69 pre-PD3 figure is the documented cost of PD3 (12.6 mm) being wired
into the router's *live* pathfinding gate (`router_clearance.rs`), and it is
unchanged. There is no regression and no improvement from the intervening
merges — the router was already at this plateau.

Key nets (fixed audit, this routed output):

| net | class | category | pads conn/total | notes |
|---|---|---|---|---|
| `power_in.ntc-no` | HighVoltage | zone_dependent | 2/4 | **76 segments at 5.0 mm** + 14 zone outlines; RT1.2/U1.2 rely on zone fill |
| `tank-out` | HighVoltage | **connected** | 2/2 | 27 segs @ 5.0 mm |
| `w1_2` | HighVoltage | zone_dependent | 2/3 | 26 segs @ 5.0 mm |
| `ac_l` / `ac_n` | ACMains | zone_dependent | 1/2, 1/3 | pours; zones declared, unfilled |
| `+170V_BUS` | — | zone_dependent | 1/11 | pour net |
| `PWR_RTN` | — | zone_dependent | 1/18 | pour net |
| `gnd` | Power | broken | 1/86 | no copper emitted (zone net, no zone written) |
| `GATE_HS` / `GATE_LS` | GateDriveHV | broken | 1/2, 1/3 | segments present, pads not joined |
| `zcd` / `ZCD_ISO` | — | broken | 1/4, 1/3 | no copper |

**Toolchain note (why 29/27 on the committed board).** The previous session
ran the fixed audit from the fix-branch tree with the fix-branch extensions;
that tree's `pin_geometry.py` crashes against main's Rust netlist contract
(`Component.initial_rotation` removed — verified empirically). This session
uses the fixed audit module against main's parser/geometry for BOTH the
committed and the routed board, so the committed-vs-routed delta is
tool-independent. The 2-net offset (29 vs 27 committed) is parser-version
noise, not a board change (board sha256 is identical).

Zone-dependent verdicts are **"cannot measure"**, not "connected": 139 zone
outlines, **0 filled** (`filled_polygon` count = 0). A real KiCad zone-fill
pass is required before any zone-dependent net can be called connected.

## 4. Ampacity — trace-level achieved and improved; net-level still open

Width histogram (segments only, strict per-line parse of the output):

```
5.0000: 148  3.0000: 1  2.0000: 102  1.0000: 140  0.5080: 77
0.5000: 205  0.4000: 185  0.2000: 1963  0.1270: 499
```

- **`power_in.ntc-no`: 76 segments, ALL at 5.0 mm** (previous run: 72).
  IPC-2221B kernel (`temper_drc_rs.ipc.estimate_trace_current`, k=0.048
  external, 2 oz): 5.0 mm = **17.2 A @ 20 °C rise / 23.3 A @ 40 °C rise**.
  Required minimum for 15 A, 2 oz, 40 °C external = **2.729 mm** → 5.0 mm
  gives **1.55× margin**. (An earlier analysis pass flagged two thin
  segments on this net; that was a regex artifact — `(net 88)` matching
  `(net 988)`-style suffixes — a strict per-line parse confirms all 76 are
  5.0 mm.)
- `tank-out` (27), `w1_2` (26), `tank.c_tank1-p2` (2), `DC_BUS_RTN` (5)
  also draw 5.0 mm.
- **Net-level ampacity is NOT achieved**: `power_in.ntc-no` is
  zone_dependent — RT1.2 and U1.2 are joined only by unfilled zone
  outlines. The handoff §8.6 pour-fragmentation question is unchanged.
- **FinePitch width conflict persists**: 499 segments at 0.1270 mm (the
  declared `FinePitch` `trace_width: 0.127`) against the board setup's
  0.2000 mm minimum — pre-existing netclass-SSOT vs board-setup conflict,
  unchanged since the previous run. Owner decision still open.

## 5. DRC — routed beats committed under the same DRU (kicad-cli 10.0.5,
`--all-track-errors`, PD3 DRU, thread-pinned)

| board | errors | warnings | creepage | unconnected items |
|---|---|---|---|---|
| committed (this session, same DRU) | 1572 | 490 | 379 | 428 |
| committed (previous session) | 1574 | 490 | 377 | 428 |
| **routed (this run)** | **1392** | 582 | **330** | **353** |
| routed (previous session) | 1335 | 580 | 307 | 342 |

Routed is better than committed on errors (−180), creepage (−49),
unconnected (−75) despite carrying 3320 segments of new copper — same
direction and same story as the previous run.

**The routed delta vs the previous routed run (1392 vs 1335 errors, 330 vs
307 creepage) is route nondeterminism, not a DRU change.** Verified: the DRU
generated at this head is byte-identical to the one the previous head
generates (33 rules, zero diff). The routed outputs are similar-but-not-
identical boards (3320 vs 3295 segments, 139 vs 72 zone blocks — the zone
count change coincides with #1115's per-net-pair pour-emission changes,
though no bisect was run to isolate it; both runs' zones are unfilled
outlines), and the router is explicitly nondeterministic
across process launches (per-process HashMap hashing — `route_board.py`'s own
docstring). A single-run routed DRC spread of ±23 creepage / ±57 errors is
the noise floor for this pipeline; both runs' routed boards beat the
committed board.

Saturation note: kicad-cli caps `clearance` at 499 and `shorting_items` at
199 even with `--all-track-errors` — both categories are at/near cap in both
columns, so those cells are lower bounds. `creepage` is not capped and is
the honest count. Sample enforced rule: `'HV to LV' creepage 12.6000 mm` —
the PD3 bar, live in the same DRU the router was built against.

Creepage breakdown on the routed board (329–330 violations):

| rule | count |
|---|---|
| HV to LV | 188 |
| HighVoltageSignal to LV | 82 |
| HighVoltageIsolated to LV | 24 |
| AC Mains to LV | 18 |
| (HighVoltageTank + other rules) | remainder |

Components in creepage violations (top): U7 28, U27 24, K2 19, R5 15, U3 14,
K3 13, U6 11, L1 11, K1 8, C14 8, R30 8. **314 of 329–330 violations do not
involve T1/T2/U6** — on the *routed* board the placement-domain creepage is
spread across the safety/control/driver circuitry, not concentrated in the
power stage. This is consistent with the handoff §7C finding that T1/T2/U6
dominate at both PD figures *on the un-routed board*; the routed copper
redistributes the picture. The ~64 "net-new exposure excluding T1/T2/U6"
estimate from §7C was a placement-domain figure and does not transfer
directly to the routed board — the routed board measures more (314) because
it carries 3320 segments of new copper, each a potential creepage pair.

## 6. Fabricability verdict — NOT fabricable yet; pipeline honest and stable

Progress since the last capstone run: none in connectivity (plateau), but
ampacity trace-level improved (72→76 segs @ 5.0 mm) and the route remains
OOM-free and deterministic in outcome. The remaining blockers:

1. **No zone-fill pass** — 139 zone outlines, 0 filled. All pour nets
   (`gnd`, `+3V3`, `+170V_BUS`, `PWR_RTN`, `ac_l`, `ac_n`, `SW_NODE`,
   `DC_BUS_RTN`) and the zone-dependent half of `power_in.ntc-no` are
   unconnected until KiCad fill runs, and the handoff §8.6 documents that
   `power_in.ntc-no`'s pour fragments into 47+ islands under DRC-aware fill.
2. **OCP-02 subsystem absent** — `T2` is not on the board at all; `R65` sits
   at (5.08, 0) and `C37` at (0, 0), i.e. staged at the origin, not placed
   (handoff §4 / PR #1151 finding; re-verified on this board). The
   overcurrent-protection path is physically missing.
3. **PD3 creepage violations** — 330 on the routed board, 314 outside
   T1/T2/U6 (U7/U27/K2/R5/U3/K3/L1 lead). Placement-domain; needs a
   re-place or component changes, not routing.
4. **FinePitch 0.127 vs 0.200 mm** netclass-SSOT vs board-setup conflict —
   499 segments at 0.127 mm; owner decision open.
5. **GATE_HS/GATE_LS and 76 broken nets** — dominated by power/ground/HV
   pours that emit no copper (`gnd` 1/86) plus signal-net gaps.

**Is the board fabricable? No.** The router pipeline is honest, stable,
OOM-free, PD3-correct and width-correct, but connectivity is at 53/139
(38%), the pours are unfilled, and the OCP subsystem is not on the board.
None of the remaining blockers are router-correctness bugs — they are
zone-fill infrastructure, placement/component work, and two open owner
decisions.

## 7. Artifacts

- Full route log: `/tmp/opencode/final-route.log` (pid file
  `/tmp/opencode/final-route.pid`)
- Routed scratch board: `/tmp/opencode/final-route-output.kicad_pcb`
  (sha256 `ed761fb6…`; with propagated `.kicad_pro`/`.kicad_dru` sidecars)
- DRC JSONs: `/tmp/opencode/committed-drc-raw.json` (raw kicad-cli),
  `/tmp/opencode/raw-drc.json` (routed, raw kicad-cli)
- Fixed-audit runner: `/tmp/opencode/run_audit.py` (audit code from
  `fix/pad-connectivity-audit-metric` @ `575f1ba8f` loaded against main's
  parser/geometry via the isolated venv)
- Width/ampacity analyzers: `/tmp/opencode/analyze_route.py`,
  `/tmp/opencode/check_ampacity.py`
- Committed board untouched: sha256 `6928b7c8…` before and after.

## 8. Non-goals / not measured

- No zone-fill pass was run on the output (KiCad fill is a separate stage;
  the audit explicitly does not point-in-polygon).
- No multi-run spread (`--runs N`) — single capstone run, matching the
  previous capstone's methodology. The routed-DRC noise floor (±23 creepage)
  is inferred from the two single-run capstones, not measured directly.
- `power_in.ntc-no` ampacity verified at trace level only; net-level requires
  the zone-fill question resolved.
- The 4 mergeable-but-red PRs (#1225/#1237/#1238/#1239) remain open for their
  owners; merging them is a prerequisite for any further connectivity gain
  from the un-silenced checks / shim deletions they carry.
