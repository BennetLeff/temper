<!-- provenance: commit=1952c6e36a628e86f417133d08ca24ea4d6349ce (main at task start) dirty=true -- this doc, packages/temper-placer/src/temper_placer/router_v6/_power_islands.py, packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py (docstring only, no behavior change), packages/temper-placer/tests/router_v6/test_power_islands.py, and scripts/generate_power_islands.py are the diff this task produced. pcb/temper.kicad_pcb is UNCHANGED by this task -- verified `git status --short pcb/temper.kicad_pcb` empty throughout. -->

# In2.Cu power islands: a real generator, a corrected premise, and measured DRC/connectivity deltas

**Branch:** `feat/in2cu-power-islands`
**Scope:** `In1.Cu`/`gnd` was solved in #1022/#1033. This task's job was
`In2.Cu` -- the power islands (`+3V3`, `vcc`, `+15V`, `V_BUS_SENSE`).

## Headline

1. **An In2.Cu zone can now be emitted at all.** A new generator,
   `packages/temper-placer/src/temper_placer/router_v6/_power_islands.py`
   (`generate_power_islands_content`), produces real `(zone ...)` geometry
   on `In2.Cu` for all four power-island rails, plus drop vias and an
   F.Cu backbone per rail -- following the exact precedent
   `_ground_plane.py` already set for `In1.Cu`/`gnd`. Validated only on
   scratch copies of the real board; `pcb/temper.kicad_pcb` itself is
   untouched.
2. **The task's own premise about the fix mechanism was wrong, and I did
   not follow it.** The brief suggested driving eligibility from
   `NetClassRules.routing_strategy`, stating "the GND/Power classes carry
   `routing_strategy: plane_preferred`." Measured directly: `Power`'s is
   `None`, not `"plane_preferred"` -- and setting it to match would not
   close an accidental gap the way GND's own fix did. It would **revert
   an already-landed, evidence-corroborated, actively-tested project
   decision** (R1/R7 of
   `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`) that
   `Power`-class nets are deliberately trace-only. See S:2 for the full
   trace and why I built a standalone generator instead of wiring this
   into the shared eligibility path.
3. **Creepage does not regress** (the task's stated blocker). 5 repeated
   samples each, identical `kicad-cli 10.0.5` invocation: baseline
   363-365, with power islands 360-361 -- the ranges do not overlap, and
   the islands board is consistently *lower*, never higher.
4. **Per-rail pad connectivity moves from 0 (no copper of any kind) to a
   real, if partial, connected group for all four rails** -- `+3V3`
   15/51, `vcc` 3/13, `+15V` 2/10, `V_BUS_SENSE` 2/4 (all from a baseline
   of 1/N, i.e. zero copper, on every rail).
5. **Honest cost, matching the #1033 standard**: `clearance` (+107),
   `tracks_crossing` (+34, from 1 to 35), `solder_mask_bridge` (+34), and
   `hole_clearance` (+5) all regress, deterministically (near-zero spread
   across 5 samples each side) -- the same "new copper vs. pre-existing
   other-net F.Cu copper" tradeoff `_ground_plane.py` already documented
   and left unfixed for `gnd`, now measured here for the power rails too.
   This is **not** hidden behind the creepage headline.

---

## 1. What was built

`packages/temper-placer/src/temper_placer/router_v6/_power_islands.py`
(new) -- `generate_power_islands_content(pcb_path, *, nets=POWER_ISLAND_NETS,
domain_manifest_path=...)`. Given a `.kicad_pcb` path, returns
`(new_content, {net_name: PowerIslandResult})`. Processes rails in
pad-count-descending order (`+3V3` 51, `vcc` 13, `+15V` 10,
`V_BUS_SENSE` 4 unique pad positions, measured against the production
board) and, for each:

- Computes a **per-component-cluster** zone footprint (`cluster=True` --
  islands, plural, matching this layer's documented intent, unlike
  `gnd`'s single board-spanning hull), clipped against the board outline,
  the shared HV/SELV keepout, and every **previously processed rail's**
  own new zone footprint (buffered by 0.4mm) -- the one genuinely new
  geometry problem this task has that the ground-plane task did not:
  multiple nets sharing one physical layer, not just net-vs-HV-keepout.
- Drops a via per (non-through-hole) pad, connecting `F.Cu` (where the
  components/pads live) down to `In2.Cu`, avoiding existing drilled holes,
  the HV keepout, other nets' pre-existing F.Cu/B.Cu copper, and every
  **previously placed via/backbone segment from an earlier rail in this
  same run**.
- Emits an MST backbone on `F.Cu` (same "vias only union graph nodes for
  the layers literally named in the via's own `layers` tuple" reason
  `_ground_plane.py`'s own docstring documents) joining the drop vias,
  with the same bounded one-bend-detour-around-the-keepout heuristic,
  additionally treating this run's own already-placed F.Cu copper as a
  hard obstacle so two rails' backbones cannot cross each other.
- One shared fill-time keepout rule-area zone (`copperpour not_allowed`)
  is emitted on `In2.Cu` covering the HV keepout region once (not once
  per rail -- the region is net-independent) -- the same independent
  defense `_ground_plane.py` built against the pour-outline-hole-drop bug
  (a clipped hull with an interior hole around a deeply-nested HV pad
  silently re-filling that hole if only the exterior ring were emitted).

**What is reused, unmodified, from `_ground_plane.py` (read-only
import -- that file is out of this task's boundary and was not
touched):** `compute_hv_selv_keepout`, `_collect_hv_copper_geometry`,
`_collect_other_net_copper`, `_existing_drilled_holes`,
`_find_via_drop_point`, `mst_edges`, `_emit_keepout_zone_s_expr`,
`_dedupe_positions`. None of that hard-won collision-avoidance logic is
re-derived; only the multi-rail accumulation around it is new.

`scripts/generate_power_islands.py` (new) -- thin CLI wrapper, mirroring
`scripts/generate_ground_plane.py`'s `--pcb`/`--output` safety convention
(refused if equal) plus an optional `--nets` to run a subset (e.g. just
`+3V3`, the highest-value rail, if a maintainer wants the smallest
possible first step).

`packages/temper-placer/tests/router_v6/test_power_islands.py` (new) --
2 tests against the real production board (always on a `tmp_path` copy):
one asserting the measured connectivity improvement for all four rails
plus the generator's own report agreeing with reality, and one asserting
no two rails' emitted `In2.Cu` zone polygons overlap (the multi-rail
correctness property this task's geometry actually needed, beyond what
`_ground_plane.py`'s own single-net tests could cover). Both pass.

---

## 2. The course correction: why `_zone_layers_for_net` is untouched

The task named `_zone_layers_for_net`'s hardcoded
`return ["F.Cu", "B.Cu"]` as *the* blocker for inner-layer expressibility,
and suggested closing it by driving eligibility from
`NetClassRules.routing_strategy` -- explicitly citing "the GND/Power
classes carry `routing_strategy: plane_preferred`... that is probably the
right signal," mirroring the paired fix GND itself already got (R3/R4 of
`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`: GND's entry
was corrected from the Python default `None` to `"plane_preferred"`,
closing an accidental drift against a human-authored config that already
said so).

**Measured directly, before writing any code:**

```
TEMPER_NET_CLASSES["Power"].routing_strategy == None   # not "plane_preferred"
_zone_layers_for_net("+3V3") == []
_zone_layers_for_net("vcc") == []
```

I prototyped the obvious mirror of GND's fix -- add
`routing_strategy="plane_preferred"` to `Power` in `design_rules.py`
(and the paired oracle file, `tests/core/_design_rules_py_oracle.py`,
which a differential test pins bit-identical to it), and add an
`nc_name == "Power"` branch to `_zone_layers_for_net` returning
`["In2.Cu"]`. It ran and produced plausible-looking output. **It was
wrong, and I reverted it before running any DRC measurement against it,**
because reading the surrounding test suite surfaced a fact the task's own
premise directly contradicts:

`Power` staying trace-only -- no default pour of any kind, on any
layer -- is **not** an accidental gap like GND's was. It is an
already-landed, deliberate, three-source-corroborated decision, from the
*same* plan document GND's fix comes from:

- **R1**: "No net in `Power` or `GateDrive` gets a default pour: `+3V3`,
  `vcc`, `+15V`, `+15V_LS`, `V_BUS_SENSE` ... route as traces only,"
  corroborated by `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS3.4/3.6-3.8
  (a trace-width spec with local decoupling for each of these nets, never
  a pour spec), `packages/temper-placer/configs/temper_constraints.yaml`
  (a separate, human-authored net-class table declaring
  `Power: routing_strategy: "wide_trace"`, not any plane tier), and
  `docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1 (independently
  reached DELETE, not pour, for all nine Power/GateDrive nets after
  checking real current budgets).
- **R7**: an explicit, named regression test exists specifically to catch
  this reverting silently --
  `tests/router_v6/test_adapter.py::TestZoneLayersForNet.test_power_class_is_not_zone_eligible`
  asserts `_zone_layers_for_net("+3V3") == []` (and the same for
  `vcc`/`+15V`/`V_BUS_SENSE`) by name. Roughly a dozen other fixtures in
  the same file were deliberately rewritten on 2026-07-28 and again on
  2026-07-30 specifically to stop using `vcc`/`+3V3` as "zone-eligible"
  test data, after two earlier rounds of exactly this kind of drift.

`deterministic/stages/power_plane.py`'s docstring -- the task's other
cited source, and the origin of the "`In2.Cu`: power islands" framing
this task itself is built on -- is not independent corroboration of the
opposite conclusion. It is a design note in a pipeline no production
entry point invokes (`_ground_plane.py`'s own module docstring traces
this: only `deterministic/__init__.py`'s internal assembly calls it,
and `scripts/route_board.py` -- the only `make route` entry point --
never does), and it names nets (`+5V`, `VCC_BOOT`) that do not exist
anywhere in the compiled netlist. That is a sign of drift, not a
currently-validated intent that should outweigh R1's three live,
cross-checked, currently-enforced sources.

**Conclusion, and what I built instead of what was suggested.** Flipping
`Power.routing_strategy` would not have added an `In2.Cu` option
alongside the existing trace-only behavior -- it would have silently
reverted R1/R7 for every production `route_pcb()` call, re-granting these
four rails an *outer-layer* pour too (the exact regression R7's test
exists to catch), and it would have needed `tests/router_v6/test_adapter.py`
and `tests/core/_design_rules_py_oracle.py` changed to stop failing,
which is to say: it would have required un-doing a chunk of a previous,
deliberate fix to make my own change's tests pass. I reverted the
`design_rules.py`/oracle/`_zone_layers_for_net` edits back to their
exact original state (verified: `git diff` on `design_rules.py` and the
oracle is empty) and instead followed the precedent `_ground_plane.py`
already set: **a standalone generator that calls the zone-emission
primitives directly and never goes through `_zone_layers_for_net` at
all.** `_zone_layers_for_net` gained only a docstring addition pointing
here (no behavior change, confirmed: `_zone_layers_for_net("+3V3")` is
still `[]`, `TEMPER_NET_CLASSES["Power"].routing_strategy` is still
`None`, and the full existing test suite for both files passes
unmodified). This means the *live* production `route_pcb()` pipeline's
behavior for these four rails is completely unchanged by this task --
the `In2.Cu` capability exists only via the new opt-in generator/script,
exactly mirroring how `_ground_plane.py`/`scripts/generate_ground_plane.py`
already relate to `gnd`.

`packages/temper-design-bundle/src/parse_engine.rs`'s discarded
layer-role token (the other named root cause) is also not touched, for a
different reason: this sandbox's own tooling notes document
`maturin`/shared-venv rebuilds of pyo3 extensions as fragile under
concurrent worktree use (stale `.so` after a reported-successful
`maturin develop`, a shared venv many parallel agent worktrees point at),
and the standalone-generator route above is sufficient to make `In2.Cu`
expressible and measurable end-to-end without it -- rebuilding a shared
native extension for a second, redundant path to the same capability
was judged not worth that shared-environment risk this run.

---

## 3. Measured results

All measurements: `kicad-cli 10.0.5`, `--all-track-errors --refill-zones`,
identical invocation on both boards, `temper.kicad_pro` + a freshly
regenerated `temper.kicad_dru` staged beside each `.kicad_pcb` (a project
file is required or kicad-cli silently drops every custom-rule violation
-- creepage included). Baseline = the real, current, unmodified
`pcb/temper.kicad_pcb`. "Islands" = the same board with
`generate_power_islands_content` applied for all four rails, written to
a scratch copy only.

### 3a. DRC, 5 repeated samples each side (per-category range, not a
single point -- `creepage` and `clearance` are this project's own
documented chronically-nondeterministic categories, see `AGENTS.md`)

| category | baseline (5 samples) | islands (5 samples) | verdict |
|---|---|---|---|
| `creepage` | 363-365 | 360-361 | **no regression** -- ranges do not overlap; islands board is consistently *lower* |
| `clearance` | 392-393 | 499-501 | regresses, deterministically (+107ish) |
| `tracks_crossing` | 1 (all 5) | 35 (all 5) | regresses, deterministically (+34) |
| `solder_mask_bridge` | 154 (all 5) | 188 (all 5) | regresses, deterministically (+34) |
| `hole_clearance` | 105 (all 5) | 110 (all 5) | regresses, deterministically (+5) |
| unconnected items (DRC's own ratsnest count) | 427 | 383 | **improves** (-44) |

**Why `creepage` does not regress, and why that is the load-bearing
number, not `clearance`.** The task named `creepage` explicitly as the
blocker ("If your islands add creepage, they do not land either");
`clearance` is ordinary electrical spacing, not a mains-safety figure.
Inspecting the violation JSON directly (not just the aggregate count):
every one of the 34 new `tracks_crossing` violations names a power-rail
net (`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE`) crossing a *pre-existing*
other-net `F.Cu` track -- the same "new F.Cu backbone vs. the board's
1193 other-net tracks" tradeoff `_ground_plane.py` already measured and
documented for `gnd`'s own backbone, now confirmed for the power rails
too. `creepage` violations that mention a power-rail net specifically:
50/365 at baseline, 51/360 with islands -- flat, within measurement
noise, not a new safety-relevant crossing this generator introduced.

### 3b. Per-rail pad connectivity
(`pad_connectivity_audit.audit_pcb_file`, the project's declared PRIMARY
completion metric)

| net | pads | before: connected / has copper | after: connected / has copper |
|---|---:|---|---|
| `+3V3` | 51 | 1 / False | **15** / True |
| `vcc` | 13 | 1 / False | **3** / True |
| `+15V` | 10 | 1 / False | **2** / True |
| `V_BUS_SENSE` | 4 | 1 / False | **2** / True |

None reach `fully_connected` -- per `NetConnectivityResult.is_fake_completion`'s
own definition (`has_any_copper and not fully_connected`), all four move
into that bucket, stated plainly rather than rounded up. The generator's
own report explains why: of the MST edges attempted, a large fraction
were dropped rather than rerouted around the keepout/other-rails'-new-copper
obstacle set (`+3V3`: 11 of 50 edges dropped after a one-bend-detour
attempt; `vcc`/`+15V`/`V_BUS_SENSE` fared worse -- 10/12, 7/9, 2/3
dropped respectively, unsurprising since each later rail has strictly
less free `F.Cu` real estate than the one before it, per the priority
ordering in S:1). This is the same MST-forest limitation
`_ground_plane.py` reported honestly for `gnd` (46/86, not 86/86), scaled
across four rails competing for the same layer instead of one net alone
on an empty one.

### 3c. Aggregate zone/copper counts

96 zones -> 156 (60 new: 45 net-owned island polygons across the 4 rails
-- `+3V3` 22, `vcc` 12, `+15V` 8, `V_BUS_SENSE` 3 -- plus 15 pieces of
the one shared HV-keepout rule-area zone, measured directly on the
generator's raw output before any `kicad-cli --save-board` reformatting
touches it). 0 vias belonging to these four nets before -> 70 real drop
vias after (`+3V3` 47, `vcc` 12, `+15V` 7, `V_BUS_SENSE` 4 -- excluding
through-hole-pad skips and unresolved-conflict skips, both reported
honestly by `PowerIslandResult`, not silently absorbed into the via
count).

---

## 4. What this does not do (reported honestly, not silently skipped)

- **Only 4 rails, per this task's own scope.** `deterministic/stages/power_plane.py`'s
  aspirational net list also names `+5V`/`VCC_BOOT`, which do not exist
  on the compiled board -- there was nothing to add for them.
- **`tracks_crossing`/`clearance`/`solder_mask_bridge`/`hole_clearance`
  against pre-existing other-net copper are not fixed** -- the same
  MST-backbone-vs-dense-F.Cu tradeoff `_ground_plane.py` already
  documented and left open for `gnd`. A real router (not a straight-line
  MST + bounded one-bend detour) is the actual fix; out of this task's
  budget, same as it was out of the ground-plane spike's.
- **No `fully_connected` rail.** See S:3b -- real, substantial, measured
  progress from zero, not a claim of completion.
- **`parse_engine.rs`'s discarded layer-role token is not fixed.** See
  S:2's last paragraph.
- **`_zone_layers_for_net` is not generalized.** This was a deliberate
  course correction (S:2), not an oversight -- the live production
  eligibility path for `Power`-class nets is byte-identical to before
  this task.
- **The generated board was validated on scratch copies only.**
  `pcb/temper.kicad_pcb` is provably untouched throughout (`git status
  --short pcb/temper.kicad_pcb` empty). Landing the generated islands
  onto the tracked board is a separate decision requiring a zone-fill +
  full DRC pass against the *current* tracked board state and a
  `power_pcb_dataset/drc_ceiling.json` re-measurement in the same PR
  (`AGENTS.md`'s hard requirement) -- not done here, matching the
  ground-plane precedent's own §7d.

---

## Sources

- `packages/temper-placer/src/temper_placer/router_v6/_power_islands.py` (new)
- `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py` (read-only reuse, unmodified)
- `packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py` (`_zone_layers_for_net`, docstring-only change)
- `packages/temper-placer/src/temper_placer/core/design_rules.py` (`Power` entry -- confirmed unchanged, `git diff` empty)
- `tests/router_v6/test_adapter.py::TestZoneLayersForNet` (R1/R7's enforced regression coverage)
- `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md` (R1/R7, KD1)
- `docs/evidence/2026-07-28-pour-strategy-audit.md` (Task 1's independent DELETE verdict for Power/GateDrive)
- `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` (SS3.4/3.6-3.8, per-net trace-width+decoupling specs)
- `docs/evidence/2026-08-11-keepout-before-pour-spike.md` (#1022/#1033, the `In1.Cu`/`gnd` precedent this task mirrors)
- `AGENTS.md` (creepage/clearance nondeterminism convention; the noise-headroom reasoning this doc's 5-sample-range methodology follows)
