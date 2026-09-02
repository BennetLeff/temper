<!-- provenance: commit=061981dd58ddcc7c06ae03d5a6ef3d88c46d7fc4 dirty=UNKNOWN (measurement-base commit; the Conditions section records a fresh origin/main worktree at this commit, but measurement-time dirty state was not independently recorded) -->

# Any-angle router configuration (Theta*/Lazy-Theta*): DRC + creepage review

**Verdict: REJECT.** The any-angle configuration must not be adopted on
`pcb/temper.kicad_pcb`. It produces **8 direct HV<->SELV metallic contacts**
(0.0000 mm copper separation), **+889 new DRC violations**, and **+126
creepage violations**, including mains-domain nets touching SELV logic nets.
The connectivity gain it is credited with is partly *caused by* that
copper collision.

Reviewer: automated review of PR #1381 (`fix/observer-independent-router`,
unmerged). PR #1381 itself **did not** flip the flags; it only documented the
divergence. This document reviews whether the flip is safe. Nothing here
changes the board, any threshold, or any gate.

## 1. Conditions (stated, not inherited)

- Worktree cut fresh from `origin/main` @ `061981dd5`.
- `pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
  verified identical in working tree, `HEAD`, and `origin/main`. **Never modified**
  (re-verified after all runs).
- `scripts/check_stale_extensions.py`: **PASSED 10/10 fresh** immediately before
  each measurement round. Extensions built with `env -u CONDA_PREFIX make extensions`
  into this worktree's own `.venv` (`make worktree VENV=1`) — the documented
  `CONDA_PREFIX` maturin failure did fire on the first attempt and was corrected,
  not worked around.
- **`route_board.py` flags: none.** `scripts/route_board.py` exposes no any-angle
  flag, so both arms were driven through the *production* `route_pcb()` entry point
  by `route_board.route_once(pcb, rules)` with all defaults
  (`enable_geographic_pruning=False`, `enable_net_batching=False`,
  `max_sat_nets=None`, `enable_nlayer_astar_spike=False`, existing copper stripped),
  with only `RouterV6Pipeline.__init__`'s `enable_theta_star` /
  `enable_lazy_theta_star` forced per arm. `enable_smoothing` deliberately left
  alone (it is inert). `max_iter` stays 500_000 in both arms.
- **cProfile was NOT attached** to any measurement run.
- Machine: 24 cores, load average 3.8–7.4 during runs (32 concurrent users on the
  host). Wall times are therefore indicative only; every reported *result* metric
  is bitwise deterministic (below) and load-independent.
- kicad-cli 10.0.5. DRC boards staged with the full sidecar set
  (`temper.kicad_pro`, `fp-lib-table`, `libs/`, regenerated `temper.kicad_dru`).

### Instrument sanity checks (AGENTS.md "Measurement Instruments That Lie")

- `pcb/temper.kicad_dru` was **absent** (gitignored) and was regenerated per run via
  `generate_kicad_dru.generate_dru()` — the string was written into the scratch dir,
  `main()` was **not** run (it rewrites 4 git-tracked YAMLs). Creepage reads
  non-zero (106/232), not 0.
- `lib_footprint_issues` reads **13**, not 168 — the fp-lib-table sibling resolved.
- No count is exactly 199 or 499 (no saturation cap hit).
- Violation **sets** diffed, keyed on `(rule, sorted(items))` — `items` is the only
  lossless field; sorting normalizes kicad-cli's net-order swap. 3 runs per board,
  intersected.

## 2. Reproduction: the PR's table does not reproduce

Both arms are **bitwise deterministic** — two independent full routes per arm
produced byte-identical output (sha256 equal).

| | PR #1381 claimed | **measured here** |
|---|---|---|
| both `False` — pad-connected | 61/139 | **60/139** |
| both `False` — fake completions | 0 | **6** |
| both `False` — segments / vias | 4500 / 52 | **4553 / 169** |
| both `True` — pad-connected | 94/139 | **80/139** |
| both `True` — fake completions | 4 | **7** |
| both `True` — segments / vias | 3260 / 72 | **2608 / 172** |

The production-arm routed content hashes to `6d4e17337bcf2633…`, which **matches the
sha256 prefix PR #1381 itself cites** for that arm. So both parties routed the
identical board, yet the PR's reported metrics differ from what that board actually
measures. **The PR's table was not measured from the board it names.** Its headline
figures (+33 nets, 0 fake completions on production, 52 vias) are all overstated:
the real gain is **+20** pad-connected nets, production already has **6** fake
completions, and the real via count is **169 -> 172 (+1.8%)**, not 52 -> 72 (+38%).
The 52/72 figures appear to count only the router's own vias, excluding
ground-plane stitching vias, so the "+38% vias" question as posed is not a
board-level fact.

**"Fewer segments" is not less copper.** Total emitted copper length rises
**4529 mm -> 7760 mm (+71%)** while segment count falls 43%. Theta* replaces short
staircases with long chords: mean segment length 0.99 mm -> 2.98 mm, max
83.7 mm -> **166.2 mm**, segments over 100 mm 0 -> 15.

## 3. Full DRC, both arms (3 runs each, sets intersected)

| rule | production (`False`) | any-angle (`True`) | delta |
|---|---|---|---|
| **creepage** | 106 | **232** | **+126** |
| clearance | 179 | 358 | +179 |
| **shorting_items** | 37 | **195** | **+158** |
| solder_mask_bridge | 4 | 196 | +192 |
| hole_clearance | 31 | 72 | +41 |
| copper_edge_clearance | 8 | 15 | +7 |
| drill_out_of_range | 3 | 5 | +2 |
| courtyards_overlap | 1 | 1 | 0 |
| **raw error total** | **379** | **1087** | **+708** |
| track_width | 0 | 0 | 0 |
| annular_width | 0 | 0 | 0 |

Set diff (distinct violation identities): **889 NEW**, 187 resolved.
New by rule: clearance 246, solder_mask_bridge 196, shorting_items 195,
creepage 163, hole_clearance 72, copper_edge_clearance 14, drill_out_of_range 3.

Run-to-run stability: production arm 0 unstable rows across 3 runs; any-angle arm
14 unstable rows (intersected 1020 of union 1034). The intersected sets above are
the conservative reading.

### Verdict per new violation class

| class | new | verdict |
|---|---|---|
| `shorting_items` (8 HV<->SELV) | 195 | **UNSAFE — blocking** |
| `creepage` (44 HV<->SELV) | 163 | **UNSAFE — blocking** |
| `clearance` (8 HV<->SELV) | 246 | **UNSAFE — blocking** |
| `hole_clearance` (8 HV<->SELV) | 72 | **UNSAFE — blocking** |
| `solder_mask_bridge` (1 HV<->SELV) | 196 | **UNSAFE** |
| `copper_edge_clearance` | 14 | unsafe (board-edge copper), not barrier-crossing |
| `drill_out_of_range` | 3 | manufacturability, not safety |

There is no new violation class that is safe to accept.

## 4. Creepage, derived independently from pad/track geometry

Because kicad-cli reports **one creepage violation per net pair, not per pad pair**,
the geometry was derived directly rather than counted: exact pad cores via
`pad_geometry.pad_core_polygon` + `pad_corner_radius` (no arc polygonisation),
tracks as width-buffered `LineString`s, PTH pads expanded to all copper layers,
HV/SELV membership from `elec/domain_manifest.yaml` (27 HV / 35 SELV nets, literal
names — not the `-line` keyword heuristic).

Enforced figure: **`MIN_BARRIER_WIDTH_MM` = 12.6 mm** (PD3 reinforced), read from
`isolation_constants.py`. Not modified.

| | production | any-angle |
|---|---|---|
| distinct HV<->SELV net pairs closer than 12.6 mm | 83 | **129** (+46) |
| item-level offending pairs | 486 | 728 |
| **global minimum HV<->SELV separation** | 0.0331 mm | **0.0000 mm** |

The production arm's worst case (0.0331 mm, `hb.gate_hs.driver-p1-1` pad C22.1 <->
`gnd` pad C6.2) is a **pad-to-pad placement** defect that both arms share — it is
not caused by routing and is out of scope here.

**The any-angle arm introduces 8 HV<->SELV pairs at exactly 0.0000 mm — direct
metallic contact. Every one of them involves an any-angle track or via:**

| layer | HV side | SELV side | mm |
|---|---|---|---|
| F.Cu | `tank-out` track | `I_SENSE` pad T1.3 | 0.0000 |
| F.Cu | `+15V_LS` via | `+3V3` pad U6.3 | 0.0000 |
| In3.Cu | `+170V_BUS` pad C2.1 | `WDT_RESET_N` track | 0.0000 |
| In4.Cu | `+170V_BUS` pad PS1.1 | `WDT_KICK` track | 0.0000 |
| In4.Cu | `tank-out` pad R30.2 | `RTD_DRDY` track | 0.0000 |
| In4.Cu | `discharge.k_dis1-nc` track | `discharge.k_dis1-coil1` pad K2.2 | 0.0000 |
| B.Cu | `PWR_RTN` pad K2.1 | `power_in.bypass_relay-coil1` track | 0.0000 |
| B.Cu | `PWR_RTN` pad R8.1 | `power_in.bypass_relay-coil2` track | 0.0000 |

This is corroborated independently: kicad-cli's own `shorting_items` rows name the
same pairs (`+170V_BUS`/`WDT_RESET_N`, `+170V_BUS`/`WDT_KICK`,
`PWR_RTN`/`power_in.bypass_relay-coil2`, `DC_BUS_RTN`/`WDT_RESET_N`,
`discharge.k_dis1-coil1`/`discharge.k_dis1-nc`). Two methods, same answer.

Three are individually sufficient to reject:

- **`tank-out` <-> `I_SENSE`.** `tank-out` is the resonant tank node, measured
  570.5 Vrms / 923.7 V peak. It is the net the 10.0 mm PD3 functional figure
  (`HV_TANK_CREEPAGE_ENFORCED_MM`) exists for. It lands on a SELV sense pad at
  0.0000 mm — a shortfall against **both** the 12.6 mm reinforced barrier and the
  10.0 mm functional figure.
- **`+170V_BUS` <-> `WDT_RESET_N` / `WDT_KICK`.** The DC bus in contact with the
  watchdog reset and kick lines — the SELV nets whose whole purpose is to fail the
  system safe.
- **`discharge.k_dis1-nc` <-> `discharge.k_dis1-coil1`.** The mains-side discharge
  relay contact shorted to *its own SELV coil*, defeating the isolation of a safety
  interlock.

### Why the any-angle arm reaches across the barrier

There is no physical barrier for it to respect. `scripts/check_isolation_keepout.py`
reports, on **both** arms identically, that the `MAINS_SELV_ISOLATION_BARRIER`
keepout zone **does not exist on the board** (pre-existing; not caused by either
arm). Nothing in the router's configuration space forbids crossing the mains<->SELV
boundary. What kept production traces from crossing was an *emergent* property —
grid A* emits short local staircases (mean 0.99 mm). Theta*'s line-of-sight
shortcut removes exactly that property: it emits single chords up to 166 mm that
fly straight across the board, and therefore straight across the isolation region.

This is compounded by which nets get routed. The any-angle arm emits tracks for
**9 HV-domain nets** vs 3 in production — newly including `tank-out`, `input`,
`discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `discharge.r_dis1a-p2`,
`discharge.r_dis2a-p2`, `+15V_LS`. Several are single-segment: `tank-out` is **one
chord**, `discharge.r_dis1a-p2` is one 139.4 mm chord. Mains-domain nets are being
flown across the board as single diagonals.

A further structural note, independent of these measurements:
`_astar_search._dispatch_search` forwards `thermal_flat`/`thermal_weight`,
`congestion_tensor` and `corridor_mask` **only** to the plain-2D-A* arm. The
Theta*/Lazy-Theta* arms silently drop all three (documented in PR #1381's own
`_resolve_any_angle_search`). Adopting any-angle therefore also silently disables
thermal-aware and congestion-aware routing and all corridor confinement.

## 5. The fake completions

`has_any_copper and not fully_connected`. The premise that production has 0 is not
reproducible — production has **6**; any-angle has **7**.

| net | production | any-angle | assessment |
|---|---|---|---|
| `+15V`, `+3V3`, `V_BUS_SENSE`, `gnd`, `vcc` | fake | fake | **pre-existing, both arms.** Power/ground nets delivered by zone pours, which the segment/via audit cannot see. Not a failure mode of either arm. |
| `GATE_LS` | fake | — | resolved by any-angle |
| `safety.thermal.comp-inp` | **unrouted** | **fake** | a net that was previously *not routed at all* now emits copper that does not connect its pads. New, but strictly an unrouted net moving sideways. |
| `fb` | **fully pad-connected** | **fake** | **genuine regression.** A working net now has copper that fails to join its own pads. |

So: 5 pre-existing, 1 previously-unattempted net becoming a fake completion, and
1 true regression. Additionally, **3 nets regress from fully pad-connected to not
connected** under any-angle: `PWM_HS` (now unrouted), `fb` (now fake completion),
`rtd_pan.r_low_top-inn` (now unrouted). The +20 net gain is a net figure hiding 3
losses.

## 6. Manufacturability

These are the only checks the any-angle arm passes cleanly.

- **Trace-width floors per netclass: PASS, both arms.** 0 segments below their
  netclass `trace_width`. 0 `track_width` DRC violations either arm. Widths group
  correctly by class (Default 0.2, FinePitch 0.2, GateDrive* 0.4, Power 1.0,
  HighVoltageSignal 0.5, HighVoltage 5.0).
- **Annular-ring floor 0.254 mm: PASS, both arms.** All 169 (production) and 172
  (any-angle) vias — including the 37/40 blind vias — have a ring of exactly
  0.300 mm. 0 below floor; 0 `annular_width` DRC violations. This is structural:
  `Via::new` (`packages/temper-orchestration/src/pipeline_route.rs:191`) clamps pad
  diameter to `drill + 2*MIN_ANNULAR_RING_MM`.
- **Via legitimacy.** Board-level via count is 169 -> 172, **+3 vias (+1.8%)**, not
  +38%. Blind vias 37 -> 40. All spans are F.Cu<->B.Cu / F.Cu<->In3.Cu /
  F.Cu<->In4.Cu — no illegal spans. The vias are legitimate; the "+38%" premise
  came from a partial count.
- **Acute angles / acid traps.** 12 sub-90-degree joints in *each* arm (0.27% of
  4489 joints vs 0.48% of 2524). No absolute increase. Arbitrary-angle segments
  rise 112 (2.46%) -> 329 (12.62%), but note production is **already** 51%
  non-axis-aligned (48.7% at 45 degrees) — diagonal copper is not new, only its
  length is.

## 7. Recommendation

**REJECT.** Do not flip `enable_theta_star` / `enable_lazy_theta_star` at
`_adapter_convert.py:393-394`.

The connectivity gain is real but smaller than claimed (+20, not +33), it is not
free (3 nets regress, 1 into a fake completion), and it is bought with copper that
physically touches across the mains<->SELV isolation boundary in 8 places,
including the 570 V resonant tank onto a SELV sense pad and a safety relay's mains
contact onto its own coil. On an IEC 60335-1 mains design that is not a
DRC-count regression to be triaged later; it is a shock-hazard defect in the
artifact being produced.

**What PR #1381 got right and should still land:** its actual change — naming and
logging the resolved search, and pinning the divergence in a test — is correct and
useful, and its decision *not* to flip the flags was the right call. Only its
measurement table should be corrected against the numbers above before anyone
relies on it.

**What would have to be true to reopen this**, in order:

1. The `MAINS_SELV_ISOLATION_BARRIER` keepout zone must actually exist on the board
   and be honoured by the router's configuration space. Any-angle search is
   unsafe on this board primarily because nothing constrains a 166 mm chord;
   that is a missing constraint, not an unfixable property of Theta*.
2. Theta*/Lazy-Theta* must stop dropping `corridor_mask` (and thermal/congestion)
   in `_dispatch_search`. Without corridor support, any-angle cannot be confined
   even once a barrier exists.
3. Re-measure with a maximum-chord-length bound, and require **zero** new
   HV<->SELV pairs below 12.6 mm and zero new `shorting_items`.

Until at least (1) and (2), any-angle should stay off, and the stale
`NOTE 2026-06-23` should be corrected to say so on *these* grounds — its original
two premises really have expired, but the conclusion it reached is still the
right one for a different and much stronger reason.

## 8. Reproduction

```
make worktree NAME=<name> BASE=origin/main VENV=1
env -u CONDA_PREFIX make extensions
uv run --no-sync python scripts/check_stale_extensions.py     # expect 10/10 fresh
# route both arms through production route_pcb(), forcing only the two flags;
# stage each routed board with .kicad_pro + fp-lib-table + libs/ + regenerated
# .kicad_dru, then run_drc 3x and intersect the violation sets.
```

Neither `pcb/temper.kicad_pcb` nor any threshold, gate, or test was modified by
this review.
