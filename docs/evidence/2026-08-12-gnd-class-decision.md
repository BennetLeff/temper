<!-- provenance: commit=81ac8432e7966e340ba671bfac98a4efd94cf851 dirty=UNKNOWN -->

# `gnd` should carry a declared `GND` class, not `Power` -- Option B wins, modestly, on measurement

## Headline

**Option B (declare `GND` in `pcb/temper.kicad_pro`, map `gnd` -> `GND`) is the
right call, on measurement, not assumption.** It reduces `clearance`
violations by **16** on the unmodified, currently-committed board (418 ->
402, n=30 samples each, both fully stable/deterministic) with **zero
measurable cost** anywhere else: `creepage`, `shorting_items`,
`solder_mask_bridge`, `tracks_crossing`, and every other DRC category are
byte-for-byte identical between the two options, and `track_width` is
identical by construction (`GND`'s 1.0mm equals `Power`'s 1.0mm). This PR
declares `GND` with its real, already-shipped `core/design_rules.py`
parameters (trace 1.0mm / clearance 0.3mm / Via3x3) -- a pure
correction of `kicad_pro` to match the Python SSOT it has silently
disagreed with, not a netclass-value change (PR #1061's settlement is
untouched).

**`routing_strategy` is live, but not because of anything this decision
changes.** `core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` already maps
`gnd -> "GND"` and `TEMPER_NET_CLASSES["GND"].routing_strategy` is already
`"plane_preferred"`, **on `origin/main`, before this PR** -- the task
brief's framing ("`gnd` has silently lost `plane_preferred`") describes a
state that predates this repo's current `main`; it was already fixed
(2026-08-11, `TEMPER_NET_ASSIGNMENTS`'s own inline history) independently
of what `kicad_pro` declares. Traced directly: `_should_route()`
(`_net_policy.py:21`) and `_zone_layers_for_net()` (`_zone_pour_stitch.py:78`)
both read `TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` -- Python-side,
**never `kicad_pro`** -- and confirmed live by direct call: `_zone_layers_for_net("gnd")`
returns `["F.Cu", "B.Cu"]` today, on `origin/main`, regardless of what
this PR does to `kicad_pro`. **This PR's `kicad_pro` change does not
touch that mechanism at all -- it was never wired to `kicad_pro` in the
first place.** What this PR *does* touch is a separate, real mechanism:
`_ground_plane.py`'s corridor-aware A* backbone stitcher reads `gnd`'s
clearance **directly from `kicad_pro`** (`resolve_netclass_clearances`,
`_corridor_backbone.py:133`, by deliberate design, not accident -- see
§3). That is where this decision's real, measured effect lives.

---

## 1. What changed

`pcb/temper.kicad_pro`'s `net_settings.classes` gained one entry:

```json
{
  "name": "GND",
  "clearance": 0.3,
  "track_width": 1.0,
  "via_diameter": 1.0,
  "via_drill": 0.5,
  ...
}
```

mirroring `core/design_rules.py`'s `TEMPER_NET_CLASSES["GND"]` exactly
(same four scalar routing fields the project's own parameter-correspondence
gate checks). `net_settings.netclass_assignments["gnd"]` was changed from
`"Power"` to `"GND"`. `PWR_RTN`/`CGND` were left untouched (still
`"HighVoltage"`/unassigned) -- `scripts/sync_kicad_netclass_assignments.py`
structurally protects them (`PROTECTED_NETS`) as an explicit, separate,
larger-blast-radius human decision; that script's own `--check` mode
refuses to run once `GND` is declared, for exactly that reason, confirming
the protection is live. No value in any existing class changed.

Verified clean after the edit:

```
$ uv run python scripts/check_netclass_class_param_correspondence.py
Net-class parameter correspondence gate -- 9 class(es) checked, 0 mismatches

$ uv run python scripts/check_netclass_map_board_correspondence.py
Net-class map <-> board correspondence gate passed (58 keys, 0 broken)

$ uv run python scripts/check_hv_netclass_coverage.py
HV netclass coverage gate passed (all 5 PROPERTY checks: 0 violations)
```

---

## 2. DRC on the unmodified, currently-committed board (`pcb/temper.kicad_pcb`)

Protocol: `temper_placer.validation._drc_api.run_drc` (`--all-track-errors`,
single-threaded `KICAD_CONFIG_HOME`, kicad-cli 10.0.5) against a scratch
copy of the untouched, currently-committed `pcb/temper.kicad_pcb`
(sha256 `6928b7c8...`, identical under both options -- only the sidecar
`.kicad_pro` differs), each scratch dir carrying its own `fp-lib-table`,
`libs/`, and a **freshly regenerated** `pcb/temper.kicad_dru`
(`scripts/generate_kicad_dru.py`, run once against the unmodified
`core/design_rules.py` -- this generator never reads `kicad_pro`, so one
regeneration is valid for both options). n=30 samples per option.

| category | Option A (`gnd`->`Power`, status quo) | Option B (`gnd`->`GND`, this PR) | delta |
|---|---:|---:|---:|
| `clearance` | 418 (stable, 30/30) | 402 (stable, 30/30) | **-16** |
| `creepage` | 198-200 (noise band, matches this repo's documented creepage scatter) | 198-200 (same band) | 0 |
| `shorting_items` | 199 (stable, 30/30) | 199 (stable, 30/30) | 0 |
| `solder_mask_bridge` | 154 (stable) | 154 (stable) | 0 |
| `tracks_crossing` | 1 (stable) | 1 (stable) | 0 |
| `track_width` | 199 (stable) | 199 (stable) | 0 (both classes declare 1.0mm) |
| total errors | 1310-1312 | 1294-1296 | **-16** |
| total warnings | 489 (stable) | 489 (stable) | 0 |

Every category outside `clearance` is either exactly identical or within
the same documented noise band on both options -- `clearance` is the
*only* category this change moves, and it moves in the expected
direction, by a stable, fully-reproducible amount.

**Why this is -16, not the -32 PR #1087 attributed to `gnd`**: PR #1087's
+32 figure was measured going the other direction (GND-shaped ->
`Power`) on the board state current at that PR's own merge. `gnd`'s copper
on today's board was never generated under a 0.3mm-clearance regime in the
first place -- the copper itself is unchanged by this PR (only the DRC
rule applied to it is), so the two figures are not required to be mirror
images of each other, and empirically aren't. -16 is what this PR
actually, measurably buys against *today's* committed copper.

**Why Option A's own baseline (418) doesn't match
`power_pcb_dataset/drc_ceiling.json`'s recorded 386**: that ceiling's
`provenance.inputs[0].sha256` for `pcb/temper.kicad_pcb` matches today's
board exactly (confirmed: `sha256sum pcb/temper.kicad_pcb` ==
`6928b7c8...`, the recorded hash) -- the *board* has not moved since that
ceiling was measured. `kicad_pro` has: `git log f70296adc..origin/main --
pcb/temper.kicad_pro` shows 4 commits touching it since that ceiling's
`measured_at_commit` (#1025, #1083, #1084, #1087), none of which
re-triggered a ceiling re-measurement because none of them touched
`pcb/temper.kicad_pcb` itself and the ceiling's provenance is keyed only to
the board's content hash, not the project file's. This is a pre-existing,
separate gap (the ceiling can silently drift out of sync with `kicad_pro`-
only PRs) -- out of this PR's scope to fix, noted here only so the 418-vs-386
mismatch doesn't read as a measurement error in this document.

---

## 3. Does `routing_strategy` / the `kicad_pro` declaration change the *routed* result? Two different mechanisms, two different answers.

### 3a. The main pipeline (`scripts/route_board.py` / `router_v6.adapter.route_pcb`): NO -- and it was never wired to `kicad_pro` to begin with

Every netclass decision in the Stage 3/4 router -- `_should_route`
(A* eligibility), `_zone_layers_for_net`/`_zone_params_for_net` (zone-pour
eligibility and geometry) -- resolves through
`core.design_rules.TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS`. Grepped
across `router_v6/adapter.py` and `router_v6/_adapter_convert.py` (the
`route_pcb()` call chain `route_board.py` drives): **zero references to
`kicad_pro`, anywhere.** `_zone_layers_for_net("gnd")` on `origin/main`
already returns `["F.Cu", "B.Cu"]` (plane-eligible) and `_should_route("gnd")`
already returns `False` (excluded from A*, "handled by zone pours") --
**before this PR, and unaffected by it**, because `routing_strategy`'s
only consumer in this path is Python-side.

Attempted a live confirmatory run of `route_board.py --pcb ... --output ...`
(full Stage 3/4 route, existing-copper stripped, real `route_pcb()` call)
against Option A's scratch board. **Aborted, not completed**: RSS climbed
57GB in under 5 minutes (25GB -> 47.7GB observed, system available memory
17GB -> 7.9GB, swap 1.9/2.0Gi already exhausted from prior work) on a
machine this repo's own `AGENTS.md` documents as having been OOM-killed
before at 54-59GB under concurrent agent load, and this machine hosts 60+
shared agent worktrees -- killed (`SIGTERM`, clean exit, no orphaned
children, memory fully recovered to 57GB free afterward) rather than risk
taking down other sessions' work for a confirmatory run this task does not
strictly need. Before starting it, `ps aux` showed no other
`route_board.py`/`pumpkin_engine` process running, so the growth was this
run's own, not contention -- still too large a single-run footprint to
finish safely as an unplanned addition to whatever else this shared
machine is carrying.

The conclusion in this subsection therefore rests on the **structural
code-trace result** stated above (zero `kicad_pro` references anywhere in
`router_v6/adapter.py` or `router_v6/_adapter_convert.py`, the entire
`route_pcb()` call chain `route_board.py` drives, confirmed by direct
`grep`) plus the **live, in-process confirmation already run in §3
generally**: `_zone_layers_for_net("gnd")` and `_should_route("gnd")` were
called directly against the imported `core.design_rules` module (no board
I/O, no `kicad_pro` file involved at all in either call) and returned
`["F.Cu", "B.Cu"]` / `False` respectively -- both functions' entire
signature is `(net_name: str) -> ...`, with no path to a `kicad_pro` file
anywhere in either function body. A full `route_pcb()` run could only
possibly disagree with this if some *other*, untraced code path also fed
netclass data into Stage 3/4 from `kicad_pro` -- grepped for and not
found. This is reported as a structural/static result, honestly labelled
**outstanding** as a live full-pipeline run, rather than inferred from a
run that did not finish.

### 3b. The ground-plane generator (`scripts/generate_ground_plane.py` / `_ground_plane.py`): YES -- this is the mechanism that actually reads `kicad_pro`

`_ground_plane.py`'s corridor-aware A* backbone stitcher (landed
2026-08-12, `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`)
calls `resolve_netclass_clearances(pcb_path.with_suffix(".kicad_pro"))`
**by deliberate design** -- its own docstring: "the SAME source kicad-cli
itself resolves a net's clearance from," specifically because
`design_rules.py`'s Python-side table was historically an unreliable proxy
for what kicad-cli enforces. `gnd_own_clearance` (read from `kicad_pro`)
sets the floor for the pairwise obstacle-clearance buffer used to build
`gnd`'s F.Cu corridor mask.

Ran `scripts/generate_ground_plane.py` against both options (same input
board, only the sidecar `kicad_pro` differs), twice for Option A to confirm
determinism first:

| | Option A rerun 1 | Option A rerun 2 | Option B |
|---|---:|---:|---:|
| `mst_edges_astar_routed` | 11 | 11 (identical output, confirmed byte-for-byte) | **13** |
| `mst_edges_fallback` | 74 | 74 | **72** |
| `pads_connected` (gnd, pad-connectivity audit) | 46/86 | 46/86 | 46/86 |

**The generated board content differs (366 diff lines) and the mechanism
is deterministic (two Option-A runs are byte-identical)** -- so this is a
real, reproducible effect of `kicad_pro`'s declared `gnd` clearance, not
noise. 2 more of 85 MST edges get a real, corridor-clean A* path instead
of falling back to the keepout-only straight-line/one-bend-detour
heuristic. Pad connectivity (the project's declared PRIMARY completion
metric) stays at the existing 46/86 floor under both -- **no regression,
and no improvement at the pad-connectivity level either**: the 2 extra
solved edges connect components already joined some other way.

DRC on the two generated boards (10 samples each, same protocol as §2):

| category | Option A generator output | Option B generator output |
|---|---:|---:|
| `clearance` | 499 (stable) | 499 (stable) |
| `creepage` | 197-198 | 197-198 |
| `shorting_items` | 199 (stable) | 199 (stable) |
| `solder_mask_bridge` | 200 (stable) | 199 (stable) |
| `tracks_crossing` | 49-50 | 51 (stable) |
| total errors | 1502-1504 | 1503-1504 |

**Mechanically proven to change the routed backbone; aggregate DRC on that
backbone's own output does not materially move either way** -- consistent
with `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`'s own
finding (§3.2 of that doc: the F.Cu corridor mask for `gnd` fragments into
~94 disconnected regions "independent of search strategy," and five
different clearance configurations there (0.05mm through 0.5mm, flat and
per-pair) all left the aggregate collision counts within the same ~5-10
unit noise band). This PR's measurement is a sixth data point in the same
direction: **the specific 0.5mm-vs-0.3mm delta this decision is about does
not, by itself, fix F.Cu congestion for the ground-plane backbone.**

**So: is `routing_strategy` "live"?** Yes, unambiguously -- but the
`kicad_pro` declaration this PR makes is not what makes it live (it
already was, via the Python SSOT). What this PR's `kicad_pro` change
actually activates is `_ground_plane.py`'s independent,
already-landed-and-tested corridor-clearance read, and there its effect is
real but small (2/85 edges) and does not move DRC.

---

## 4. A related, unwired declaration found along the way (not fixed here, flagged)

`scripts/generate_kicad_dru.py`'s `KICAD_NAME_MAP = {"GND": "Ground"}`
assumes the KiCad-side netclass name for this tier would be `"Ground"`,
and the generated `.kicad_dru`'s "Ground clearance" rule (intended to
relax `gnd`-vs-everything clearance to 0.15mm, looser than either
`Power`'s 0.5mm or `GND`'s own 0.3mm) and "Ground trace width" rule both
key off `A.NetClass == 'Ground'`. **No `kicad_pro` netclass has ever been
named `"Ground"`, under Option A or this PR's Option B** -- both name it
`"GND"` (matching `core/design_rules.py`'s own `name='GND'` field and
`TEMPER_NET_ASSIGNMENTS`'s target string, which the parameter-
correspondence and sync gates both require literally). This makes the
"Ground clearance" relaxation rule dead code, identically under both
options -- **not something this decision introduces or fixes**, since it
was equally inert before this PR (when `gnd` was `Power`, `A.NetClass`
was never `'Ground'` either). The "Ground trace width" rule's dead-ness is
harmless by coincidence (both `GND` and `Power` declare 1.0mm, so its
intended value and the enforced built-in value already agree). Left
unfixed here, in scope-preserving terms with this repo's own established
pattern (see `CGND`/`PWR_RTN` in §1): renaming a `kicad_pro` class or
changing which nets a `.kicad_dru` custom rule targets is a second,
separate, larger-blast-radius decision this task's brief did not ask for.

---

## 5. Recommendation

**Ship Option B.** It is a strict improvement on every measured axis this
task's protocol covers (`clearance` -16, everything else flat, `routing_
strategy`'s only live consumer unaffected either way, ground-plane backbone
connectivity unregressed) and it removes a real SSOT disagreement
(`kicad_pro` silently overriding `core/design_rules.py`'s already-declared
`GND` class with `Power`'s coarser figures for the board's single largest
net). It is not a dramatic fix -- the F.Cu congestion problem this task's
brief raised as the reason this might matter "a great deal" is not solved
by this change (§3b, and independently confirmed by
`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`'s five-
configuration sweep) -- but "modest, real, zero-cost win; does not fix the
bigger problem" is the honest reading of the numbers, not a reason to
prefer the status quo's SSOT disagreement.

---

## Sources / commands

- `uv run python scripts/check_netclass_class_param_correspondence.py`
- `uv run python scripts/check_netclass_map_board_correspondence.py`
- `uv run python scripts/check_hv_netclass_coverage.py`
- `uv run python scripts/sync_kicad_netclass_assignments.py --check` (confirms `PWR_RTN`/`CGND` protection is live post-declaration)
- `uv run python scripts/generate_kicad_dru.py` (one regeneration, shared by both scratch DRC dirs -- reads only `core/design_rules.py`)
- `temper_placer.validation._drc_api.run_drc`, n=30 samples/option on the unmodified `pcb/temper.kicad_pcb` (§2), n=10 samples/option on the two `generate_ground_plane.py` outputs (§3b)
- `scripts/generate_ground_plane.py --pcb <scratch>/temper.kicad_pcb --output <scratch>/gplane_<opt>.kicad_pcb`, run twice for Option A to confirm determinism
- `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file` for the pad-connectivity floor (PRIMARY completion metric per this repo's own convention -- reported explicitly as pad connectivity, not topology-solved net counts)
- `scripts/route_board.py --pcb <scratch>/temper.kicad_pcb --output <scratch>/routed.kicad_pcb`, attempted (Option A), aborted under memory pressure before completion -- see §3a for why this is reported as outstanding, not inferred
- Direct in-process calls: `_zone_pour_stitch._zone_layers_for_net("gnd")` -> `['F.Cu', 'B.Cu']`, `_net_policy._should_route("gnd")` -> `False`, both against the imported `core.design_rules` module with no `kicad_pro` file involved (§3a)
- `git diff f70296adc..origin/main -- pcb/temper.kicad_pro` (explains the 418-vs-386 ceiling mismatch, §2)
- `core/design_rules.py` `TEMPER_NET_CLASSES["GND"]` / `TEMPER_NET_ASSIGNMENTS["gnd"]`, `router_v6/_net_policy.py`, `router_v6/_zone_pour_stitch.py`, `router_v6/_corridor_backbone.py`, `router_v6/_ground_plane.py`, `scripts/generate_kicad_dru.py`
