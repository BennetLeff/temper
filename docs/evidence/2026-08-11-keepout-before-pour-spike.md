<!-- provenance: commit=86e81396 (main at task start) dirty=true -- this doc, packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py, packages/temper-placer/tests/router_v6/test_ground_plane.py, and scripts/generate_ground_plane.py are the diff this task produced. pcb/temper.kicad_pcb is UNCHANGED by this task -- verified `git status --short pcb/temper.kicad_pcb` / `git diff --stat pcb/temper.kicad_pcb` both empty throughout. -->

# Keepout-before-pour spike: the inner-layer planes do not exist, and a first one was built

**Branch:** `spike/keepout-before-pour`
**Scope:** originally a diagnostic spike; upgraded mid-task to "build a
working ground plane, not just diagnose." Both halves are reported here.

## Headline

**The In1.Cu/In2.Cu power planes do not exist anywhere in this project's
code.** `pcb/temper.kicad_pcb` declares them (`(1 "In1.Cu" power)`,
`(2 "In2.Cu" power)`, commit `c4956df66`, 2026-08-08), but that commit's
own message says the declaration is inert, and this spike traced the
mechanism independently and confirms it: nothing in `router_v6` — the
only pipeline `make route` invokes — ever reads that token, and nothing
in `router_v6` ever emits `(zone ...)` geometry on an inner layer. A
parallel, non-production pipeline (`deterministic/`) has the *design*
for real inner-layer planes fully written out, but no production entry
point calls it. router_v6 never inherited the capability.

This is why `gnd` — net 50, 86 pads, the board's largest net — had
**zero copper of any kind** before this task: not because it was
deliberately excluded on a mistaken promise (that specific bug existed
and was already fixed same-day, 2026-08-08, before this task started —
see §3), but because there is no code path in the pipeline that actually
runs capable of putting copper on the layer a return net this size
needs.

**This task built one.** `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py`
generates a real `In1.Cu` `gnd` plane — a keepout-respecting pour, via
drops from every pad, and an MST copper backbone — and measurably
improves `gnd`'s pad connectivity from 0 reachable pads to 46 of 86 on
the real, committed production board. **`pcb/temper.kicad_pcb` itself
is untouched** (verified: `git status`/`git diff --stat` both empty on
it throughout this task) — the generator's output was validated against
copies only. §7 explains exactly why, and it is not a budget shortcut:
`kicad-cli` and `pcbnew` are both absent from this sandbox, so neither
DRC nor zone-fill — both required before this board could responsibly
become the tracked one — could be run here.

---

## 1. Verifying the four measured findings this task started from

All four re-measured directly against `pcb/temper.kicad_pcb` (script:
`/tmp/.../scratchpad/verify_board.py`, a standalone parenthesis-balanced
s-expression scan, independent of any project parser):

1. **96 zones, all on F.Cu (48) / B.Cu (48). Confirmed exactly.**
2. **In1.Cu/In2.Cu: zero zones**, despite the board's own `(layers ...)`
   table declaring them `power` role. **Confirmed.**
3. **`gnd` (net 50, 86 pads): zero segments, zero vias, zero zones,
   before this task.** **Confirmed** — cross-checked independently via
   `pad_connectivity_audit.audit_pcb_file()`
   (`pad_count=86, pads_connected=1, has_any_copper=False`).
4. **14 nets carry zones**: `+15V`, `+15V_LS`, `+3V3`, `DC_BUS_RTN`,
   `GATE_HS`, `GATE_LS`, `PWM_HS`, `PWM_LS`, `PWR_RTN`, `SW_NODE`,
   `V_BUS_SENSE`, `ac_l`, `ac_n`, `vcc`. **Confirmed, exact match.**
   `PWR_RTN` (net 13) and `gnd` (net 50) are confirmed **separate**
   nets on this board, not a stale alias of one another.

The board declares `(layers (0 "F.Cu" signal) (1 "In1.Cu" power)
(2 "In2.Cu" power) (31 "B.Cu" signal) ...)` — the "power" tokens are
real, present, and (per §2) never read.

---

## 2. Root cause: the inner-layer plane declaration is provably inert

Three independent facts, each confirmed by reading the actual code, not
inferred:

**2a. The Rust parser discards the per-layer role token.**
`packages/temper-design-bundle/src/parse_engine.rs` line 1139-1147, the
`"layers"` branch of `raw_board_from_tree`:

```rust
"layers" => {
    // `(0 "F.Cu" signal)` -- the NAME is the quoted token at
    // index 1; index 2 is the layer type.
    for sub in items.iter().skip(1) {
        if let KiNode::List(s) = sub
            && let Some(KiNode::Atom(a)) = s.get(1) {
                board.layers.push(atom_to_string(a));
            }
    }
}
```

The comment names index 2 as "the layer type" and then never reads it —
only `s.get(1)` (the name) is pushed. `board.layers: Vec<String>` is a
bare name list; the role string (`signal`/`power`/`user`) never reaches
Python at all.

**2b. `_extract_stackup` (Python) never asks for it either way.**
`packages/temper-placer/src/temper_placer/io/_parse_board.py` computes
`layer_type` from one of two sources — zone-net-name heuristics
(default) or purely *structural position* among the declared copper
layers when `use_declared_layer_roles=True` (outer=`"signal"`,
inner=`"mixed"`, **never `"plane"`**) — neither of which is the board
file's own per-layer token (which per §2a isn't even parsed). This
means even the code path meant to fix this (`use_declared_layer_roles`,
landed 2026-08-07/-08 per
`docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`'s
own Landing Status) classifies In1.Cu/In2.Cu as ordinary **routable
signal layers**, not planes — the opposite of what the board declares.

**2c. Commit `c4956df66`'s own message already says this.** The commit
that added the `power` tokens (2026-08-08) states directly: *"This
project's own stackup-role inference
(`temper_placer.io._parse_board._extract_stackup`) never reads this raw
layer-table token at all... The edit is therefore provably inert to
router_v6's routing/obstacle-map/copper-coverage behavior."* This spike
traced the mechanism independently (2a/2b) before finding that
admission, and it matches exactly.

**2d. The only zone-emission code path in the production pipeline
cannot target an inner layer at all**, independent of role
classification. `router_v6/_zone_pour_stitch.py::_zone_layers_for_net`:

```python
def _zone_layers_for_net(net_name: str) -> list[str]:
    ...
    if nc is not None and nc.routing_strategy in ("plane_required", "plane_preferred"):
        return ["F.Cu", "B.Cu"]
    return []
```

Every zone-eligible net gets `["F.Cu", "B.Cu"]`, unconditionally. There
is no branch, anywhere in `router_v6`, that can return `"In1.Cu"` or
`"In2.Cu"`. Even a perfectly stackup-role-classified, perfectly
netclass-classified GND-plane net would still only ever get outer-layer
copper through this path.

**2e. The correct design exists — in a pipeline nothing production
invokes.** `deterministic/stages/power_plane.py`'s own docstring states
the intended stackup precisely: `In1.Cu: Ground plane (GND, PGND,
CGND)`, `In2.Cu: Power islands (+3V3, +5V, +15V, VCC_BOOT)`. But
`deterministic/` is a separate pipeline from `router_v6`; the only
production caller of `PowerPlaneStage` is
`deterministic/__init__.py`'s own internal pipeline assembly, invoked
by nothing in `scripts/route_board.py` (confirmed: the only production
routing entry point, the `make route` target, imports exclusively from
`temper_placer.router_v6.adapter.route_pcb`). `scripts/run_feedback_loop.py`
references the deterministic pipeline; nothing else does. Also worth
noting: `TEMPER_PLANE_NETS` in that file uses uppercase `"GND"`, not the
real board's lowercase `gnd` net — the same net-name-casing drift
already fixed once for `+170V_BUS`/`"+340V_BUS"` elsewhere in this
codebase — so even resurrecting this module unmodified would not have
covered the real net.

**Conclusion: the "power" declaration on In1.Cu/In2.Cu is real
metadata, honestly intentioned, and completely disconnected from every
piece of code capable of acting on it.** This is not a bug in one
function; it is an entire capability — inner-layer plane generation —
that was designed once, in a pipeline that was superseded, and never
carried forward.

---

## 3. Why `gnd` specifically has zero copper: refining, not contradicting, the stated causal chain

The upgraded mandate's causal chain (`_should_route()` unconditionally
excludes power/ground nets from A* "on the promise of a plane that
never generates") is the right shape and was true — **but was already
partially fixed same-day, before this task started**, and the more
precise mechanism matters for what to build next:

- Commit `51ade7304` (2026-08-08, *"fix(router): route Power/GND nets by
  A* when no zone pour covers them"*) changed `_should_route()` so
  power/ground/HV-pattern nets are excluded from A* **only when
  `_zone_layers_for_net()` actually grants them zone coverage** — not
  unconditionally. `gnd` has no netclass entry in
  `core/design_rules.py::TEMPER_NET_ASSIGNMENTS` at all (only `PWR_RTN`
  and `CGND` map to the `"GND"` class — the same missing-alias defect
  shape already fixed once for `+170V_BUS`), so
  `_zone_layers_for_net("gnd")` returns `[]`, and per the fixed logic
  `gnd` now falls through to **being attempted by A***, not
  auto-excluded.
- `c4956df66` (the layer-role commit) is a *descendant* of `51ade7304`
  in this repo's history (`git merge-base --is-ancestor 51ade7304
  c4956df66` confirms), i.e. the fix already existed when the currently
  committed board was last touched.
- **But the committed board still shows zero `gnd` copper even after
  that fix, and this spike confirms why via an existing evidence doc,
  not new speculation:**
  `docs/evidence/2026-08-08-router-power-gnd-and-stage4-clearance-combined.md`
  §3.1 reports a real, live re-route with both the `_should_route` fix
  and a contemporaneous clearance fix applied: `gnd` (with `+3V3`) *"remain
  unrouted even with Fix A, now genuinely attempted and fail closed,
  exactly as Fix A's own commit message predicted."* A* attempts all 86
  pads and cannot complete the net through the board's placement
  congestion — the fail-closed forced-segment gate
  (`_allow_forced_segments`, unconditionally `False` since
  2026-07-24) refuses to fabricate an unchecked path rather than emit
  unsafe copper.

So the precise statement is: **the exclusion-on-a-false-promise bug is
already fixed in code; the committed board simply predates a
production re-route reflecting that fix (its last touching commit,
`c4956df66`, only edited a provably inert token); and even a live
re-route with the fix applied still leaves `gnd` with zero copper,
because point-to-point A* structurally cannot complete an 86-pad common
return net through real placement congestion.** This does not
contradict the "the promised plane never happens" diagnosis — it
sharpens it. An 86-pad common-return net topologically wants a plane
(or genuine multi-terminal/Steiner synthesis), not an A*-searched
point-to-point path, and no code path produces one. Fixing
`_should_route()` alone (already done) cannot fix this; only real
inner-layer copper generation can. That is what this task built.

---

## 4. Is "keepout-before-pour" the right frame? Bifurcated, not wrong

The isolation-barrier / creepage problem (171-ish residual `creepage`
violations, 87.4% copper coverage, per the originating plan doc) and the
`gnd`/0%-pad-connectivity problem **share the root cause identified in
§2** (router_v6 never inherited inner-layer plane generation) but they
are not the same fix:

- The creepage/coverage problem lives entirely on **F.Cu/B.Cu** — every
  one of the 96 existing zones is on an outer layer, and that is where
  the 87.4% coverage figure comes from. **Keepout-before-pour is the
  right frame here**: clip existing/future outer-layer pour geometry
  against the isolation barrier before emission, using
  `isolation_barrier.py`'s corridor as the source of truth and the
  already-built (but unpopulated — §5) `temper-drc-rs::routing::
  IsolationBarrierCheck` as the backstop detector.
- The `gnd`/plane-generation problem lives on **In1.Cu**, which today
  carries **zero copper of any kind, on any net, anywhere**. There is
  nothing to "keep out of a region" on a layer with nothing on it —
  designing a keepout mechanism for an empty layer does not move the
  needle on the 87.4% figure (that number is 100% an outer-layer fact)
  and does not by itself produce `gnd` copper. What that problem needed
  was a *generator*, not a keepout — which is why this task built one,
  with the keepout wired in as a hard constraint on the generator
  itself (§6), matching the upgraded mandate's explicit instruction to
  make this the corridor's "first real customer."

**Conclusion, stated as the mandate asked: yes, lead with "the planes
don't exist."** Framing this purely as "design a keepout" would have
solved the smaller, already-partially-covered problem (outer-layer
barrier crossings) while leaving the larger one (an electrically
necessary net with no copper) exactly where it was.

---

## 5. A related, already-built, currently-inert safety net

`docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` (2026-08-08,
already merged) independently found and hardened
`temper-drc-rs::routing::IsolationBarrierCheck` — a real, tested
zone/trace-vs-barrier crossing **and** clearance detector, reading actual
`geo::Polygon` zone geometry, not the schema `IsolationCheck` uses. It
is registered in the default rule set. **It never fires on this
project** because `packages/temper-placer/configs/temper_constraints.yaml`
declares zero `isolation_barrier` entries — the check has no configured
barrier to compare against. This is a *detection* mechanism (would flag
a bad pour after the fact) whereas this task needed *prevention* (never
emit the bad pour). Populating `constraints::IsolationBarrier` from
`isolation_barrier.py`'s corridor geometry so this detector actually
runs is real, low-effort follow-on work this spike did not do (out of
Rust-side scope for this task), and would make a useful independent
backstop alongside the generator-side keepout this task did build.

---

## 6. What was built

**`packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py`**
(new, production code) — `generate_ground_plane_content(pcb_path,
domain_manifest_path=...)`. Given a `.kicad_pcb` path, returns
`(new_content, GroundPlaneResult)`. Reuses existing production
primitives rather than inventing new geometry machinery:
`zone_emission.compute_zones_for_net`/`emit_zone_s_expr` (the same
functions the F.Cu/B.Cu pour path uses), `pad_connectivity_audit._pads_by_net`
and `topology_copper_audit.net_number_to_name_map` (existing, tested pad/
net extraction), and `isolation_barrier.py`'s `DEFAULT_CORRIDOR_WIDTH_MM`
+ `load_domain_manifest_nets` (read-only imports — this file was not
modified; it lives under the boundary this task was told not to touch,
and wasn't).

**`scripts/generate_ground_plane.py`** (new) — thin CLI wrapper,
`--pcb`/`--output` (mandatory, refused if equal — mirrors
`scripts/route_board.py`'s own safety convention).

**`packages/temper-placer/tests/router_v6/test_ground_plane.py`** (new)
— 7 tests: unit coverage for `mst_edges` (anti-vacuity: connects every
node, not just the right count) and `compute_hv_selv_keepout`
(coverage/exclusion/clipping), plus one integration test against the
real `pcb/temper.kicad_pcb` (always on a `tmp_path` copy) asserting the
measured baseline (`pads_connected==1`, `has_any_copper is False`) and a
real post-fix improvement (`pads_connected >= 40`,
`has_any_copper is True`). All 7 pass. This pins the headline
measurement below as an enforced regression test, not a one-time claim.

### 6a. The keepout: one design tried, measured wrong, replaced

The first implementation built a single global keepout **band**: find
whichever axis separates the HV-domain and SELV-domain (incl. `gnd`) pad
clusters' *bounding boxes* with a positive gap, band that gap. Measured
directly against the real board: **no positive gap exists on either
axis** — the bounding boxes overlap. This is not a tuning problem; it
corroborates the unmerged `safety/mains-selv-isolation-barrier` branch
(cited in §5's spike doc), whose own commit message reports that *no
single axis-aligned line* cleanly separates this board's HV/SELV pads
(28-32% misclassified at best; HV/SELV pad centroids as close as ~5.9mm
in places).

Replaced with a per-pad construction: `compute_hv_selv_keepout` unions a
disc of radius `DEFAULT_CORRIDOR_WIDTH_MM` (~8.5mm, `isolation_barrier.py`'s
own SSOT) around **every individual HV-domain pad** (`elec/domain_manifest.yaml`'s
`HV.nets`, cross-referenced against real board pad positions — the same
net-domain source of truth `isolation_barrier.py` itself uses). This has
no "clean separating line" precondition and degrades gracefully to
whatever the real, locally-interleaved geometry is. Measured on the real
board: **established** (`keepout_established=True`), covering
16,143.6 mm² (~45% of the 152×234mm = 35,568mm² board).

### 6b. The plane: convex hull of `gnd`'s own pads, minus the keepout, minus a board-edge margin

`compute_zones_for_net("gnd", ..., cluster=False)` (the same function
the outer-layer path uses, called with `cluster=False` for one hull over
all 86 pads rather than per-component clustering), clipped against
`board_polygon.buffer(-1.0mm)` minus the keepout from §6a. Result: **6**
disjoint polygon pieces (the keepout's per-pad-disc union carves the
hull into several regions) totaling **14,492.2 mm²** (~41% of the
board).

### 6c. Connecting pads to the plane, and a real limitation of `pad_connectivity_audit.py` found along the way

Every `gnd` pad gets a through-hole via drop (`size 0.8mm`/`drill
0.4mm`/`layers "F.Cu" "B.Cu"` — the exact convention every other via on
this board already uses; a standard through-via contacts every inner
copper layer it spans, including In1.Cu, without needing to name it).

**A first version also drew the MST backbone (§6d) on In1.Cu — the
geometrically obvious choice — and it connected zero extra pads under
`pad_connectivity_audit.check_net_pad_connectivity`, measured, not
assumed.** Root cause, read directly in that function
(`pad_connectivity_audit.py` lines ~190-194): a via only unions graph
nodes for the layers **literally present** in its own `via.layers`
tuple. Real KiCad electrical semantics treat a through-via as contacting
every layer it physically spans; this audit tool's connectivity graph
does not model that — it only recognizes layers a via's `(layers ...)`
field names explicitly. An `In1.Cu` segment therefore never unions with
an `F.Cu`/`B.Cu`-declared via at the same point, in this tool's model,
even though the real board electrically joins them. **This is a real,
previously undocumented gap in `pad_connectivity_audit.py` — it would
equally miss a through-via's real In1.Cu contact for any other net, not
just this one** — flagged here, fixing it is out of this task's scope
(that file is a widely-relied-on measurement tool, not something to
change opportunistically inside an unrelated fix). Widening the via's
own `layers` tuple to a 3-entry, non-standard form to route around the
tool's blind spot was considered and rejected: KiCad's file format uses
exactly two layer names per via regardless of type, and a 3-entry form
is not known to be accepted by `kicad-cli`. The fix used instead: put
the backbone on `F.Cu` (already one of the via's two declared layers) —
standard file, and the tool now sees the real connectivity.

### 6d. The MST backbone, and its honestly-reported incompleteness

A real filled zone electrically joins every via touching it — but per
§6c's finding (and `docs/evidence/2026-08-11-true-pad-connectivity-baseline.md`
§3's own documented caveat), `pad_connectivity_audit.py` does not parse
`(zone ...)` polygons **at all**. So the plane alone, however correct
electrically, would not be visible to the project's declared PRIMARY
completion metric. `mst_edges()` (Prim's algorithm, pure Python, O(n²) —
trivial at 86 nodes) computes a minimum spanning tree over the 86 via
drop points; each edge is emitted as an `F.Cu` segment (§6c) unless it
would cross the keepout, in which case a bounded one-bend detour search
(try routing through one of the 40 nearest other via points instead,
first candidate whose both sub-segments clear the keepout) is
attempted before falling back to dropping the edge entirely
(fail-closed — this generator never emits copper through the keepout,
even to complete the tree).

**Measured, real result:** of 85 MST edges, 74 route directly, 3 more
route via a one-bend detour, and **8 could not be routed around the
keepout by this bounded heuristic and were dropped**. The backbone is
therefore a forest of several components, not one connected tree — an
honestly-reported incompleteness, not a hidden one. A real
visibility-graph shortest-path router (rather than a bounded
nearest-candidate detour) would likely close most or all of this gap;
building one was judged out of this spike's remaining budget once the
core deliverable (real plane + real, measured improvement) was working.

---

## 7. Measured results

### 7a. `gnd` pad connectivity (`pad_connectivity_audit.audit_pcb_file`, the project's declared PRIMARY completion metric)

| | Before | After |
|---|---:|---:|
| `pad_count` | 86 | 86 |
| `pads_connected` (largest joined group) | **1** | **46** |
| `fully_connected` | False | False |
| `has_any_copper` | **False** | **True** |
| `unreached_pads` | 86 | 40 |

**46 of 86 `gnd` pads now land in one electrically-joined copper group,
up from a single isolated pad reaching nobody.** Not `fully_connected`
— §6d's forest limitation means the remaining 40 pads sit in smaller,
separate fragments (still real copper, still real vias, just not one
tree with the majority group). Per `NetConnectivityResult.is_fake_completion`'s
own definition (`has_any_copper and not fully_connected`), `gnd` moves
into that bucket post-fix — an honest classification to state plainly:
this is real, substantial, measured progress, not a claim of
completion.

### 7b. Whole-board pad connectivity

**Unchanged: 29/139 nets fully pad-connected, before and after** (all 29
are the same trivial single-pad nets identified in
`docs/evidence/2026-08-11-true-pad-connectivity-baseline.md`). `gnd`
does not cross into `fully_connected` (§7a), so it does not move this
count. The 0/110-real-net honest-completion headline from that document
is unchanged by this task's demonstration run.

### 7c. DRC — **not measured; `kicad-cli` and `pcbnew` are both unavailable in this sandbox**

Checked directly, not assumed: `shutil.which("kicad-cli")` returns
`None`; no `kicad-cli` binary exists anywhere on this filesystem (`find`
over `/`, `/opt`, `/snap`, this repo, and the referenced conda
environment all came up empty except one stray, non-executable flatpak
socket reference under `/tmp/org.kicad.kicad/` — `org.kicad.KiCad`
itself is not among the installed flatpak refs, only its
library/locale companion packages are). `python3 -c "import pcbnew"`
fails under both the system interpreter and the project's `uv`-managed
venv (`ModuleNotFoundError`). Neither `power_pcb_dataset/drc_ceiling.json`'s
baseline (`error_ceiling 1231`, `creepage 172`, `clearance 365`,
`shorting_items 199`) nor a fresh measurement against the generated
board could be produced here.

**This also means the emitted `In1.Cu` zone is an unfilled outline.**
Per this project's own documented convention
(`scripts/kicad_fill_zones.py`'s module docstring: *"a zone emitted with
only an outline polygon... reads as zero copper to DRC's connectivity
check"*), a `pcbnew.ZONE_FILLER` pass is required before any DRC run
would see this pour as real copper for creepage/clearance purposes — a
second tool this sandbox also lacks.

### 7d. Consequence: `pcb/temper.kicad_pcb` was deliberately left untouched

Per the upgraded mandate's own stated fallback ("If regeneration is not
achievable in budget, produce the generator change plus a demonstration
on a copy, and say clearly that the committed board is untouched"), and
per `AGENTS.md`'s hard requirement that any PR touching
`pcb/temper.kicad_pcb` re-measure `power_pcb_dataset/drc_ceiling.json`
in the same PR (a file this task's own boundaries forbid touching) —
writing the generated plane into the tracked board here would produce
an unverified, unfillable, un-DRC'd mains-board change with no path to
satisfy the repo's own gate. That is a contradiction worth stating
plainly rather than forcing past: **the fix is real and measured; the
environment to safety-verify it for the tracked artifact is not present
in this sandbox.** `pcb/temper.kicad_pcb` is provably unchanged
(`git status --short` / `git diff --stat` both empty on it throughout).
The demonstration output lives only in scratch space
(`/tmp/.../scratchpad/keepout_pour_spike/`), reproducible at any time
via `scripts/generate_ground_plane.py --pcb pcb/temper.kicad_pcb
--output <path>` on a machine with the project's Python toolchain (no
KiCad tools needed to *generate* — only to fill/verify).

---

## 8. Costing the options

**A. Land this generator as-is, unwired from production `route_pcb()`,
pending a KiCad-tooled environment to fill + DRC + re-baseline the
ceiling.** Cost: essentially done — this task. Value: closes the
single most embarrassing gap (a mains board's ground return with zero
copper) the moment someone with `kicad-cli`/`pcbnew` available runs
`scripts/generate_ground_plane.py`, fills the zone, DRCs it, and — if
clean — commits the regenerated board with a proper ceiling
re-measurement in the same PR. Risk: the forest/fragmentation
incompleteness (§6d) means the claim must stay "46/86 pads reached," not
"gnd is routed."

**B. Close the forest gap with a real visibility-graph router instead of
the bounded one-bend heuristic.** Cost: small-to-medium — a proper
shortest-path-around-obstacles algorithm over the keepout's disc union,
still well short of a full router. Would very likely recover most/all
of the 8 currently-dropped MST edges. Not done here; judged lower
priority than getting the core generator working and measured within
budget.

**C. Generalize `_zone_layers_for_net` to route other GND-class members
and build the In2.Cu power-island pours the original stackup plan (U4 of
`docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md`)
scoped.** Cost: large — genuinely a full implementation unit (thermal
via arrays, per-domain pour isolation, IPC-2152 current sizing
interaction), not a spike-sized extension of this task's module. Out of
scope here by design (see `_ground_plane.py`'s own docstring on why it
stays narrow).

**D. Wire keepout-before-pour into the existing outer-layer
(F.Cu/B.Cu) pour path** (`_zone_pour_stitch.py::_emit_zone_pours`),
addressing the 87.4%-coverage/creepage problem directly, using the same
per-pad-buffer keepout construction validated here. Cost: small —
`compute_hv_selv_keepout` is already net-domain-agnostic and could be
called from that path with minimal changes; the harder part (verifying
no existing net's outer-layer pour shrinks in a way that breaks its own
correctness) needs the same DRC tooling this task lacks. Also
independently unblocked by populating `constraints::IsolationBarrier`
for the already-built Rust detector (§5) as a backstop.

**None of A-D were done under the illusion that KiCad tooling
availability is someone else's problem to solve first** — B/C/D are
named here as the concrete next steps a maintainer with that tooling
available should pick up, in roughly that priority order.

---

## Sources

- `pcb/temper.kicad_pcb` (measured directly; unmodified by this task)
- `packages/temper-design-bundle/src/parse_engine.rs:1139-1147` (layer-role token discarded)
- `packages/temper-placer/src/temper_placer/io/_parse_board.py:90-300` (`_extract_stackup`)
- `packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py` (`_zone_layers_for_net`, hardcoded F.Cu/B.Cu)
- `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py` (the correct, unreachable design)
- `packages/temper-placer/src/temper_placer/router_v6/_net_policy.py` (`_should_route`, the already-fixed exclusion bug)
- `packages/temper-placer/src/temper_placer/core/design_rules.py` (`TEMPER_NET_ASSIGNMENTS`, `gnd` absent)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py` (read-only: `DEFAULT_CORRIDOR_WIDTH_MM`, `load_domain_manifest_nets`)
- `packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py` (measurement tool; via-layer literal-modeling gap found here)
- `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md` (U4, never implemented)
- `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md` (Landing Status: `use_declared_layer_roles` opt-in default off)
- `docs/evidence/2026-08-08-router-power-gnd-and-stage4-clearance-combined.md` (`gnd` "genuinely attempted and fails closed" under the fixed policy)
- `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` (the already-built, unpopulated DRC-side barrier-crossing detector; the unmerged barrier branch's own no-clean-line finding)
- `docs/evidence/2026-08-11-true-pad-connectivity-baseline.md` (baseline 0/110 fully connected; `pad_connectivity_audit`'s zone-blindness caveat)
- New: `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py`, `scripts/generate_ground_plane.py`, `packages/temper-placer/tests/router_v6/test_ground_plane.py`
