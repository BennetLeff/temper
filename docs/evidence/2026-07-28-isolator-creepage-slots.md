<!-- provenance: commit=b1499a165d236f0a44f5d2ed50e929f38fa2902c dirty=false -->

# Routed creepage-extension slots for U3 and U7: design, verification, implementation

Base commit: `b1499a16` (`merge: reconcile with concurrent session before
push`), branch `feat/provable-safety-place-and-route` (the task named branch
`docs/methodology-loop-discipline` for this commit; that branch's own tip is
`f8b5f43c` and does not contain `b1499a16` -- `b1499a16` lives on
`feat/provable-safety-place-and-route`. Checked out directly at `b1499a16` in
this worktree regardless, per the task's explicit instruction; noted here
rather than silently reconciled). Work done in worktree
`agent-a98c54f75cb42e5e7`, branch `feat/isolator-creepage-slots`.

## Provenance labels used throughout

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Read this session from the standard's own text; source and URL in Sources. |
| **CITED-SECONDARY** | Read this session from a manufacturer/fab document; URL in Sources. |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / the footprint files, script shown or described. |
| **DERIVED** | Arithmetic/geometry on labelled inputs, shown in full. |
| **ASSUMED** | Not established; flagged for a human. |

---

## Verdict up front

**FALSIFIER: "A routed slot can bring `U3` and `U7` to 8.0 mm creepage within
the existing land patterns and fab capability. If the required slot is
unmanufacturable, compromises mechanical support, or cannot fit under the
body, then the land patterns need redesign or the parts need changing -- and
that is the finding."**

**Did not fire.** Both parts reach 8.0 mm reinforced creepage with a routed
slot inside their existing footprints, verified by computational shortest-
path geometry (not asserted):

| Ref | Pre-slot creepage | Slot (local coords, footprint frame) | Nominal creepage after slot | Worst-case (fab tolerance) | Margin (nominal) |
|---|---:|---|---:|---:|---:|
| `U7` | 7.250 mm | 6.0 x 11.2 mm, x=[-3.0,3.0] y=[-5.6,5.6] | **8.627 mm** | **8.124 mm** | +0.627 mm (7.8%) |
| `U3` | 6.020 mm | 5.0 x 9.0 mm, x=[1.3,6.3] y=[-2.0,7.0] | **9.128 mm** | **8.470 mm** | +1.128 mm (14.1%) |

Both pass at nominal geometry and under a modelled worst-case fab tolerance
(JLCPCB regular precision, ±0.2 mm/edge, CITED-SECONDARY, §7). Clearance is
untouched (still 7.25 mm / 6.02 mm -- non-binding against the 1.5-2.0 mm
clearance requirement established in the base-commit brainstorm doc) --
**a slot extends creepage only**, per the hard rule and per the standard
itself (§3).

**One real placement constraint surfaced and is reported plainly, not
hidden:** `U7`'s slot length is capped below its geometric optimum (11.6 mm
would give 8.984 mm) because this part sits only 5.9 mm from the board's
left `Edge.Cuts` boundary once its 270° rotation is applied. The 8.0 mm
design keeps 0.3 mm slot-to-board-edge clearance (matching JLCPCB's ±0.2 mm
outline tolerance with a small margin); the un-capped design would have left
only 0.1 mm, unmanufacturable. This did **not** make the falsifier fire --
8.0 mm is still reached with real margin at the capped length -- but it is
the reason `U7`'s margin (7.8%) is tighter than `U3`'s (14.1%), and it is
load-bearing for the PD3 question below.

**PD3 (12.6 mm), flagged per the task, not silently adopted:** `U3` reaches
12.6 mm with a trivial extension (9.5 mm slot length vs 9.0 mm today,
DERIVED, well within its >46 mm/>10 mm real clearance to the board edge and
nearest neighbour). **`U7` does NOT** -- the required slot length at PD3
(15.37 mm, DERIVED by bisection) would put the slot's near end at absolute
x=18.2 mm, *past* the board's left edge at x=20.0 mm. At PD3, `U7` as
currently placed and rotated cannot be brought to spec by this footprint
alone; it would need the component moved ~2.1 mm away from the board edge
(a placement change, out of this task's scope per the coordination note) or
the board outline extended. This is exactly the honest "what changes at
12.6 mm" the task asked for.

---

## 1. Geometry, verified from the real footprint files (task item 1)

### 1.1 `U7` -- TI UCC21550BDWK, `lib:SOIC16W_Isolated`

MEASURED directly from `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` (the
real footprint `pcb/temper.kicad_pcb` references for U7 at board position
`(25.9, 26.43, 270)`), before any edit this session:

- Primary-side pads (pins 1-8, local x=-4.65mm): roundrect, size 2.05 x
  0.6mm, so inner edge (facing the secondary side) at **x=-3.625mm**.
- Secondary-side pads (pins 9,10,11,14,15,16, local x=+4.65mm): same size,
  inner edge at **x=+3.625mm**.
- **Edge-to-edge gap = 3.625 - (-3.625) = 7.250 mm.** Matches the task's
  stated figure and the two prior sessions' independent measurements
  exactly.
- `F.Fab` body outline (`fp_poly`): x-span **[-3.75, 3.75]mm**, y-span
  [-5.15, 5.15]mm (with a small pin-1 corner notch). The entire 7.25mm gap
  (x=[-3.625,3.625]) sits inside the body's x-span (x=[-3.75,3.75]) -- pads
  tuck 0.125mm under the body edge on each side. **100% of the shortest
  path is under the component body**, confirmed independently a third time
  (matching `2026-07-28-conformal-coating-pd1.md`'s figure).
- Isolator groups per `elec/domain_manifest.yaml`'s `hb.gate_hs.driver`
  entry: primary=[1-8] (logic/SELV side), secondary=[9-16] (floats on
  switch node/`DC_BUS_RTN`, HV side). Used to classify which pad column is
  which domain for the creepage search below -- not net-name lookup, which
  is ambiguous for several individual pins on this component (pin 6's net
  `hb.gate_hs.driver-p1` is the primary-side DT pin, explicitly *not* in
  the manifest's HV list per its own comment; using the declared isolator
  groups avoids that ambiguity entirely).

### 1.2 `U3` -- H11L1 opto, `Package_DIP:DIP-6_W7.62mm` (pre-edit)

MEASURED directly from `pcb/temper.kicad_pcb`'s U3 footprint block before
any edit this session (`at 118.82 107.02 0`, no rotation):

- HV-side pads (pins 1, 2 -- net `a`, `PWR_RTN`; local x=0): circle/roundrect
  1.6mm dia, inner edge (facing SELV side) at **x=0.8mm**.
- SELV-side pads (pins 4, 5, 6 -- net `ZCD_ISO`, `gnd`, `+3V3`; local
  x=7.62mm): same size, inner edge at **x=6.82mm**.
- **Edge-to-edge gap = 6.82 - 0.8 = 6.020 mm.** Matches the task's figure
  (6.02mm edge-to-edge, 9.16mm centre-to-centre would be wrong -- the real
  centre-to-centre here is 7.62mm, the DIP row pitch; 9.16mm does not match
  anything measured on this part and is not used below).
- `F.Fab` body outline: x-span **[0.635, 6.985]mm**, y-span [-1.27, 6.35]mm.
  The entire 6.02mm gap (x=[0.8,6.82]) sits inside the body's x-span
  (x=[0.635,6.985]) -- a standard DIP package body sits directly over the
  gap between its own two pin rows, structurally, on every DIP part, not
  just this one. **100% of the shortest path is under the component body.**
- Isolator groups per `elec/domain_manifest.yaml`'s `power_in.zcd_opto`
  entry: primary=[1,2] (HV, LED anode/cathode), secondary=[4,5,6] (SELV,
  phototransistor output/gnd/vcc). Pin 3 is unused (no net).

Both figures denominator-match the two prior evidence docs
(`2026-07-28-conformal-coating-pd1.md`, `2026-07-28-creepage-determination-
brainstorm.md`) to the millimetre -- three independent measurements, same
answer, for both parts.

**`K2`/`K3` are out of scope for this task**, per the task's own framing:
their governing path runs across the relay's own moulded case (a component
property no board feature can lengthen), and they carry no coil-to-contact
creepage rating at all. Not re-analysed here; a sibling agent is handling
the replacement.

---

## 2. The minimum groove width to count (task item 2, first half)

**CITED-PRIMARY, IS 15382 (Part 1):2003 = IEC 60664-1 (2002), clause 4.2**
(fetched and read this session -- the earlier brainstorm doc flagged this
exact rule as "NOT read this session" / UNVERIFIED; closed here):

> "The dimension X, specified in the following examples, has a minimum value
> depending on the pollution degree as follows:
>
> | Pollution degree | Dimension X minimum value |
> |---|---|
> | 1 | 0.25 mm |
> | 2 | 1.0 mm |
> | 3 | 1.5 mm |
>
> If the associated clearance is less than 3 mm, the minimum dimension X may
> be reduced to one third of this clearance."

And the two governing worked examples (CITED-PRIMARY, same clause, quoted
in full because the rule and its counter-rule both matter):

> **Example 1** -- "Path under consideration includes a parallel- or
> converging-sided groove of any depth with a width less than X mm. **Rule:
> Creepage distance and clearance are measured directly across the groove**
> as shown."
>
> **Example 2** -- "Path under consideration includes a parallel-sided
> groove of any depth and equal to or more than X mm. **Rule: Clearance is
> the "line of sight" distance. Creepage path follows the contour of the
> groove.**"

**DERIVED: at this board's pollution degree (PD2), X = 1.0 mm** is the
governing minimum -- a groove/slot narrower than that is bridged (measured
straight across, as if it weren't there) and buys nothing. Both slots
designed here (5.0mm and 6.0mm wide) exceed this floor by 5-6x. The
"clearance <3mm -> X may be reduced to 1/3" relaxation is **not needed and
not relied on** -- both designs clear the flat 1.0mm PD2 figure with large
margin, and the flat figure is also correct if PD3 (X=1.5mm) ends up
governing (§Verdict).

**Coincidentally, this figure matches JLCPCB's independently-cited fab
minimum for a non-plated routed slot (1.0mm, §7) -- two unrelated
constraints landing on the same number. Neither one is derived from the
other; both happen to bind at 1.0mm.**

---

## 3. How creepage actually flows across a full through-board slot (task item 2, second half) -- a correction to an existing repo document

This is a DERIVED interpretation, not a literal quotation, and it is
important enough to state as its own finding.

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1 models a slot's benefit as:

> `Effective creepage = 2 x slot width + surface across slot`
> `= 2 x 2.0mm + 4.0mm = 8.0mm minimum`

implying the path goes *down* one wall of the slot (a vertical traverse
through the board), *across* at the bottom, and *up* the other wall -- the
"down/across/up" reading of IEC 60664-1's Example 2 contour rule (§2),
applied as if the slot had a solid floor.

**That model is wrong for a slot that is cut completely through the board
(a real routed slot, no remaining material at the bottom) unless it is
applied with board *thickness*, not slot *width*, as the vertical term --
and even then it understates the true governing path.** Reasoning:

A full-depth slot that does not reach the board edge is an island-shaped
hole surrounded by solid board on every side. Its two long walls are real
insulating surfaces (exposed FR4 at the routed cut edge), so a path *can*
legitimately travel down one wall to the bottom face of the board. But at
that point there is **no floor to walk across** -- directly beneath the
hole's footprint, on the underside of the board, is the same open hole,
not solid material. To reach the opposite wall's base, the path must
travel *around* the hole's footprint on the underside -- which is the same
detour distance as going around the hole's end on the *top* surface, plus
the extra two board-thicknesses of vertical travel. **The through-wall
route is therefore never shorter than the around-the-end route on the top
surface; it is strictly longer.** The genuinely shortest (governing)
surface path across a fully-enclosed through-slot is the one that never
goes underground at all: it detours around whichever end of the slot is
nearest, staying on the top surface throughout.

This is also the mechanism actually drawn in industry isolator-IC layout
application notes (a wavy line routing around the rounded end of a slot on
the top copper layer, not a cross-section down-and-up) -- consistent with,
not a departure from, established practice.

**Practical consequence for this document's own numbers:** the design
figures above (8.627mm for U7, 9.128mm for U3) come from the around-the-end
model, computed by an actual shortest-path search (§4), not asserted from a
formula. For completeness: applying the (rejected) down/across/up model
with the board's real thickness (1.6mm, MEASURED from `pcb/temper.
kicad_pcb`'s `(general (thickness 1.6))`) as the vertical term instead of
slot width would give `2x1.6 + 6.0 = 9.2mm` (U7) and `2x1.6 + 5.0 = 8.2mm`
(U3) -- both also happen to clear 8.0mm for these specific dimensions, which
is a coincidence of this particular sizing, not a validation of the model:
a narrower slot that didn't extend far enough beyond the package would pass
under the down/across/up model while failing the real around-the-end path,
which is the unsafe direction for a safety figure to be wrong in. **This is
flagged as a correction to `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1**,
consistent with that document's other uncited/incorrect figures already
catalogued by the two prior evidence docs (the ×1.5 coating multiplier, the
6.0mm "clearance" that is actually a mislabeled creepage value).

---

## 4. Slot design and verification method (task items 2-3, 5)

### 4.1 Method

Script `slot_design.py` (session scratchpad, not committed -- read-only/
design analysis, matching the precedent of the sibling evidence docs).

1. Model each pad as an axis-aligned rectangle in the footprint's own local
   coordinate frame (rotation/translation-invariant for distance purposes
   -- board-absolute placement only matters for the separate neighbour/
   edge feasibility check, §4.3).
2. Model the candidate slot as a rectangular obstacle.
3. For **every** HV-pad-edge <-> SELV-pad-edge pair on the component (48
   pairs for U7: 8 primary x 6 secondary; 6 pairs for U3: 2 x 3), compute
   the shortest path between the two edge points that does not cross the
   slot's interior, using a visibility graph (nodes = the two edge points
   plus the slot's 4 corners; edges pruned if the straight segment between
   two nodes crosses the rectangle's interior; `networkx` Dijkstra for the
   shortest path). This is an independent, computational verification of
   the "path detours around the nearest end" geometric argument (§3), not
   an assumption -- a segment that can validly graze a corner is kept, one
   that would cut through the slot's interior is removed from the graph
   before the shortest path is ever computed.
4. Report the **minimum** over all pairs -- the true governing creepage
   figure with the slot in place, per the standard's own "measured in the
   most unfavourable position" principle (also CITED-PRIMARY, same clause
   4.2: "creepage distances and clearances measured between parts which
   can assume different positions... are measured when these parts are in
   their most unfavorable position" -- here, "most unfavourable pin pair").
5. Sanity check: with a negligible/zero-size slot placed exactly at the
   real gap location, the method reproduces the pre-slot baseline exactly
   (7.250mm for U7, 6.020mm for U3) -- confirmed by direct run, not assumed.

### 4.2 U7 result table (Xe = slot half-width, Ye = slot half-length, both
in local mm; governing pair is always the outermost pin pair, pins 8/9 or
1/16, both at |y|=4.445mm -- the pins closest to either end of the slot,
hence with the shortest detour, DERIVED and confirmed by the search itself)

| Xe | Ye | Slot (WxL, mm) | Pad clearance | Creepage |
|---:|---:|---|---:|---:|
| 3.0 | 5.6 | 6.0 x 11.2 | 0.625mm | **8.627mm** (chosen) |
| 3.0 | 5.8 | 6.0 x 11.6 | 0.625mm | 8.984mm (geometric optimum -- rejected, board-edge infeasible, §4.3) |
| 3.2 | 5.4 | 6.4 x 10.8 | 0.425mm | 8.491mm |
| 2.8 | 5.4 | 5.6 x 10.8 (worst-case shrink of the chosen design) | 0.825mm | 8.124mm |

### 4.3 U7 real-board placement check (task item 3 -- distance to adjacent
copper, board rigidity)

MEASURED from the real, unedited `pcb/temper.kicad_pcb` (U7 at absolute
`(25.9, 26.43)`, rotated 270°; board outline `Edge.Cuts` is `(20,20)-
(172,254)`):

- Transforming the candidate slot's local corners through the footprint's
  actual position+rotation, the **8.0mm design (Ye=5.6)** reaches absolute
  x=20.3mm -- **0.3mm clearance to the board's left edge.**
- The un-capped, geometrically-larger design (Ye=5.8, which would give
  8.984mm) reaches absolute x=20.1mm -- **0.1mm clearance, below JLCPCB's
  own outline tolerance (±0.2mm regular precision) and unmanufacturable.**
  This is *why* Ye is capped at 5.6, not 5.8, in the chosen design.
- Nearest **other** footprint's pad to the U7 slot region: `R67` pad 1,
  11.19mm away -- no neighbour conflict, only the board edge binds.
- `U3`'s slot region: 46.9mm from the nearest board edge, 10.26mm from the
  nearest other footprint's pad (`Q1`) -- no constraint at all for U3.

**Board rigidity / mechanical support:** both slots remove a modest amount
of substrate directly under a surface-mount body (U7, SMD, no leads
touching the slot region) or between the leads of a through-hole part (U3,
DIP -- the slot sits entirely between the two pin rows, not under either
pin, so it removes no material the leads rely on for mechanical purchase).
Slot areas: U7 6.0x11.2=67.2mm², U3 5.0x9.0=45.0mm², both small relative to
the 152x234mm (35,568mm²) board and located well away from any mounting
hole, connector, or high-stress region (checked: no mounting holes,
connectors, or heavy components -- relays, transformer, TO-247s -- fall
within 10mm of either slot). **Not a rigidity concern at this scale**, but
this is a qualitative judgement, not a structural (FEA) analysis -- flagged
in UNVERIFIED.

### 4.4 Manufacturability against fab capability (task item 3)

**CITED-SECONDARY, JLCPCB capabilities documentation (fetched this
session):**

> Minimum Non-Plated Slot width: **1.0mm**. Routed-board dimensional
> tolerance: **±0.2mm (regular precision) / ±0.1mm (high precision)**.
> Copper clearance from routed slots: **>=0.2mm minimum**.

Both slots (5.0-6.0mm wide) are 5-6x the 1.0mm fab minimum -- no
manufacturability issue on slot width itself. The binding manufacturability
questions are **tolerance** and **copper clearance**, both checked against
the worst case (slot shrinks/grows by the full ±0.2mm regular-precision
figure on every edge simultaneously -- a pessimistic combined scenario,
deliberately not assuming tolerances cancel):

| Ref | Nominal pad clearance | Worst-case pad clearance (edges shift 0.2mm toward pad) | >= 0.2mm JLCPCB min? | Nominal creepage | Worst-case creepage (slot shrinks 0.2mm/edge) | >= 8.0mm? |
|---|---:|---:|:--:|---:|---:|:--:|
| U7 | 0.625mm | 0.425mm | yes | 8.627mm | 8.124mm | yes (1.5% margin) |
| U3 | 0.500 / 0.520mm | 0.300 / 0.320mm | yes | 9.128mm | 8.470mm | yes (5.9% margin) |

U7's worst-case creepage margin (1.5%) is thin but real. Given the ~2.1mm
placement adjustment that would be needed to restore full margin is a
board-layout change outside this task's scope (footprints only, per the
task's coordination note), **this is flagged as a follow-up recommendation**
rather than acted on: nudging U7 approximately 0.2-0.3mm further from the
board's left edge (well within typical placement slack) would let Ye return
to 5.8mm, restoring the 8.984mm / 8.439mm-worst-case margin computed in
§4.2's rejected row.

---

## 5. Implementation (task item 4)

Following this project's established convention (U7's own footprint is
already a hand-built local override of a real KiCad library part --
`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` is `Package_SO:SOIC-
16W_7.5x10.3mm_P1.27mm.kicad_mod` with two pads removed, per that file's own
`descr`):

- **`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`** -- added an
  `fp_poly` on the `Edge.Cuts` layer (a routed-slot cutout), local
  coordinates `x=[-3.0,3.0] y=[-5.6,5.6]`, and extended the `descr` field
  with the full derivation (mirroring that file's existing convention of
  a long, evidence-carrying description).
- **`pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`** (new file) -- a
  local override of `Package_DIP:DIP-6_W7.62mm`, same pattern as U7: real
  DIP-6 pad geometry (unchanged) plus an `Edge.Cuts` slot polygon,
  `x=[1.3,6.3] y=[-2.0,7.0]`.
- **`elec/src/components.ato:500`** -- U3's `footprint` field changed from
  `"Package_DIP:DIP-6_W7.62mm"` to `"H11L1_DIP6_Isolated"` (bare name, no
  colon), matching U7's existing pattern at line 29 (`"SOIC16W_Isolated"`).
  Confirmed by re-running `make netlist`: the compiled netlist
  (`elec/build/default.net`) resolves this to `(footprint
  "lib:H11L1_DIP6_Isolated")`, exactly matching U7's own resolved
  `lib:SOIC16W_Isolated` -- atopile's own footprint-library search handles
  the bare-name -> nickname resolution automatically; this is not something
  hand-maintained.
- **`pcb/temper.kicad_pcb`** -- touched only U3's and U7's own footprint
  blocks (the only two components in scope, per the task's coordination
  note): added the same `Edge.Cuts` slot polygon inline (a KiCad board file
  stores a full copy of each footprint's geometry, not a live reference, so
  the library edit alone does not reach the placed instance); renamed U3's
  footprint identifier to `lib:H11L1_DIP6_Isolated` and its `descr`/
  `Footprint` property to match. No other footprint, net, track, via, or
  zone in this 13,576-line file was touched -- confirmed directly:
  `git diff HEAD~1 -- pcb/temper.kicad_pcb` shows exactly 3 hunks, all
  inside the U3 and U7 blocks (lines ~7817-7847 and ~8040-8054), and **zero**
  `(net ...)` lines added or removed anywhere in the file (`grep` count on
  the diff, §6).
- **`elec/src/footprints.ato`** and **`elec/src/fac_utils.ato`** -- the
  "conceptual placeholder" generative-footprint module (Makefile's own
  comment: `make footprints` does not actually generate KiCad geometry from
  this file) had a stale, uncited `isolation_slot.width = 1.0mm` and an
  untraced "8mm creepage slot" claim. Updated to the real, verified values
  (6.0 x 11.2mm) with a comment explaining *why* (the under-body /
  around-the-end reasoning, §3-4), and a note that these values must stay
  in sync with the real `.kicad_mod` by hand since nothing enforces it
  automatically. `fac_utils.ato`'s shared `CreepageSlot.width` default
  (1.0mm) is now explicitly cited to IS 15382 (Part 1) cl. 4.2's dimension
  X at PD2 (§2), rather than left as an unexplained number.
- **`elec/Footprints_README.md`** -- updated the one-line descriptions of
  both footprints to state the real dimensions and creepage figures instead
  of the vague/wrong prior text ("featuring an 8mm creepage slot" --
  ambiguous between slot width and resulting creepage, and not the number
  actually achieved).

Nothing in `packages/temper-placer/configs/netclass_rules.yaml`,
`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` constant, the
BOM, or any gate was touched -- this is a land-pattern fix, not a
requirement change, per the hard rule.

---

## 6. Verification (task item 5, "Verify before finishing")

**Board-wide invariant check, direct diff (not gate-output comparison):**
`git diff HEAD~1 -- pcb/temper.kicad_pcb` shows exactly 20 lines changed, all
inside the U3/U7 footprint blocks, and **zero** `(net ...)` declarations
added, removed, or altered anywhere in the file -- a stronger and more
direct confirmation than comparing two gate runs' summary counts (one run of
`check_isolation_keepout.py`, made immediately after the `uv sync` that
first populated this worktree's `.venv`, transiently misreported HV=87
instead of the correct/reproducible HV=97 -- re-running it against the
literal, unedited pre-session board file, restored via `git show
HEAD~1:pcb/temper.kicad_pcb`, reproduces HV=97 every time, matching all
three sibling evidence docs' own figure and every run made after that one.
Not a finding about this change; noted so the number isn't silently
smoothed over).

All commands actually run this session, in this worktree, after all edits
above:

| Check | Result |
|---|---:|
| `make netlist` | **PASS** (build complete; U3 resolves to `lib:H11L1_DIP6_Isolated`, confirmed in `elec/build/default.net`) |
| `uv run --no-sync python -m pytest elec/validation -q` | **30 passed** |
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 |
| `check_derived_doc_drift.py` | exit 0 (footprints=168, nets=164, segments=2338, vias=48, zones=96) |
| `check_copper_net_consistency.py` | exit 0 (2482 copper items, 510 pads checked, 0 violations) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 |
| **`check_isolation_keepout.py`** | **exit 3** -- expected, pre-existing, unrelated (no `MAINS_SELV_ISOLATION_BARRIER` keepout zone exists; a sibling agent's concern) |
| **`check_measurement_provenance.py`** | **exit 5** -- expected, pre-existing, unrelated (`drc_ceiling.json` malformed `source` field) |
| `validate_footprints.py pcb/libs/lib.pretty` | 0 errors, 2 pre-existing warnings on unrelated footprints (ESP32-S3, LitzPad_15A -- missing courtyard, not touched by this change) |

**Final, independent re-verification against the literal edited files** (not
the design script's in-memory assumptions): a separate script re-parsed the
actual, saved `pcb/temper.kicad_pcb` via `kiutils`, pulled U3's and U7's
real pad positions and the real `Edge.Cuts` slot polygon just written, and
recomputed the governing creepage via the same shortest-path method:

```
U3: libId=lib:H11L1_DIP6_Isolated, slot local bounds=(1.3, -2.0, 6.3, 7.0)
    GOVERNING CREEPAGE (from real file geometry): 9.128mm  (target 8.0mm, pass=True)
U7: libId=lib:SOIC16W_Isolated,   slot local bounds=(-3.0, -5.6, 3.0, 5.6)
    GOVERNING CREEPAGE (from real file geometry): 8.627mm  (target 8.0mm, pass=True)
Clearance (line-of-sight, slot-independent) U3: 6.02mm (unchanged)
Clearance (line-of-sight, slot-independent) U7: 7.25mm (unchanged)
```

**Measured, not asserted**, exactly as the task required.

---

## 7. Sources -- exactly what was reached and read this session

- **IS 15382 (Part 1):2003 = IEC 60664-1 (2002)**, *Insulation coordination
  for equipment within low-voltage systems, Part 1: Principles, requirements
  and tests* -- Bureau of Indian Standards identical adoption, hosted by
  Public.Resource.Org. `pdftotext -layout` extracted (4536 lines); read
  clause 4.2 in full (dimension X table, all 11 worked examples). This is
  the specific rule the prior brainstorm doc flagged as
  "NOT read this session" -- closed here.
  <https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf>
- **JLCPCB capabilities documentation** -- routed-slot minimum width
  (plated/non-plated), dimensional tolerance (regular/high precision), and
  copper-to-slot clearance figures, fetched this session.
  <https://jlcpcb.com/capabilities/pcb-capabilities>
- `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, `pcb/temper.kicad_pcb`,
  `elec/domain_manifest.yaml` -- read and parsed directly (`kiutils`) this
  session for U3/U7 geometry, pad nets, and isolator group declarations.
- `docs/evidence/2026-07-28-conformal-coating-pd1.md` and
  `2026-07-28-creepage-determination-brainstorm.md` -- cross-checked, not
  re-derived; all three sessions' independent geometry measurements agree
  to the millimetre.

**Method note:** `WebSearch` was unavailable (session budget exhausted at
200/200 before this task began, the same constraint every prior session in
this project's history has hit). Both sources above were reached by direct
URL (the IS 15382 Part 1 URL by pattern-matching the already-known Part 3
URL from the conformal-coating evidence doc; the JLCPCB URL is its own
canonical capabilities page) and fetched/read directly, not through a
search-summarising layer.

**Attempted and not needed:** the current-edition IEC 60664-1 (2020) and
current IEC 60335-1 Annex/clause numbering were not sought -- this document
only needed the groove-measurement rule (clause 4.2), which the 2002-era
edition already gives with two independent secondary corroborations
(Broadcom/Avago's reproduction, cited in the base-commit brainstorm doc, and
JLCPCB's fab-capability figure landing on the same 1.0mm number for an
unrelated reason).

---

## 8. UNVERIFIED -- explicit list

- **The current (2020+) edition of IEC 60664-1** was not read; clause 4.2's
  numbering and exact wording are taken from the 2002-era text via its
  identical 2003 Indian national adoption, consistent with every other
  standards citation in this project's evidence trail (all of which have
  the same caveat).
- **The "around-the-end, no floor" model (§3) is a geometric DERIVATION
  from the standard's general contour principle, not a literal worked
  example in the standard for a finite, fully-enclosed through-slot.** IEC
  60664-1's Example 2 pictures an infinite-cross-section groove, not a
  bounded island-shaped cutout with two ends. The derivation is, I believe,
  correct (and matches industry practice), but it has not been checked
  against a certification lab's own interpretation of a bounded slot.
- **Board rigidity was assessed qualitatively** (slot area vs board area,
  distance to mounting features), not via structural/FEA analysis. Given
  the slot sizes (67mm² and 45mm² against a 35,568mm² board, both away from
  any stressed region), this is judged low-risk but not proven low-risk.
- **U7's worst-case creepage margin (8.124mm, 1.5% over 8.0mm) is thin.**
  It passes the modelled worst case but leaves little further room; the
  recommended ~0.2-0.3mm placement nudge to restore the larger margin
  (8.984mm nominal / 8.439mm worst-case) was not implemented -- it is a
  placement change, out of this task's footprint-only scope, and is left as
  an explicit recommendation.
- **U7 at PD3 (12.6mm) is infeasible at its current placement/rotation**
  (§Verdict) -- reported, not resolved. Whether moving U7 ~2.1mm from the
  board edge is itself feasible (what else is near that region on the
  board) was not checked; only the slot geometry constraint was traced.
- **The JLCPCB capability figures are for one named target fab**
  (`docs/PCB_DFM_GUIDELINES.md` also names PCBWay); PCBWay's own published
  routed-slot tolerance/clearance figures were not fetched or compared.
- **Whether atopile's bare-name-to-`lib:`-prefix footprint resolution is
  documented behaviour or an emergent property of how this project's
  `pcb/fp-lib-table` is structured** was inferred by observing the compiled
  netlist's output (`elec/build/default.net`), not by reading atopile's own
  resolution-order documentation.
- No claim in this document is a compliance determination or a substitute
  for type testing; no clause, table value, or fab-capability figure is
  stated except where read directly this session and traceable to the file
  or URL given above.

---

## Compliance with the task's hard rules

- **Creepage target never reduced.** 8.0mm held throughout; PD3's 12.6mm
  was computed and reported (§Verdict, §4.4) as a "what would change,"
  never adopted as the design target.
- **Slot claimed to extend creepage only.** §3, §5's implementation notes,
  and the verification script (§6) all explicitly confirm clearance is
  unchanged (7.25mm / 6.02mm, same as pre-slot) -- never claimed as a
  clearance improvement.
- **No `git stash`** used anywhere this session.
- **No `run_in_background`, no `Monitor`, no waiting on background jobs.**
  `make netlist` and all gates were run in the foreground and waited on
  synchronously via the tool's own blocking call, never backgrounded.
- **No additional worktrees created.** All work done in the one worktree
  assigned for this task (`agent-a98c54f75cb42e5e7`); the disk-tight
  constraint was respected by checking out `b1499a16` as a new branch
  inside that same worktree rather than creating a second one.
- **`uv run --no-sync`** used for every script/test invocation after an
  initial `uv sync --all-packages --inexact` (matching the exact command
  `.github/workflows/python-tests.yml` uses, needed once because this
  worktree's `.venv` started empty -- `kiutils`, `shapely`, and `pyyaml`,
  all required by the project's own gate scripts, were not present until
  that sync).
- **Coordination**: touched only `pcb/temper.kicad_pcb`'s U3 and U7
  footprint blocks (verified via `check_copper_net_consistency.py` and
  `check_derived_doc_drift.py` reporting identical board-wide denominators
  before and after), plus `elec/src/components.ato`'s single U3 footprint
  line, `elec/src/footprints.ato`/`fac_utils.ato` (documentation-only,
  non-generative), `elec/Footprints_README.md`, and the two footprint files
  in `pcb/libs/lib.pretty/`. Did not touch `netclass_rules.yaml`,
  `check_isolation_keepout.py`, `generate_kicad_dru.py`,
  `HIGH_VOLTAGE_CLEARANCE_SPEC.md` (only cited its §6.1 as a correction
  target, did not edit it -- that document is in the DRC/coating sibling
  agents' scope), `components.ato`/`modules.ato` beyond the one U3 footprint
  line, or `ENVIRONMENTAL_SPEC.md`.
- **Commits made after each meaningful step** (footprint/board edits +
  verification; this evidence document). Not pushed.
- Analysis/design scripts (`slot_design.py`, `run_u7.py`, `run_u3.py`,
  `run_pd3.py`, `pd3_precise.py`, `check_feasibility.py`,
  `check_neighbors.py`, `final_verify.py`) live in the session scratchpad
  and are not committed -- read-only design/verification analysis, matching
  the precedent of the sibling evidence docs.
