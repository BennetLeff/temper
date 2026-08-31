<!-- provenance: commit=0f307d928625e8627911a29a7ba3e19a0eb329ac dirty=UNKNOWN -->
---
module: temper-placer
tags: [router, route, verification, connectivity, ampacity, pd3, net-batching]
problem_type: capstone-verification
---

# 2026-08-15: Full-board route verification — all fixes on main, end-to-end

Capstone verification run: does the board route now that the Stage 3 OOM is
fixed, trace widths are corrected, and PD3 is enforced? One full batched
route from scratch on `origin/main` head `7f6a6bd5c` (#1222), which carries
every relevant fix:

- **#1222** `7f6a6bd5c` — Stage 3 selective-SAT net filter wired for real +
  Stage 4.4 width pass-through
- **#1220 / #1229** — PD3 creepage enforcement (12.6 mm reinforced /
  10.0 mm tank), Gate 4 blocking
- **#1223** — IPC-2221B width correction (k=0.048/0.024, copper-oz,
  material-group)
- **#1221** — parser retains single-pad nets (139-net registry)

## 1. Recipe and environment

```
git worktree add /tmp/opencode/agent-full-route -b verify/full-board-route-2026-08-15 origin/main
# HEAD 7f6a6bd5c, pcb/temper.kicad_pcb sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
# (byte-identical to the PD3-raise board in drc_ceiling.json's _march)

.venv/bin/python scripts/route_board.py --net-batching --batch-size 10 \
  --output /tmp/opencode/full-route-output.kicad_pcb
```

- 10/10 pyo3 extensions fresh in an isolated worktree venv
  (`make venv-isolate`, incremental via shared `CARGO_TARGET_DIR`).
- Memory before launch: 35 GB free / 52 GB available; no competing
  `route_board.py` / `pumpkin_engine` / `cargo` processes.
- Route **completed** (did not OOM): `65/104 nets (62.5%)`,
  segments=3295 vias=28 zones=72, wall=698.8 s (~11.6 min).
- Net-batching summary: **14 batches, 14 solved at batch level, 0 crashed,
  0 subprocess timeouts.**
- Output is a scratch file (`/tmp/opencode/full-route-output.kicad_pcb`);
  the committed board was never written. Board sha256 verified unchanged
  before and after (`6928b7c8…`).

## 2. Connectivity — the primary metric

Fixed audit (`origin/fix/pad-connectivity-audit-metric` @ `575f1ba8f` —
NOT on main; run from a separate worktree against the scratch output):

| board | fully connected | zone-dependent | broken |
|---|---|---|---|
| committed `pcb/temper.kicad_pcb` (measured this session) | 27/139 | 13 | 99 |
| routed scratch output (this run) | **53/139** | 10 | 76 |
| best pre-PD3 code-only (handoff §4, fix branches) | 69/139 | — | — |

The built-in (main) audit on the same routed output reported 51/139 —
the fixed audit recovers 2 more via zone-layer visibility; both agree the
board is in the low-50s, up from 27 on the committed board.

**Why 53 now vs 69 pre-PD3:** the 69 was measured on fix branches whose
router gate ran at PD2/8.0 mm creepage. This run has PD3 wired into the
router's *live* pathfinding gate (`router_clearance.rs`:
`HighVoltage => 12.6 mm` reinforced, `Mains240V => 8.0 mm`, from
`VoltageClass` → Table 17 lookups). The ~16-net gap is the documented
cost of the stricter as-built bar (handoff §7C: 8.0 mm vs 12.6 mm
changes 167–168 → 320–321 DRU violations; net-new exposure ~64 excluding
T1/T2/U6). The route now enforces what the DRU measures — the two no
longer disagree by a pollution degree.

### High-value nets (fixed audit)

| net | class | category | pads conn/total | notes |
|---|---|---|---|---|
| `power_in.ntc-no` | HighVoltage | zone_dependent | 2/4 | **72 segments at 5.0 mm** (all B.Cu) + 4 zone outlines; 2 THT pads (RT1.2, U1.2) rely on zone fill |
| `tank-out` | HighVoltage | **connected** | 2/2 | 25 segs at 5.0 mm |
| `w1_2` | HighVoltage | zone_dependent | 2/3 | 25 segs at 5.0 mm |
| `ac_l` / `ac_n` | ACMains | zone_dependent | 1/2, 1/3 | pours (`_should_route` excludes; zones declared, unfilled in output) |
| `+170V_BUS` | — | zone_dependent | 1/11 | pour net |
| `PWR_RTN` | — | zone_dependent | 1/18 | pour net |
| `gnd` | Power | broken | 1/86 | no copper emitted (zone net, no zone written) |
| `GATE_HS/GATE_LS` | GateDriveHV | broken | 1/2, 1/3 | 2.0 mm segments present but pads not joined |
| `zcd` / `ZCD_ISO` | — | broken | 1/4, 1/3 | no copper |

Zone-dependent verdicts are **"cannot measure"**, not "connected": the
audit sees zone outlines but not fill geometry. In this scratch output the
72 zones are outlines (hatch, no `filled_polygon`) — a real KiCad zone-fill
pass is required before any zone-dependent net can be called connected, and
the handoff §8.6 documents that `power_in.ntc-no`'s pour fragments into
47+ islands under DRC-aware fill.

## 3. Ampacity — the width pass-through works

Widths in the routed output (segments only):

```
5.0000: 124  2.0000: 102  1.0000: 140  0.5080: 77  0.5000: 205
0.4000: 185  0.2000: 1963  0.1270: 499
```

- **`power_in.ntc-no`: 72 segments at 5.0 mm** — previously the drawn
  copper was 0.508 mm (pre-#1222 keyword-cascade bug). IPC-2221B
  (k=0.048 external, 2 oz): 5.0 mm = **17.2 A @ 20 °C rise / 23.3 A @
  40 °C rise** vs the pre-fix 0.508 mm = 3.27 A. Required minimum width
  for 15 A, 2 oz, 40 °C external = **2.73 mm** → 5.0 mm gives 1.8× margin.
  The netclass table's declared width is now the drawn width.
- `tank-out`, `w1_2`, `tank.c_tank1-p2`, `DC_BUS_RTN` also draw 5.0 mm.
- Gate-drive nets draw the declared 2.0 mm (`GateDriveHV`/`GateDriveSELV`).

**Caveat — width is achieved at the trace level, not yet the net level:**
ampacity requires continuous copper between a net's own pads, and
`power_in.ntc-no`'s two main THT pads (RT1.2, U1.2) are not joined by the
drawn segments — they sit on zones that are outline-only in this output.
The trace-level ampacity defect (0.508 mm) is fixed; the net-level
zone-fill question from handoff §8.6 remains open.

### FinePitch width conflict (pre-existing, now visible)

6 nets (`RTD_SDO` 170, `sclk` 183, `bias` 79, `RTD_CS_N` 30,
`RTD_HW_FAULT` 26, `RTD_SDI` 11 segments) draw at 0.1270 mm — the declared
`FinePitch` `trace_width: 0.127` in `netclass_rules.yaml`. The board's
setup min track width is 0.2000 mm, so these are all `track_width` DRC
errors. This is a **netclass-SSOT vs board-setup conflict that predates
this run** — the router now faithfully draws the declared width, which
exposes the conflict instead of hiding it. Owner decision needed: raise
`FinePitch` width to 0.2 mm or lower the board setup min.

## 4. DRC (kicad-cli 10.0.5, `--all-track-errors`, PD3 DRU generated in-tree)

| board | errors | warnings | creepage viols | unconnected items |
|---|---|---|---|---|
| committed (PD3 DRU) | 1574 | 490 | 377 | 428 |
| **routed (PD3 DRU)** | **1335** | 580 | **307** | **342** |

Routed board is *better* than the committed board on errors (−239),
creepage (−70), and unconnected (−86) despite carrying 3295 segments of
new copper — the new copper mostly respects the enforced rules, and the
DRU's own categories are now the ones the router was built against.

Saturation note: kicad-cli caps `track_width` and `shorting_items` at 199
violation records even with `--all-track-errors` (the repo's
`_drc_api.run_drc` convention); the totals above are therefore **lower
bounds** for those two categories. `creepage` is not capped and is the
honest count (307 routed / 377 committed). Sample creepage rule enforced:
`'HV to LV' creepage 12.6000 mm` — the PD3 bar, live.

## 5. Fabricability verdict

**Not fabricable yet, but the pipeline is now honest and progressing.**
- No OOM: the Stage 3 blowup is fixed (14/14 batches solved, 0 crashes).
- Correct widths: the SSOT width is the drawn width (5.0 mm HV nets).
- PD3 enforced end-to-end: router gate = DRU = DRC.
- 53/139 nets fully pad-connected (+10 zone-dependent awaiting fill) vs
  27/139 on the committed board; 76 nets still broken, dominated by
  power/ground/HV pours that emit no copper in this scratch route
  (`gnd` 86 pads, `+3V3` 50, `PWR_RTN` 18, `+170V_BUS` 11) and
  signal-net gaps.

The remaining work is not the router's OOM/width/PD3 correctness — it is
(i) zone-fill pass for the pour nets and the `power_in.ntc-no` islands,
(ii) the FinePitch 0.127-vs-0.2 width decision, and (iii) the ~64
net-new PD3 creepage violations excluding T1/T2/U6 (handoff §7C), which
are placement-domain, not routing-domain.

## 6. Artifacts

- Full route log: `/tmp/opencode/full-route.log`
- Routed scratch board: `/tmp/opencode/full-route-output.kicad_pcb`
  (sha256 recorded at measurement time; NOT committed — scratch output)
- DRC JSONs: `/tmp/opencode/routed-drc-pd3.json`,
  `/tmp/opencode/committed-drc-pd3.json`
- Committed board untouched: sha256 `6928b7c8…` before and after.

## 7. Non-goals / not measured

- No zone-fill pass was run on the output (KiCad fill is a separate
  stage; the audit explicitly does not point-in-polygon).
- No multi-run spread (`--runs N`) — single capstone run.
- `power_in.ntc-no` ampacity verified at trace level only; net-level
  requires the zone-fill question resolved.
