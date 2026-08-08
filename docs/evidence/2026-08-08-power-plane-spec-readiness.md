# REQ-ELEC-05 (Power Plane Design) — Readiness to Generate Real Copper

**Date:** 2026-08-08
**Scope:** `docs/hardware/POWER_PLANE_DESIGN.md` (REQ-ELEC-05, "Status: Implemented", v1.0,
2025-12-16, last touched at commit `07da9130`), against `pcb/temper.kicad_pcb` (unmodified by
this doc) and every code path in the repo that generates or checks power/ground plane copper.

**Verdict: NOT READY.** REQ-ELEC-05 is not a set of geometry decisions with a few gaps to fill
in — its central mechanism (a galvanically-joined GND star point between what it calls `PGND`
and `CGND`) specifies a net topology that (a) does not exist in the current schematic, (b) is
not merely "not yet built" but is the **exact topology a prior, documented safety fix
deliberately removed** because it shorted a certified isolation barrier, and (c) is now
prevented from being reintroduced by a CI-wired gate. Separately, every piece of code that
*does* generate real plane geometry today produces a single solid pour (or, at best, three
equal-width unconstrained strips) with no split, no islands tied to load, and no isolation
voids — and nothing in the DRC engine would notice if it did cross the barrier. This is a
"not ready" on both the spec (stale relative to a real safety fix) and the implementation
(does not build what the spec describes even where the spec is buildable).

All figures below come from files read or commands run in this session, listed inline.

---

## 0. What "power_plane.py" actually is (three different things, not one)

The task description's "`power_plane.py` generates 100% `In1.Cu` / 99.6% `In2.Cu` coverage"
maps to a *specific* module once you account for the fact that there are **three unrelated
"power plane" code paths** in this repo, none of which agree with each other or with
REQ-ELEC-05:

| # | File | What it does | Layer for GND | Split/islands? |
|---|------|---------------|----------------|-----------------|
| 1 | `scripts/add_power_planes.py` (docstring: "V5... single GND zone... NO overlapping priority zones — clean, solid copper pour") | One rectangle, 0.5mm board-edge inset, for net `GND` only | **`In2.Cu`** (hardcoded `LAYER_GND = "In2.Cu"`, line 21) | None. `PGND`/`CGND` are explicitly *not* joined by this script — its own comment (line 79-81) says they "connect via fanout vias to the unified GND plane," i.e. the split is asserted, not built. |
| 2 | `packages/temper-placer/src/temper_placer/io/zone_manager.py::add_power_planes()` | One solid GND zone on `In1.Cu` + one solid zone for **one** "primary" VCC net (first match of `+15V`/`+5V`/`+3V3`/`VCC`) on `In2.Cu`, both spanning the full board outline | `In1.Cu` (correct per stackup) | None — one net wins, the other two power rails get nothing. |
| 3 | `packages/temper-placer/src/temper_placer/router_v6/power_plane.py::generate_power_planes()` | `generate_ground_pour()`: one rectangle over the **exact full board bounds**, no inset, no voids, net `GND`, layer `In1.Cu`. `generate_power_pours()`: `In2.Cu` split into `len(domains)` (default 3: `+3V3`, `+5V`, `+15V`) **equal-width vertical strips**, gap = `DEFAULT_ISOLATION_GAP_MM = 0.3mm` | `In1.Cu` / `In2.Cu` | Three strips, fixed left-to-right order, equal width regardless of load — no relationship to REQ-ELEC-05 §4.1's load-driven 40/30/15/15% areas. |

**#3 is the module the 100%/99.6% figures come from**, and the arithmetic is exact, not
coincidental. `generate_ground_pour` returns the raw board rectangle
(`packages/temper-placer/src/temper_placer/router_v6/power_plane.py:129-136`) — by
construction, 100.000% of the board area, zero cutouts. `generate_power_pours` lays out 3
domains with 2 gaps of `0.3mm` each (`power_plane.py:34,46,172`); against the board width
declared in `packages/temper-placer/configs/temper_constraints.yaml:12-13`
(`width_mm: 100.0`, `height_mm: 150.0` — matching REQ-ELEC-05 §3.1/§4.1's stated "100mm × 150mm")
the lost width is `2 × 0.3 = 0.6mm` out of `150mm` → coverage `= (150 − 0.6) / 150 = 99.6%`,
matching the cited figure exactly. (Using the *real* board's actual `Edge.Cuts` outline instead
— `(20,20)`–`(172,254)`, i.e. 152mm × 234mm, read from `pcb/temper.kicad_pcb:8245-8251` — gives
`(152 − 0.6)/152 = 99.605%`, still rounding to 99.6%. Note the configured board size and the
real board's outline already disagree by 52mm × 84mm; not otherwise investigated here.)

Confirmed independently: `pcb/temper.kicad_pcb` contains the string `"In1.Cu"` and `"In2.Cu"`
**exactly once each** — only in the layer-definition table (`(1 "In1.Cu" signal)` /
`(2 "In2.Cu" signal)`, lines 10-11). No zone, pad, via, or track references either layer
anywhere in the file. Zero copper on both, as stated in the task. None of the three modules
above have ever been run against this board file and had their output committed.

The manufacturing-side stackup validator's own fallback constant
(`packages/temper-placer/tests/manufacturing/_stackup_validator_py_oracle.py:150-153`) encodes
the same "solid plane" mental model as a literal default: `{"F.Cu": 35.0, "In1.Cu": 95.0,
"In2.Cu": 95.0, "B.Cu": 30.0}`, commented `"In1.Cu: 1oz, solid GND plane ~95% fill"` / `"In2.Cu:
1oz, solid PWR plane ~95% fill"`. Nowhere in the toolchain — not the generators, not the
validator's own assumptions — is "split ground" or "power islands" represented as anything
other than "one solid pour."

---

## 1. Is the geometry fully specified? No — on both axes the task called out, and on a third the doc doesn't mention.

### 1a. GND plane split (§3)

REQ-ELEC-05 gives *areas* (PGND ~60%/60cm², CGND ~35%/52cm², ISOGND ~5%/8cm²), a *split gap
width* (2mm), a *star-point size* (10mm×10mm, "Location: Adjacent to DC bus negative
terminal" — a verbal reference, not a coordinate), a *via count* (20+, 4×5 array, 0.5mm drill,
1.5mm pitch), and four *void sizes* (8×4mm under UCC21550, 4×2mm under ADUM1250, 2mm×board-width
isolation-slot zone, "minimize" under high-dV/dt nodes) — but:

- **No boundary geometry.** Where the PGND/CGND split line actually runs (straight? stepped?
  what's its endpoint on each board edge?) is drawn as a single vertical divider in ASCII art
  with no dimension anchored to a board coordinate, a component refdes position, or the star
  point's own location.
- **No void placement.** The four voids are located by component name ("Under UCC21550
  transformer") or by a vague zone name ("Isolation slot zone"), never by (x, y). A generator
  cannot place a cutout from this document without a separate lookup into placement data this
  document doesn't cite.
- **The named nets don't exist.** REQ-ELEC-05 assumes three ground nets — `PGND`, `CGND`,
  `ISOGND` — connected by an explicit net-tie/star point. The current compiled netlist has
  neither `PGND` nor `CGND` at all (`grep` of `pcb/temper.kicad_pcb` for the literal strings
  `"PGND"` / `"CGND"`: **0 occurrences of each**), and no `ISOGND` net either. This is not new
  information this session invented — `docs/evidence/2026-07-28-netclass-defect-reconciliation.md:226-229`
  already recorded it: *"`CGND` ... has 0 occurrences in `elec/build/default.net` and is not
  mentioned anywhere in `elec/domain_manifest.yaml`. A legacy/historical alias ... not a live
  net."* The real board's ground-adjacent nets are `gnd` (87 string occurrences in
  `pcb/temper.kicad_pcb`, i.e. present with many pad references) and `PWR_RTN` (19
  occurrences) — different names, different case, and (see §3 below) *deliberately not
  galvanically joined*.

So even setting the safety question aside, §3's geometry cannot be executed as written: the
document specifies cutting copper by net domain, and two of its three named domains are not
nets on the board being cut.

### 1b. PWR plane islands (§4)

Areas are given (40%/30%/15%/15%-fill) with load lists and currents, but:
- No polygon geometry, no stacking orientation. §4.1's ASCII diagram stacks the three islands
  in horizontal bands (5V on top, 3.3V middle, 15V bottom); the only implementation that
  actually produces geometry (`router_v6/power_plane.py`) lays them out as **vertical** strips
  in a different order (`+3V3, +5V, +15V` left-to-right, `power_plane.py:35`). The document
  doesn't state which orientation is authoritative, so "matches the doc" isn't even a
  well-formed question for this axis.
- **`+5V` does not exist on the real board.** `grep -c '(net [0-9]* "+5V")' pcb/temper.kicad_pcb`
  → **0**. No `5V`/`vcc_5v` spelling exists either (checked case-insensitively across the full
  684-net list). §4.1's entire `+5V` island — sized off "LMR51430 output (5V, 2A)" feeding the
  fan driver, gate-driver VCCI, and the XC6220 LDO input — describes a rail the current design
  does not have. (`+15V` and `+15V_LS` do exist, 11 and several occurrences respectively,
  suggesting the regulator topology moved on from what §4 describes.)
- **`PE` is not a separate net either.** `grep -c` for `"PE"` (any case) → 0. `elec/domain_manifest.yaml:262-263`
  states directly: *"now bonded directly to protective earth (`gnd ~ pe`, main.ato) rather than
  to power_return — there is no separate `pe` net record any more"* — `pe` was merged into `gnd`.
  `power_plane.py`'s own net table (`TEMPER_PLANE_NETS`, `deterministic/stages/power_plane.py:60`)
  still lists `"PE"` as a distinct plane net targeted at layer 0 (`F.Cu`).

### 1c. Net-name matching is silently broken against the real board (not called out by either question, but load-bearing for "ready to generate from")

`recompute_plane_assignments` (`packages/temper-design-bundle/src/deterministic_leaves.rs:419-458`,
the Rust kernel behind the deterministic `PowerPlaneStage`) matches net names by **exact
case-sensitive string equality** (`std::collections::HashSet<&str>`, lines 425-426, 431, 443).
Checked every entry of `TEMPER_PLANE_NETS` against `pcb/temper.kicad_pcb` by exact string:

| Net in `TEMPER_PLANE_NETS` | Occurrences in `pcb/temper.kicad_pcb` | Real equivalent |
|---|---|---|
| `GND` | 0 | `gnd` (87) — case mismatch |
| `PGND` | 0 | none — merged into `PWR_RTN`/`gnd`, see §3 |
| `CGND` | 0 | none |
| `+15V` | 11 | matches |
| `+3V3` | 52 | matches |
| `+5V` | 0 | doesn't exist (§1b) |
| `DC_BUS+` | 0 | `+170V_BUS` |
| `DC_BUS-` | 0 | `DC_BUS_RTN` |
| `SW_NODE` | 8 | matches |
| `AC_L` | 0 | `ac_l` (3) — case mismatch |
| `AC_N` | 0 | `ac_n` (4) — case mismatch |
| `PE` | 0 | merged into `gnd` (§1b) |

**9 of 12 net names in the deterministic layer-assignment stage's own plane-net table have zero
exact-string matches on the real board.** Concretely: the ground net (`gnd`), the AC input nets,
and the DC bus nets are silently *not* marked `is_plane=True` by `PowerPlaneStage` against this
board today, because the matching is case- and spelling-exact and the real netlist uses
different names. Whether the parallel generation-wiring work reads net names from this stage's
output or re-derives them elsewhere is out of this analysis's scope to determine, but if it
reads from here, the ground plane specifically — the one net every other finding in this
document is about — would not get marked for plane connectivity at all.

---

## 2. Does `power_plane.py` implement what the document specifies?

No, on every clause that can be checked, and the divergence direction is consistent: every
generator (see §0's table) produces the simplest possible geometry — one solid pour, or evenly
divided strips — never the doc's domain-driven split/island geometry. Clause-by-clause:

| REQ-ELEC-05 clause | Doc requirement | What ships (any of the 3 generators) | Authoritative? |
|---|---|---|---|
| §3.1 GND domains | 3 domains (PGND/CGND/ISOGND), 60/35/5% | 1 domain, 100% (router_v6) or 1 unified zone (scripts/, zone_manager) | **Doc**, but unbuildable as written — see §1a. Code is simpler-and-wrong, not an intentional simplification with a stated reason. |
| §3.2 Star point, 20 vias, 10×10mm | Explicit net-tie bridge | Not implemented anywhere; no code references a star point or a net-tie footprint | Doc describes something safety-relevant that was already tried and removed — see §3 below. Neither is "authoritative" until §3's finding is resolved. |
| §3.4 Voids (isolation barrier, ×4) | 4 explicit cutouts | None of the 3 generators cut any void; `generate_ground_pour` is a solid rectangle with **zero** cutouts | **Doc** — this is the one clause that is safety-critical *and* buildable in principle (see §3), so the code is simply missing required geometry, not disagreeing on a design choice. |
| §4.1 Islands, load-driven 40/30/15/15% | Sized to LMR51430/XC6220 loads, board-position-relative | 3 (or 1) equal-width strips, position-independent, fixed net order | **Doc's intent** (island area should track load), but doc's own island definitions are partly stale (§1b, `+5V` doesn't exist) — neither is fully executable today. |
| §4.2 Island separation ≥1.0mm | ≥1.0mm, "prevent shorts, allow routing" | `DEFAULT_ISOLATION_GAP_MM = 0.3mm` (`power_plane.py:46`) | **Doc.** The code's own comment claims this value is "the GND/Power class clearance from `configs/netclass_rules.yaml`" — checked: that file's `GND` entry is a **self**-clearance of `0.3mm` (`netclass_rules.yaml:111-112`) and `Power` a self-clearance of `0.25mm` (`:75-76`); there is no `GND`-`Power` *pair* entry, so unlabeled pairs fall back to `default_clearance_mm: 0.2mm` (`:9`). None of these three numbers is "island separation" — that's a distinct, specifically-justified rule in REQ-ELEC-05 §4.2 itself, and the code cites the wrong table for it. The value used is under a third of what the design doc it's supposedly implementing requires. |
| §5 Via stitching (10mm perimeter, 5mm switch-node ring, 3mm under ESP32, 8mm around isolation barrier) | 4 distinct pitches, purpose-tied | Only one via pattern exists in code at all: a 3×3 **thermal** array under Q1/Q2 (`generate_thermal_vias`, unrelated net `DC_BUS+`) | **Doc** — none of §5's stitching vias are implemented by any generator found. |
| §6.4 Thermal relief (solid for power vias/IGBT pad, spoked for signal) | Per-connection-type rule table | Every generator uses one uniform `thermal_gap=0.5, thermal_bridge_width=0.5` setting for its zone(s), regardless of connection type | **Doc** — the per-type distinction isn't represented in code. |

**Net effect on "99.6%/100% coverage":** those figures describe geometry that looks nothing
like what the document calls "split" and "islands" — they describe two solid-to-near-solid
pours. The 99.6% figure is not evidence the spec was followed; it's the direct, computable
consequence of choosing a 0.3mm gap between 3 arbitrarily equal strips on a wide board, a
choice unconnected to any load, area percentage, or the doc's own ≥1.0mm minimum.

---

## 3. Does the split interact with safety isolation? Yes — and the interaction is worse than "unimplemented."

This is the most important finding in this document. **REQ-ELEC-05 §3.2's star-point
specification describes, at the net-topology level, almost exactly the construction that a
prior, dedicated safety investigation found and removed as the single highest-consequence
defect it discovered on this board.**

- `elec/domain_manifest.yaml:17-23`: *"the original star-point join (`power_return ~ gnd`,
  `main.ato`) shorted the AuxSupply's isolation barrier outright ... That join has been REMOVED
  (`docs/hardware/SELV_ISOLATION_REDESIGN.md`, commit `6976ef44`): `gnd` and `PWR_RTN` are
  separate compiled nets as of this manifest's writing."*
- `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:21-41` (§2.1, preserved as the historical
  record): the original star join tied the SELV control domain's ground reference through
  `power_return` to a node that tracks AC Neutral — defeating a Mean Well IRM-10-15 module
  independently certified for a **4.2 kVAC** input-output withstand rating — described there as
  *"the single highest-consequence finding in this document."*
- The fix (`:43-49`, commits `6976ef443` / `1390e807`): the star join line is gone
  (`elec/src/main.ato:714`, replaced by a comment recording the removal); `gnd` is instead bonded
  directly to protective earth (`gnd ~ pe`) and verified as a **distinct** compiled net from
  `PWR_RTN` (80 pins on `gnd`, 17 on `PWR_RTN` per that document's own falsifier).
- `scripts/check_domain_partition.py` is now wired into CI
  (`.github/workflows/python-tests.yml:706,718` per the same document, not independently
  re-verified in this session) specifically to fail if the star join is reintroduced.

REQ-ELEC-05 §3.2 ("PGND and CGND connect ONLY at the star point... Location: Adjacent to DC bus
negative terminal... 20 vias minimum") is, in net-topology terms, the same shape of construction
— a single deliberate galvanic bridge between what are now `gnd` and `PWR_RTN` (or whatever the
document's `PGND`/`CGND`/`ISOGND` domains would map onto today). REQ-ELEC-05 predates none of
this — it's dated 2025-12-16, the SELV redesign is dated 2026-07-26, and REQ-ELEC-05 has not
been revised since (single revision-history entry, §9) to reflect it. **Executing REQ-ELEC-05
§3 as literally written today would mean rebuilding the exact join that was found to short a
certified 4.2 kVAC barrier and was removed for that reason** — and would additionally fail the
CI gate now watching for it. This is not a copper-generation gap; it is a stale requirement
that actively points at a previously-fixed defect.

*(REQ-ELEC-05's §3.4 voids are a different matter: cutting copper away from an isolation
barrier is the same direction as the fix, not the opposite of it, so those four voids remain a
reasonable, safety-positive requirement — they're just unbuilt, per §2 above.)*

### 3b. Would anything in the codebase catch a plane crossing the barrier? No — checked three ways.

1. **`IsolationCheck` (`packages/temper-drc-rs/src/rules/safety/isolation.rs`)** only inspects
   *component* positions against a *named* zone's declared net classes (`check()`,
   lines 68-131) — it has no concept of copper-pour/zone polygons at all. The module's own test
   suite documents this as a known defect (lines 238-281, `bug_fires_regardless_of_component_position_no_spatial_containment_check`):
   `ZoneDefinition` in `constraints.rs` carries only `name` + `net_classes`, no `bounds` field,
   so even the geometric containment the check's docstring promises isn't implemented for
   components, let alone for plane geometry.
2. **It's also structurally inert on this project's own constraint config.** `is_iso_zone`
   (isolation.rs:41-44) requires the zone's *name* to contain one of
   `["iso","opto","coupler","transformer","gutter","slot"]`. None of the 17 named zones in
   `packages/temper-placer/configs/temper_constraints.yaml` (`power_zone`, `driver_zone`,
   `control_zone`, `interface_zone`, `igbt_power_stage`, `gate_driver_circuit`, ..., `bootstrap`)
   matches any of those keywords. `check()` returns early with zero violations whenever
   `iso_zones.is_empty()` (isolation.rs:79-81) — so on this board's actual configuration, the
   check can never fire, for any reason, today.
3. **`CreepageCheck` and `HVLVSeparationCheck`** (same directory) are likewise purely
   component/pad-geometry checks — package width and edge-to-edge component distance,
   respectively. **The REQ-SAFE-01 clearance/creepage validator**
   (`packages/temper-placer/src/temper_placer/requirements/validators/{clearance,_copper}.py`,
   `packages/temper-drc-rs/src/req_safe_01.rs`) — the one place in the repo that actually
   computes IEC 60335 creepage/clearance numbers (8.0mm REINFORCED HV↔SELV/ISOLATED creepage,
   `clearance.py:265-284`, matching the task's cited figure) — is built entirely on
   pad-to-pad copper geometry (`_copper.py`'s `_CopperModel`, `copper_scan_py`). It has no
   representation of an inner-layer zone polygon whatsoever; a GND or PWR pour on `In1.Cu`/`In2.Cu`
   bridging the isolation barrier is invisible to it by construction, not merely by
   misconfiguration.

**Conclusion: nothing in the DRC/validator surface would notice a plane pour crossing the
isolation barrier, independent of the topology question in §3a.** If REQ-ELEC-05's voids are
skipped when generation is wired up, no automated check catches it.

---

## 4. Are the impedance numbers self-consistent? Partially, and one clause is internally contradictory.

REQ-ELEC-05 §2.3 gives: Microstrip L1→L2 (GND ref) 50Ω, 0.28mm trace; Microstrip L4→L3 (PWR
ref) 50Ω, 0.28mm trace; Stripline L2-or-L3 (both ref) 50Ω, 0.20mm trace. Checked against §2.1's
stated z-heights.

**4a. The stack diagram is internally inconsistent about copper thickness.** Reading §2.1's
z-boundaries literally: L1 spans `0.000→0.070mm` (0.070mm = 2oz, matches its "2 oz" label);
Prepreg 1 spans `0.070→0.270mm` (0.200mm, matches its "(0.2mm)" label — consistent); but L2 then
spans `0.270→0.340mm`, i.e. **0.070mm**, even though §2.2's table labels L2 "1 oz" (which is
0.035mm). The same doubling recurs for L3 (`1.340→1.410`, 0.070mm, labeled 1oz) and L4
(`1.610→1.680`, 0.070mm, labeled 1oz). Summing the diagram's own boundary deltas gives a total
stack height of 1.680mm; summing the *labeled* copper weights instead (0.070 L1 + 0.200 PP1 +
0.035 L2 + 1.000 core + 0.035 L3 + 0.200 PP2 + 0.035 L4) gives **1.575mm** — a 0.105mm
discrepancy, exactly `3 × 0.035mm`, i.e. exactly the three 1oz layers each drawn one full 1oz
too thick. The task's own reference points ("L2 at 0.305mm, L3 at 1.375mm") are the diagram's
box-center labels and are only self-consistent with the **wrong** (2oz-drawn) boundaries, not
with the document's own stated 1oz copper weights. This is a genuine, checkable inconsistency
between §2.1 and §2.2, not a rounding artifact.

**4b. No dielectric constant is stated anywhere in the document.** Using the boundary-based
reading (Prepreg 1 = 0.200mm dielectric height between L1's bottom and L2's top — the one
figure in the stack that both readings agree on, since it's a prepreg thickness, not a copper
thickness), a standard microstrip formula (IPC-2141: `Z0 = 87/√(εr+1.41) · ln(5.98h/(0.8w+t))`,
h=0.20mm, w=0.28mm, t=0.07mm for 2oz L1 copper) requires **εr ≈ 4.55** to land on 50Ω. That's a
plausible FR4 value, but REQ-ELEC-05 never states a laminate or its εr — Sections 2.1-2.3 give
copper weights and a prepreg/core thickness but no material spec. **The 50Ω figures are
unfalsifiable as documented**: a reader cannot check them without guessing the dielectric
constant the author used, and the number recovered by reverse-solving (4.55) is a guess this
session made to test plausibility, not a value confirmed anywhere in the repo.

**4c. The Stripline row doesn't apply to this stackup as specified.** §2.3's third row is
"Stripline L2 or L3 | Both ref | 50Ω | 0.20mm" — a signal trace *routed on* L2 or L3, referenced
by the planes on both sides. But §2.2 and every other section of this same document designate
L2 and L3 as **wholly dedicated** plane layers (GND and PWR respectively) — §6.1/§6.2's copper
pour tables list no signal routing on either inner layer, and §4.2's own rule states "No
islands under HV — Keep L3 as GND flood." A stripline signal trace cannot be routed *on* L2
while L2 is simultaneously the reference plane a stripline on some other layer would need. This
row is either a leftover from a generic 4-layer template not adapted to this specific
all-plane inner-layer stackup, or the document elsewhere (§2.2, §6) is wrong about L2/L3 being
fully dedicated. Either way it's inapplicable-or-contradictory as written. (§2.3's own footnote
— "Controlled impedance not required for this design (max signal frequency ~100MHz for ESP32)"
— suggests the whole table may be treated as non-binding reference material rather than a
requirement anyone intended to hold the board to; that reading is not stated explicitly enough
to rely on.)

---

## 5. What must a human decide vs. what this document resolves

### Resolved by this analysis (no further human input needed to state the fact, though action is still required):
- The three plane-generation code paths disagree with each other and with the spec on GND
  layer assignment, split, and island count — **use `router_v6/power_plane.py`'s layer
  convention (`In1.Cu`=GND, `In2.Cu`=PWR) as the one consistent with the doc and with
  `netclass_rules.yaml`; `scripts/add_power_planes.py`'s `In2.Cu`-for-GND choice is the odd one
  out and should not be the one wired into the real output path without a rename.**
- `PGND`, `CGND`, `ISOGND`, `+5V`, and a standalone `PE` net do not exist on the current board;
  `power_plane.py`'s net tables reference several names that don't exact-match the real
  netlist at all (§1c). This is a fact, not a judgment call, though what replaces those names
  is a design decision (next section).
- The star-point ground join REQ-ELEC-05 §3.2 specifies was already built once, found to short
  a certified isolation barrier, and removed; it should not be rebuilt as specified without
  re-deriving it against the current, correct topology (§3).
- Nothing in the DRC/validator surface checks plane/zone geometry against the isolation barrier
  (§3b) — this is a coverage gap independent of whether §3.2's specific construction is used.
- The 50Ω impedance figures cannot be independently verified without a stated dielectric
  constant (§4b); the stack diagram's copper-thickness boundaries contradict its own 1oz labels
  by exactly 2× on three layers (§4a).

### Requires the board owner's decision (out of scope for an agent to resolve):
1. **What is the current, intended ground topology?** REQ-ELEC-05 §3 describes a 3-domain
   split (`PGND`/`CGND`/`ISOGND`) with a star point; the actual schematic today has a 2-net
   split (`gnd`/`PWR_RTN`) with **no** direct galvanic join, by deliberate design
   (`SELV_ISOLATION_REDESIGN.md`). REQ-ELEC-05 needs to be rewritten against the real topology,
   not patched — this is a safety-relevant electrical decision, not a documentation fix an
   agent should make unilaterally.
2. **Where, physically, is the isolation barrier** (coordinates, not a component name), so that
   §3.4's four voids and any GND/PWR pour boundary can be placed without guessing? This
   requires the current placement data, which this document doesn't cite and this analysis
   didn't cross-reference.
3. **What is the current `+5V` rail's fate?** §4.1's `+5V` island is sized against a rail that
   no longer exists in the netlist — was it folded into `+3V3`/`+15V`, or dropped, or renamed?
   Only the board owner (or the schematic history) can say.
4. **What laminate/εr is this stackup built from?** Needed to make §2.3's 50Ω claims checkable
   at all, and to confirm whether the impedance table is a real requirement or reference-only
   (per its own "not required" footnote).
5. **Is §4.2's ≥1.0mm island-separation rule still the intended minimum**, or was the 0.3mm
   value now hardcoded in `router_v6/power_plane.py` an intentional, undocumented relaxation?
   (This document does not relax it — flagging the conflict is as far as this analysis goes,
   per the hard constraint against proposing clearance changes.)
6. **Whether `check_domain_partition.py`'s CI gate is the intended permanent backstop** for the
   ground-join question, or whether an equivalent zone-geometry check needs to be added
   specifically for plane pours (since, per §3b, no existing DRC rule inspects zone polygons at
   all) before plane generation is wired into the real output path.

---

## Bottom line

REQ-ELEC-05's "Status: Implemented" is not supported by the board file (zero copper on
`In1.Cu`/`In2.Cu`, confirmed), by the code (three mutually-inconsistent generators, none of
which builds the split/island geometry the doc describes), or by the schematic (the doc's named
ground domains don't exist as nets). Worse than a documentation lag: the document's flagship
ground-topology requirement (§3.2's star point) reintroduces, in net-topology terms, a
previously-found-and-removed safety defect, and no DRC rule in the repository would notice a
plane pour crossing the isolation barrier even if the rest of the geometry were built correctly.
**Not ready to generate real copper from as written.** Before wiring plane generation into the
real output path, the board owner needs to resolve the six items above — at minimum, REQ-ELEC-05
§3 needs to be rewritten against the actual `gnd`/`PWR_RTN` topology (not `PGND`/`CGND`), and a
geometry-aware isolation check needs to exist before any generator is trusted to place copper
near the barrier unsupervised.
