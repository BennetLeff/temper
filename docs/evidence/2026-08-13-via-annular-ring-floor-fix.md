<!-- provenance: this document (branch fix/via-annular-ring-floor, worktree
/home/bennet/Desktop/temper-via-annular-fix, based on origin/fix/board-schematic-resync
a3fbaff37, PR #1134). Stacks on top of PR #1142's docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md
and docs/hardware/FAB_CAPABILITY.md (cherry-picked commit ccc795ccc from
docs/jlcpcb-fab-capability-envelope onto this branch) -- coordinate merge order with that PR.
kicad-cli 10.0.5. No subagents were dispatched; all measurements below were performed directly. -->

# Via annular-ring floor: independent verification, fix, and DRC delta

## 1. Independent verification of the 44/44 finding

PR #1142's evidence doc reports 44/44 vias failing JLCPCB's 0.254mm 2oz PTH annular-ring floor.
Re-measured independently here with a standalone stdlib-only script (balanced-paren scan of
every `(via ...)` block in `pcb/temper.kicad_pcb`, `ring = (size - drill) / 2`) against the exact
same board content (`sha256(pcb/temper.kicad_pcb) = b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6`,
matching PR #1142's cited hash):

```
Total via blocks found: 44
  size=0.4000mm drill=0.2000mm ring=0.1000mm count=4  -> FAIL vs 0.254mm floor
  size=0.8000mm drill=0.4000mm ring=0.2000mm count=40 -> FAIL vs 0.254mm floor
44/44 vias FAIL the 0.254mm annular-ring floor.
```

Confirmed: 44/44, both families, independently reproduced. Not taken secondhand from PR #1142's
own document.

## 2. What generates each via family (root-cause, not just geometry)

The two via families are **not** two arbitrary sizes -- they trace to identifiable code:

- **0.4mm/0.2mm (4 vias)**: `TEMPER_NET_CLASSES["FinePitch"]` (`core/design_rules.py`) --
  confirmed by cross-referencing `TEMPER_NET_ASSIGNMENTS` (2 of the 4 vias' current net names,
  `sclk` and `RTD_SDI`, resolve to `FinePitch`; `get_via_diameter`/`get_via_drill` return exactly
  0.4/0.2 for this class).
- **0.8mm/0.4mm (40 vias)**: two literal, independently-hardcoded generator constants,
  `router_v6/_ground_plane.py` and `router_v6/_power_islands.py`'s `VIA_SIZE_MM =
  0.8`/`VIA_DRILL_MM = 0.4` -- confirmed by their own inline comments, which cite this exact
  board's existing `(size 0.8) (drill 0.4)` vias as the convention they match. These two
  constants are the sole source of the literal `0.8`/`0.4` pair anywhere in `router_v6/` outside
  net-class tables (grepped). `_power_islands.py`'s constant carried a comment claiming it
  mirrored `TEMPER_NET_CLASSES["Power"]`'s via convention "0.8/0.4mm exactly" -- that claim was
  already stale before this fix (Power's own via fields were corrected to 1.0/0.5mm on
  2026-08-12, docs/evidence/2026-08-12-netclass-param-reconciliation.md, and this hardcoded
  constant was never updated alongside it), confirming these two constants were always
  independent, unsynced generators, not derived mirrors.

Every other `TEMPER_NET_CLASSES` entry (Power, GND, HighSpeed, Signal, GateDriveHV,
GateDriveSELV, HighCurrent, HighVoltageIsolated) and the router's Python-side defaults
(`constraints_design_rules.py`, `stage0_data.py`) also declare a via geometry below the 0.254mm
floor, even though none of them currently manifest on the routed board -- a latent regression
risk for the next route, per the task brief's instruction to fix the generator, not only the
board file.

## 3. Fix: uniform 0.3mm annular ring, board-wide

**Derivation.** Minimum pad diameter to clear the floor: `pad = drill + 2 x 0.254mm`. Applied
directly this lands right at the edge (e.g. drill 0.2mm -> pad 0.708mm, zero margin). Chose a
`0.3mm` ring **design target** instead (`pad = drill + 2 x 0.3mm`) for a small, deliberate margin
above the bare floor (0.046mm), for two reasons: (a) `ACMains`/`HighVoltage`/`HighVoltageTank`
already use a 1.2mm/0.6mm pad/drill pair -- a 0.3mm ring -- and already pass; reusing that exact
ring width keeps every via family on the board at one consistent, already-precedented value
instead of introducing a new one. (b) JLCPCB's own capability page flags its published PTH
annular-ring figure as having "no separate absolute minimum" at 2oz -- 0.254mm already is both
the recommended and the only published figure -- so sitting exactly on it, as the bare-minimum
computation would, is the kind of "meets exactly, no margin" situation PR #1142's own evidence
doc flagged as a real DFM-review risk for the *other* (0.2mm-ring) family before this fix.

**Note on PR #1142's own §9 arithmetic.** That document's derivation section computed target pad
sizes as `old_pad + 2 x 0.254mm` (e.g. "0.4mm + 2x0.254 ~ 0.91mm") -- adding the *new floor* to
the *old pad* rather than computing from the drill (`drill + 2 x new_ring`) or from the deficit
(`old_pad + 2 x (new_ring - old_ring)`). Both of the latter are algebraically identical and give
0.708mm for the 0.2mm-drill family, not the ~0.91mm/~1.31mm section 9 computed. This was not
carried into this fix (verified independently per §1); recorded here because the task brief
explicitly asked not to take a figure secondhand, and this is the second instance of that
caution paying off in this same document lineage (the first being the `DEFAULT_ROUTING_CLEARANCE_MM`
hypothesis PR #1142 itself already corrected).

**Changed (all raised to a 0.3mm ring, drill unchanged in every case):**

| Site | Old (pad/drill, ring) | New (pad/drill, ring) |
|---|---|---|
| `pcb/temper.kicad_pcb`: 4 vias | 0.4/0.2, 0.10mm | 0.8/0.2, 0.30mm |
| `pcb/temper.kicad_pcb`: 40 vias | 0.8/0.4, 0.20mm | 1.0/0.4, 0.30mm |
| `TEMPER_NET_CLASSES["FinePitch"]` | 0.4/0.2 | 0.8/0.2 |
| `TEMPER_NET_CLASSES["Power"]` | 1.0/0.5, 0.25mm | 1.1/0.5 |
| `TEMPER_NET_CLASSES["GND"]` | 1.0/0.5, 0.25mm | 1.1/0.5 |
| `TEMPER_NET_CLASSES["HighVoltageIsolated"]` | 1.0/0.5, 0.25mm | 1.1/0.5 |
| `TEMPER_NET_CLASSES["GateDriveHV"/"GateDriveSELV"]` | 0.8/0.4 | 1.0/0.4 |
| `TEMPER_NET_CLASSES["HighCurrent"]` | 0.8/0.4 | 1.0/0.4 |
| `TEMPER_NET_CLASSES["HighSpeed"/"Signal"]` | 0.6/0.3, 0.15mm | 0.9/0.3 |
| `create_temper_design_rules()` default | 0.6/0.3 | 0.9/0.3 |
| `router_v6/constraints_design_rules.py` defaults (2 sites) | 0.6/0.3 | 0.9/0.3 |
| `router_v6/stage0_data.py` default | 0.6/0.3 | 0.9/0.3 |
| `router_v6/_ground_plane.py` `VIA_SIZE_MM`/`VIA_DRILL_MM` | 0.8/0.4 | 1.0/0.4 |
| `router_v6/_power_islands.py` `VIA_SIZE_MM`/`VIA_DRILL_MM` | 0.8/0.4 | 1.0/0.4 |
| `router_v6/_astar_search.py`/`_astar_nlayer.py`: `via_diameter=net_rules.via_diameter_mm if net_rules else 0.6` (used when a net being routed resolves to no net_rules) | 0.6 fallback | 0.9 fallback |
| `packages/temper-placer/configs/netclass_rules.yaml` | (mirrors the table above) | (mirrors the table above) |
| `pcb/temper.kicad_pro` `net_settings.classes[*].via_diameter` | (mirrors) | (mirrors), plus `Default` 0.6->0.9 and `Differential` 0.5->0.85 (kicad_pro-only classes) |
| `pcb/temper.kicad_pro` `design_settings.rules.min_via_annular_width` | 0.15mm | 0.254mm (the exact fab floor, project-level enforced minimum) |
| `pcb/temper.kicad_pro` `design_settings.via_dimensions` (UI preset list) | 0.6/0.3, 0.8/0.4, 1.0/0.5, 1.2/0.6 | 0.8/0.2, 0.85/0.25, 0.9/0.3, 1.0/0.4, 1.1/0.5, 1.2/0.6 (every preset now a 0.3mm-ring family) |

`ACMains`/`HighVoltage`/`HighVoltageTank` (1.2mm/0.6mm, 0.3mm ring already) needed no change --
they already sit at the same target ring this fix standardizes on.

**Not changed, deliberately out of scope**: `FinePitch`/`Differential` trace width (0.127mm) and
same-footprint-pad clearance (0.1mm), both below the 0.15mm 2oz trace/space floor per PR #1142's
own finding -- neither is a via annular-ring or hole-clearance question, and neither is currently
used by any routed track (latent risk, not a present violation). `router_v6/astar_core.py`'s
`_astar_search_3d`/`_route_segment_3d` function-signature defaults (`via_diameter: float = 0.6`,
2 sites) were investigated and deliberately left unchanged: both real production call sites
(`_astar_search.py`, `_astar_nlayer.py`, fixed above) always pass `via_diameter` explicitly, so
these bare defaults are unreachable in production -- the only place that reaches them is
`test_astar_3d_production_scale_spike.py`, which deliberately characterizes 0.6mm as `_astar_
search_3d`'s documented default (multiple hardcoded `via_diameter=0.6` fixture values, a `via_
diameter_mm = 0.6  # _astar_search_3d's default` comment) for its own keepout-radius legality
math, unrelated to board fab-floor compliance. Changing it would require rewriting that test's
own fixtures for zero board-facing effect. `ViaTemplate`'s own bare via-array defaults
(`core/design_rules.py`'s pinned oracle and the Rust `temper-design-bundle`
crate's built-in `Via1x1`/`Via2x2`/`Via3x3`/`Via4x4` pad/drill pairs, all 0.6mm/0.3mm) were
identified but left unchanged: `get_via_template`/`via_templates` has zero production consumers
in `router_v6/` or anywhere else under `packages/temper-placer/src/` (grepped) -- it is
declared-but-dead code, not a live via-geometry source, and fixing it would require a Rust crate
change for no board-facing effect. `stage0_data.py`'s `min_annular_ring_mm: float = 0.1` field is
similarly declared-but-unused (zero non-test consumers) and left unchanged.

## 4. `hole_clearance` (task item 4): does NOT share root cause with annular ring

**Verdict: no shared root cause.** `hole_clearance` measures the distance from a hole (via or PTH
pad) to *neighboring, different-net* copper -- a two-object spacing/congestion property. Annular
ring measures a via's *own* pad diameter against its *own* drill diameter -- a single-object
geometry property. They are different dimensions of the same board, not two views of one defect.

Evidence: of the 89 `hole_clearance` violations remaining after this fix, 58 involve at least one
via's hole, but in every one of those the OTHER item is a track or a different pad -- only 4 of
89 are via-to-via. Enlarging every via's pad (this fix) left the count essentially flat (90 -> 89,
see §5) precisely because pad size is not what `hole_clearance` measures; a via's hole position
never moved. The DRU-rule threshold raise (0.25mm -> 0.28mm, in isolation) moved it +1 (90 -> 91,
measured directly, see §5's attribution table); the two effects combine to -1 net.

**The DRU rule itself was fixed** (task item 2): `scripts/generate_kicad_dru.py`'s `"Via hole
clearance"` rule raised from 0.25mm to 0.28mm, JLCPCB's published PTH-to-track absolute minimum
(`VIA_HOLE_CLEARANCE_MM`, with its own derivation comment in that file). This is a
manufacturability floor correction, not a fix to the 90 (now 89) findings themselves -- those are
a routing-congestion problem, explicitly the scope of the separate rerouting effort the task
brief carves out ("stripping disconnected copper and rerouting 7 nets"). Left there, not
half-fixed here.

## 5. DRC delta, with attribution

All measurements: `temper_placer.validation._drc_api.run_drc` (`--all-track-errors`,
single-thread `KICAD_CONFIG_HOME` pin), `pcb/temper.kicad_dru` regenerated from the current
`scripts/generate_kicad_dru.py` first (the `ci_check_drc.py` protocol). kicad-cli 10.0.5.

### 5.1 True baseline vs. true new state (single sample each, both ends of the diff)

Scratch-copy comparison (`scripts/measure_uncapped_drc.py`'s own `make_scratch_board`, never
touches the real `pcb/temper.kicad_pcb`): board+kicad_pro+DRU all at the pre-fix committed state
(`a3fbaff37`, unmodified) vs. all three at this fix's state.

| Category | Baseline | New | Delta |
|---|---|---|---|
| `annular_width` | 4 | 0 | **-4** |
| `clearance` (capped raw) | 500 | 502 | +2 (noise-range; true uncapped count below) |
| `creepage` | 168 | 169 | +1 (single-sample; nondeterministic category, see §5.3) |
| `hole_clearance` | 90 | 89 | -1 |
| `shorting_items` | 181 | 194 | **+13** |
| `solder_mask_bridge` | 145 | 146 | +1 |
| `via_diameter` | 4 | 0 | **-4** |
| `via_dangling` (warning) | 30 | 25 | -5 |
| all other categories | unchanged | unchanged | 0 |

`pcb/temper.kicad_pcb`'s diff against this baseline is via `(size ...)/(drill ...)` fields only
(88 changed lines, 44 vias x 2 lines; confirmed via `git diff`) -- every category delta above is
therefore attributable to the via geometry change, the DRU rule change, or both; not to any other
board edit, because there is no other board edit.

### 5.2 Attribution: board-geometry effect vs. DRU-rule-threshold effect, isolated

4-way scratch comparison (board x DRU, each independently held at baseline or new):

| Category | base/base | base/newDRU | newBoard/base | newBoard/newDRU | DRU-only | board-only |
|---|---|---|---|---|---|---|
| `annular_width` | 44* | 44* | 0 | 0 | +0 | -44* |
| `clearance` | 502 | 500 | 501 | 502 | -2 | -1 |
| `creepage` | 168 | 168 | 169 | 169 | +0 | +1 |
| `hole_clearance` | 90 | 91 | 88 | 89 | **+1** | **-2** |
| `shorting_items` | 181 | 181 | 194 | 194 | **+0** | **+13** |
| `solder_mask_bridge` | 145 | 145 | 146 | 146 | +0 | +1 |
| `via_dangling` | 30 | 30 | 25 | 25 | +0 | -5 |
| `via_diameter` | 4 | 4 | 0 | 0 | +0 | -4 |

\* This 4-way table's "base board" combos use the LIVE (raised) `pcb/temper.kicad_pro`
(`scripts/measure_uncapped_drc.py`'s `make_scratch_board` always copies the current project
file), so `annular_width`'s 44 here reflects the OLD board measured against the NEW, stricter
`min_via_annular_width=0.254` -- not the originally-recorded ceiling value (4, measured against
the old 0.15mm project setting). §5.1's true end-to-end baseline (both files at their real,
committed pre-fix state) is the correct number for the PR/ceiling record; this table isolates
board-only vs. DRU-only effects for `clearance`/`hole_clearance`/`shorting_items`/`solder_mask_bridge`/`creepage`/`via_dangling`, none of which are sensitive to that same mismatch (`min_via_annular_width`
governs only `annular_width`/`via_diameter`, confirmed unaffected).

**`shorting_items` (+13) is entirely a board-geometry effect** (DRU-only = 0), i.e. entirely
caused by enlarging via pads, exactly the trade-off the task's hard constraints anticipated
("Enlarging via pads consumes clearance. Report the honest DRC delta, including any category
that worsens."). Investigated further, not merely reported as a number:

- 28 net-pairs became newly-shorting, 22 previously-shorting pairs resolved (net +6 unique pairs,
  +13 total instances after multiplicity).
- Some newly-shorting pairs involve HV-domain nets (`+170V_BUS`, `PWR_RTN`,
  `hb.gate_hs.driver-p1-1`/`-p2`, `SW_NODE`) against LV/signal nets -- flagged prominently, not
  buried in a count.
- `shorting_items` is a net-level connectivity check, not a point-distance one: the JSON's
  reported "items" for one such pair (`+170V_BUS` vs `WDT_RESET_N`) were a component pad and a
  track ~15mm apart -- i.e. the reported item pair is not necessarily the physical touch point,
  it is two representative items sampled from each now-electrically-connected net. Full
  root-causing of all 28 pairs (tracing each to its actual touch point) was not completed within
  this task's scope.
- This board is independently documented (task brief, this PR's hard constraints) to have 66% of
  its `clearance` violations traceable to "fake completion" -- disconnected copper the router
  left behind, with only 27/139 nets actually pad-connected -- scoped to a separate, already-named
  rerouting effort. Enlarging via pads in that same congested, partially-disconnected copper
  landscape is exactly where a pad-size increase would surface new incidental contact. This
  finding is reported for that effort to account for, per the task's explicit instruction to
  "say so and scope around it" rather than attempt a fix here that would collide with it.
- **No IEC-60335 creepage/clearance safety figure was touched to accommodate any of this** --
  confirmed by `git diff` scope (only via `size`/`drill` fields in the board; only via_diameter
  fields, the DRU hole_clearance constant, and one project-level annular-ring setting elsewhere).
  If the newly-shorting HV-domain pairs represent a genuine new safety-margin problem (as opposed
  to the pre-existing disconnected-copper artifact described above), that is exactly the kind of
  finding the task's hard constraints ask to be reported rather than silently absorbed by
  loosening a safety figure -- and it is reported here.

### 5.3 True (uncapped) `clearance` count

Raw kicad-cli caps `clearance` at ~500 (a report-widget limit, not a board property --
`docs/evidence/2026-08-12-uncapped-drc-measurement.md`). Uuncapped via
`scripts/measure_uncapped_drc.py dru-category clearance` (provably-exhaustive DRU-rule
partition-and-sum, the same method PR #1134's own 1,085 figure used):

**True clearance count on the fixed board: 1093** (PR #1134's own recorded true count on the
pre-fix board: 1085; delta **+8**). Consistent with a modest congestion increase from larger via
pads, an order of magnitude smaller than the `shorting_items` delta, and not concentrated in any
single netclass pairing per the partition breakdown (largest single band: `HV to LV` sub-buckets,
consistent with the pre-fix board's own dominant band).

### 5.4 Multi-sample / nondeterminism check

130 samples (>= the file's 120-sample floor for a nondeterministic-category record),
`temper_placer.validation._drc_api.run_drc`, kicad-cli 10.0.5:

```
clearance: min=499 max=499 dist={499: 130}              (capped; true count 1093, see 5.3)
copper_edge_clearance: min=7 max=7 dist={7: 130}
courtyards_overlap: min=8 max=8 dist={8: 130}
creepage: min=168 max=169 dist={168: 27, 169: 103}       -- the one nondeterministic category
drill_out_of_range: min=4 max=4 dist={4: 130}
hole_clearance: min=89 max=89 dist={89: 130}
hole_to_hole: min=3 max=3 dist={3: 130}
shorting_items: min=194 max=194 dist={194: 130}
solder_mask_bridge: min=146 max=146 dist={146: 130}
track_width: min=199 max=199 dist={199: 130}             (capped; unverified uncapped, out of scope)
tracks_crossing: min=1 max=1 dist={1: 130}
(annular_width, via_diameter: absent from every one of 130 samples -- 0/0/130)

warnings, all 9 categories fully deterministic across 130 samples (lib_footprint_issues 13,
lib_footprint_mismatch 26, missing_courtyard 5, pth_inside_courtyard 1, silk_edge_clearance 1,
silk_over_copper 63, silk_overlap 199, track_dangling 44, via_dangling 25)
```

**11 of 12 error categories and all 9 warning categories are fully deterministic** across all
130 samples. Only `creepage` varies, spread 1 (unchanged from the prior record's own spread),
band shifted up by 1 (166-168 -> 168-169) -- consistent with the same upstream KiCad
pointer-dedup artifact (issue #20048) this repo has documented since #602, not a new source
(this fix touches no creepage-governing rule or copper). Ceiling = max(169) + 1 headroom = 170,
numerically unchanged from the prior record (coincidence: prior max 168 + spread-2 headroom =
170). `scripts/ci_check_drc.py --backend kicad-cli`'s noise-headroom guard passes with zero
slack (170 - 169 = 1 >= 169 - 168 = 1), verified directly (`DrcRatchet.check_noise_headroom()`
returns `[]`) before committing `power_pcb_dataset/drc_ceiling.json`.

`shorting_items` (194/194) and `hole_clearance` (89/89) are **fully deterministic** at 130
samples, confirming §5.1-5.2's single-sample measurements were not noise -- the +13
`shorting_items` rise is a stable, repeatable property of this board's geometry, not a
transient artifact.

`error_ceiling`: 1901 -> 1914 (+13, sum of every per-type delta in §5.1: -4 annular_width, +8
clearance, +0 creepage, -1 hole_clearance, +13 shorting_items, +1 solder_mask_bridge,
-4 via_diameter). `warning_ceiling`: 382 -> 377 (-5, via_dangling only).
`scripts/check_drc_ceiling_approval.py` and `scripts/check_measurement_provenance.py` both
PASS against this record (the latter after also re-pinning
`packages/temper-placer/configs/temper_constraints.references.yaml`'s content-hash freshness
block -- a second, independently-registered measurement artifact keyed to
`pcb/temper.kicad_pcb`'s content hash; re-verified, not blindly re-pinned, that this fix's
board diff touches zero `reference`/`Sheetpath`/footprint content, only `(via ...)` `size`/
`drill` fields, so that file's designator aliases needed no re-derivation).

## 6. Independent gate verification

`scripts/check_fab_capability_floor.py` (added by this PR, see §7) passes cleanly against the
fixed tree (all 5 properties P1-P5 OK) and was mutation-tested against the exact pre-fix shapes
of every property (16 tests, `scripts/tests/test_check_fab_capability_floor.py`), proving it
would have caught this defect had it existed before the board was ever routed.

## 7. Gate added

`scripts/check_fab_capability_floor.py`, reading `docs/hardware/FAB_CAPABILITY.md` sec.5 (a new
fenced `yaml` block, the same sec.1 table's figures in machine-readable form -- this script
hardcodes no fab number itself). Five properties: real board via geometry (P1), every
`TEMPER_NET_CLASSES` via template (P2), the two router_v6 generator constants (P3), the DRU rule
constant and its emitted text (P4/P5). Registered in
`temper_placer.validation.gate_input_registry._CI_SCRIPT_SURVEY` and wired into
`.github/workflows/python-tests.yml`'s `Board, Provenance & Requirements Gates` job, immediately
after the thematically-adjacent router-clearance-floor gate. While registering it, two
pre-existing, unrelated gaps of the identical shape (`check_router_clearance_floor.py` and
`check_wasm_covered.py`, both already invoked in CI but never registered, confirmed pre-existing
on `origin/fix/board-schematic-resync` before this branch) were found by this PR's own U4
completeness test and fixed alongside it.

## 8. Left undone

- Full root-cause trace of all 28 newly-shorting net-pairs (§5.2) -- reported, not resolved; the
  disconnected-copper/rerouting effort this task's brief carves out is better positioned to fix
  the underlying congestion than a via-geometry PR is to rewire it.
- `FinePitch`/`Differential` trace width (0.127mm) and same-footprint clearance (0.1mm), both
  below the 2oz trace/space floor per PR #1142 -- latent, not present on the routed board, and not
  a via/hole-clearance question.
- `ViaTemplate`'s Rust-crate-level 0.6mm/0.3mm defaults (`Via1x1`/`Via2x2`/`Via3x3`/`Via4x4`) --
  identified as dead code (zero production consumers), not fixed, since fixing it would touch a
  Rust crate for zero board-facing effect.
- `docs/hardware/PCB_SPECIFICATION.md` / `GROUNDING_EMI_STRATEGY.md` / `POWER_PLANE_DESIGN.md`'s
  1oz-vs-2oz L4 disagreement and the board's missing `(stackup ...)` declaration (PR #1142 §3) --
  out of this fix's scope entirely (copper-weight declaration, not via geometry).
