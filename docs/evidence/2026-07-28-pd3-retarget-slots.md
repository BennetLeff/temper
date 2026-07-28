<!-- provenance: commit=fd6c9c15d61700ff034445a1b67d31190ef2c162 dirty=false -->

# Re-targeting U3/U7 creepage slots from 8.0mm (PD2) to 12.6mm (PD3)

Base commit: `fd6c9c15` (`merge: K2/K3 replaced with a DPDT part that closes
the DC-break gap too`), branch `docs/methodology-loop-discipline` per the
task's naming (that branch's own tip does not contain `fd6c9c15`, matching
the same base-commit-vs-branch-tip note the isolator-creepage-slots doc
already flagged for its own base commit `b1499a16` -- checked out directly
at `fd6c9c15` per the task's explicit instruction). Work done in worktree
`agent-aaec0ab36855ae931`, local branch `fix/pd3-retarget-u3-u7-slots`.

The 8.0mm/PD2 U3 and U7 slot designs already existed at `fd6c9c15`
(confirmed: `pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod` and
`SOIC16W_Isolated.kicad_mod` were both present with their slots, and
`elec/components.ato:500` already pointed U3 at the isolated footprint) --
this document re-targets that existing work, it does not originate it.

## Provenance labels (same convention as the two "READ FIRST" docs)

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched/read this session; URL in Sources. |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / the footprint files, script shown. |
| **DERIVED** | Arithmetic/geometry on labelled inputs, shown in full. |
| **ASSUMED** | Not established; flagged for a human. |

---

## FALSIFIER -- result

Stated exactly as the task posed it: *"Both slots can be extended to 12.6mm
within their existing footprints and the board outline. If U7 cannot, that
is a placement finding -- quantify the shortfall rather than shrinking the
target."*

**Partially fires, exactly as anticipated by the task's own framing.**
`U3` extends to 12.6mm cleanly within its existing footprint and the board
outline. `U7` cannot -- and this is a placement finding, quantified below,
not a target reduction. The 8.0mm target was never lowered anywhere in this
work.

## Verdict up front

| Ref | Slot (before -> after) | Nominal creepage | Worst-case (fab tolerance) | vs 12.6mm (PD3) | vs 8.0mm (PD2) |
|---|---|---:|---:|:--:|:--:|
| `U3` | 5.0x9.0mm -> **5.0x14.0mm** | **14.058mm** | **13.317mm** | **PASS** (11.6% / 5.7% margin) | PASS (both figures, larger margin) |
| `U7` | 6.0x11.2mm -> **unchanged** | 8.627mm | 8.124mm | **FAIL** (3.97mm short) | PASS (unchanged from the original design) |

**`U7`'s failure at PD3 is a placement constraint, independently
re-derived and quantified this session (Sec 3), not a footprint-geometry
limitation and not something this task's scope (footprints only) can fix.**
Reaching 12.6mm at `U7` requires a slot length of 15.37mm; the board's own
physical edge caps the achievable length at 11.2mm (Ye=5.6mm) given `U7`'s
current placement and 270-degree rotation. The required slot would begin
1.79mm past the board's own outline. Displacing `U7` ~2.09mm away from the
board's left edge (independently re-derived; the sibling design session
found ~2.1mm) would resolve it, but that is a placement change, out of this
footprint-only task's scope, and is reported as a recommendation rather than
acted on.

---

## 1. PD3 minimum groove width X -- established from primary text before designing anything (task item 1)

**CITED-PRIMARY, IS 15382 (Part 1):2003 = IEC 60664-1 (2002), clause 4.2**
-- re-fetched and independently re-read this session (not inherited from the
isolator-creepage-slots doc's own citation of the same clause), via
`pdftotext -layout` on the same archived PDF:
<https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf>. `WebFetch`
could not parse the raw PDF stream directly (it returned "unable to locate
readable content" against the binary), so the already-fetched PDF (saved to
this session's tool-results cache by the `WebFetch` call itself) was
extracted locally with `pdftotext -layout` and read as text, matching the
project's established method for this exact document.

Quoted verbatim, clause 4.2 (line 3138 of the extracted text):

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

And the two governing worked examples, independently re-confirmed against
the same text (lines 3170-3208):

> **Example 1** -- "Path under consideration includes a parallel- or
> converging-sided groove of any depth with a width less than X mm. Rule:
> Creepage distance and clearance are measured directly across the groove as
> shown."
>
> **Example 2** -- "Path under consideration includes a parallel-sided
> groove of any depth and equal to or more than X mm. Rule: Clearance is the
> 'line of sight' distance. Creepage path follows the contour of the
> groove."

**DERIVED: at PD3, X = 1.5mm** is the governing minimum groove width --
**up from 1.0mm at PD2**, confirming the task's own suspicion that this
constant plausibly changes at PD3 and should not be reused verbatim from the
PD2-era design. It does change, by exactly the ratio the standard's own
table implies (1.5x).

**Consequence for both slots: neither is bound by this floor at either
pollution degree.** `U3`'s 5.0mm slot width exceeds 1.5mm (PD3) by **3.3x**;
`U7`'s 6.0mm slot width exceeds it by **4.0x**. The groove-width minimum is
not the reason `U7` fails at PD3 -- board-edge placement is (Sec 3). This
closes the task's own flagged risk ("using the PD2 figure at PD3 would be
exactly the kind of stale-constant error this project keeps finding") by
showing the correct PD3 figure and showing it does not change either
verdict.

---

## 2. `U3` extended to 12.6mm (task item 2)

### 2.1 Method

Independent visibility-graph shortest-path script, written this session,
not copied from the isolator-creepage-slots session's own (uncommitted,
session-scratchpad) script. Same method as that prior determination,
re-derived from first principles and cross-checked:

1. Model each pad's inner (creepage-facing) edge as a point in the
   footprint's local coordinate frame (the mid-point of the pad's edge
   nearest the opposite domain -- e.g. for `U3`'s HV pads at local x=0,
   size 1.6mm, the inner edge point is at x=0.8).
2. Model the candidate slot as an axis-aligned rectangle obstacle.
3. Build a visibility graph per HV<->SELV pad-edge pair: nodes are the two
   pad points plus the slot's 4 corners; an edge between two nodes exists
   iff the straight segment between them does not cross the slot
   rectangle's **interior** (grazing a corner or running along an edge is
   allowed -- implemented as intersection-testing against a `shapely`
   `buffer(-1e-6)`-eroded copy of the slot polygon, which is true interior
   penetration and excludes boundary grazes by construction).
4. Dijkstra shortest path (`networkx`) between the two pad points over that
   graph; the governing creepage is the **minimum** over all HV<->SELV pairs
   (6 pairs for `U3`: 2 HV x 3 SELV, matching the isolator groups in
   `elec/domain_manifest.yaml`'s `power_in.zcd_opto` entry -- primary=[1,2],
   secondary=[4,5,6], pin 3 unused, exactly as the prior determination
   classified it).

**Sanity check against the existing 8.0mm design's own published figures**
(exact reproduction, independent implementation): `U3`'s existing
5.0x9.0mm slot (x=[1.3,6.3], y=[-2.0,7.0]) computes to **9.128mm** by this
script -- matches `docs/evidence/2026-07-28-isolator-creepage-slots.md`'s own
figure to the third decimal. A negligible-size slot at the real pad gap
reproduces the pre-slot baseline **6.020mm** exactly. `U7`'s existing
6.0x11.2mm design reproduces **8.627mm** exactly, and its pre-slot baseline
reproduces **7.250mm** exactly. This gives high confidence the independent
re-implementation is computing the same thing the prior session computed,
not coincidentally agreeing with the design intent.

### 2.2 Extension design

`U3` sits far from any board edge or neighbouring copper (Sec 2.3), so
unlike `U7` no placement cap applies -- the only question is how much Y
(slot length) is needed. X (slot width, pad-to-slot clearance) was left
unchanged.

Bisection (extending the existing slot's Y-range symmetrically on each end,
same shape convention as the original design) against the **worst-case**
figure (not just nominal, since a design that clears 12.6mm nominal but not
under fab tolerance would repeat exactly the kind of thin-margin problem the
prior session flagged for `U7`):

| Slot y-range (local) | Length | Nominal | Worst-case (JLCPCB +/-0.2mm/edge) | Worst-case >= 12.6mm? |
|---|---:|---:|---:|:--:|
| [-3.0, 8.0] | 11.0mm | 11.086mm | 10.377mm | FAIL |
| [-3.5, 8.5] | 12.0mm | 12.074mm | 11.351mm | FAIL |
| [-4.0, 9.0] | 13.0mm | 13.065mm | 12.332mm | FAIL |
| [-4.2, 9.2] | 13.4mm | 13.462mm | 12.725mm | PASS |
| **[-4.5, 9.5]** | **14.0mm** | **14.058mm** | **13.317mm** | **PASS (chosen)** |

**Chosen design: 5.0 x 14.0mm slot** (x=[1.3,6.3] unchanged, y=[-4.5,9.5],
was y=[-2.0,7.0]) -- **14.058mm nominal (11.6% margin over 12.6mm), 13.317mm
worst-case (5.7% margin)**. This margin philosophy matches the original
8.0mm design's own choice for `U3` (14.1% nominal / 5.9% worst-case margin
over 8.0mm there) rather than the thinner margin the original design
accepted for `U7` -- deliberately, since `U3` has no placement constraint
forcing a thinner margin here.

Pad-to-slot copper clearance is **unchanged** from the original design
(0.500mm HV-side / 0.520mm SELV-side nominal, 0.300mm/0.320mm worst-case,
both still >= JLCPCB's 0.2mm minimum) because only the Y-extent moved -- the
X-extent that sets this figure was not touched. Note this worst-case
direction is the **opposite** of the creepage worst-case: pad-clearance
worst-case models each X edge shifting 0.2mm *toward* its adjacent pad
(worst case for manufacturability), while creepage worst-case models the
whole slot shrinking 0.2mm/edge (worst case for the creepage path length).
These are two independent fab-tolerance failure modes; conflating them
would be an error (caught and corrected during this session -- an earlier
draft mistakenly applied the shrink-model to the pad-clearance figure too
and got 0.700mm/0.720mm, which is the *wrong* direction for that check).

### 2.3 Board-edge and neighbour feasibility (task item 2, manufacturability)

MEASURED, `U3` at board position `(118.82, 107.02, 0)` (no rotation, so
local Y maps directly to global Y), board outline `Edge.Cuts` at
`(20,20)-(172,254)`:

- Absolute slot bounding box after extension: x=[120.12,125.12],
  y=[102.52,116.52].
- Clearance to board edges: **left 100.12mm, right 46.88mm, top 82.52mm,
  bottom 137.48mm** -- no constraint anywhere close to binding.
- Nearest other footprint's pad: `Q1` (SOT-23, `power_in.q_relay_drv`) at
  board position `(125.71, 125.86)`. Distance from the slot's bounding box
  to `Q1`'s pad centre: **9.36mm** (was 10.26mm before the Y-extension,
  since the extension moves the slot's near end 2.5mm closer to `Q1` on the
  +Y side -- still two orders of magnitude above JLCPCB's 0.2mm minimum
  copper-to-slot clearance, not a real constraint).

**No placement-driven size cap applies to `U3`.** The design is bound only
by the margin choice made in Sec 2.2, not by board geometry.

### 2.4 Final, independent re-verification against the literal edited files

Per the task's instruction ("Verify final creepage by independently
re-parsing the edited footprint files, not by asserting the design intent"),
a separate script parsed the actual, saved `pcb/temper.kicad_pcb` via
`kiutils.board.Board`, pulled `U3`'s real pad positions/sizes/nets and the
real `Edge.Cuts` slot polygon just written, and recomputed governing
creepage independently of the design script:

```
U3: libId=lib:H11L1_DIP6_Isolated, slot local bounds=(1.3, 6.3, -4.5, 9.5)
    GOVERNING CREEPAGE (from real file geometry): 14.0576mm  (PD3 target 12.6mm, pass=True)
Clearance (line-of-sight, slot-independent) U3: 6.020mm (unchanged)
```

Matches the design script's figure to the fourth decimal, and confirms
clearance (the through-air, slot-independent figure) is unchanged at
6.020mm -- **the slot extended creepage only**, per the hard rule.

---

## 3. `U7`'s verdict: a placement finding, quantified (task item 3)

### 3.1 The board-edge constraint, independently re-derived

MEASURED/DERIVED, `U7` at board position `(25.9, 26.43, 270)`, board left
`Edge.Cuts` edge at absolute x=20.0mm. The rotation transform was derived
from first principles (not assumed) and confirmed against the existing
design's own published figures: for a 270-degree footprint rotation,
`global_x = at_x + local_y` and `global_y = at_y - local_x`. Checked: at
`local_y = -5.6` (the existing design's slot half-length), this predicts
`global_x = 25.9 - 5.6 = 20.3`, matching the isolator-creepage-slots
document's own reported "0.3mm clearance to the board's left edge" exactly;
at `local_y = -5.8` it predicts `global_x = 20.1`, matching that document's
"0.1mm clearance... unmanufacturable" exactly. Both independent
confirmations passed before this transform was relied on for anything new.

### 3.2 What 12.6mm actually requires

Bisection (same visibility-graph method as Sec 2.1) on the slot half-length
Ye, holding the slot's X-extent fixed at the existing design's
`[-3.0,3.0]`:

**Ye = 7.6853mm required for 12.6mm nominal creepage (slot length
15.3705mm).** This independently reproduces the isolator-creepage-slots
document's own bisected figure ("15.37mm... by bisection") to the fourth
significant figure -- two independent implementations, same answer.

At that Ye, the slot's near end reaches absolute
`x = 25.9 - 7.6853 = 18.2147mm` -- **1.7853mm past the board's own physical
edge at x=20.0mm.** This is not a fab-tolerance-scale shortfall; it is
nearly 2mm, an order of magnitude beyond any manufacturing tolerance in
play elsewhere in this document (JLCPCB's own +/-0.2mm).

### 3.3 The achievable maximum, and how short it falls

| Ye | Board-edge clearance | Creepage achieved | vs 12.6mm |
|---:|---:|---:|---:|
| 5.6mm (current design, 0.3mm clearance convention) | 0.3mm | 8.627mm | **3.97mm short** |
| 5.9mm (theoretical, **zero** clearance -- unmanufacturable) | 0.0mm | 9.167mm | **3.43mm short** |
| 7.685mm (required for 12.6mm) | **-1.785mm (past the edge)** | 12.600mm | -- |

**Even the unmanufacturable zero-clearance limit falls 3.43mm short of
12.6mm.** This is decisively a placement problem, not a fab-tolerance or
groove-width problem -- no achievable slot at `U7`'s current location and
rotation, however aggressively sized, reaches 12.6mm.

### 3.4 What would fix it, quantified

Displacement of `U7` away from the board's left edge needed to fit the full
15.37mm slot at the same 0.3mm edge-clearance convention the original
design used:

```
required_clearance(0.3mm) = (at_x + displacement) - Ye_required - 20.0 = 0.3
displacement = 0.3 - (25.9 - 7.6853 - 20.0) = 2.0853mm
```

**~2.09mm of displacement away from the board's left edge**, independently
re-derived here and matching the isolator-creepage-slots document's own
figure ("~2.1mm placement adjustment") almost exactly (the 0.015mm
difference is rounding in that document's own bisection precision, not a
disagreement in method). This is a **placement change** -- moving a
component, not editing a footprint -- and is out of this task's explicit
scope (footprints only, per the coordination note: "Your files:
`pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`,
`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`... Coordinate carefully if
you must touch `pcb/temper.kicad_pcb`" -- footprint content, not
placement). It is reported as a recommendation for whoever owns placement,
not acted on.

### 3.5 Decision: `U7`'s footprint geometry is left unchanged

`U7`'s slot (6.0 x 11.2mm, Ye=5.6mm) is **already at the maximum feasible
extent for its current placement** at the established 0.3mm board-edge
clearance convention. There is no larger slot to design within this
footprint-only task's scope that would move the PD3 number at all
materially (Sec 3.3 shows even the unmanufacturable zero-clearance extreme
only adds 0.54mm). Re-deriving and publishing a marginally larger slot
(e.g. Ye=5.7 at 0.2mm bare-fab-minimum clearance) would not change the
verdict and would erode the manufacturability margin for no real benefit --
so the existing design (nominal 8.627mm, worst-case 8.124mm, both still
comfortably clearing the superseded 8.0mm/PD2 target) is left in place, and
this document records the PD3 shortfall instead of forcing a slot that
cannot reach the target. Per the hard rule ("never reduce the creepage
target to make a slot fit"), the 12.6mm target itself was never lowered
anywhere in this analysis to manufacture a false pass.

---

## 4. If PD2 governs after all (task item 4)

A sibling agent is evaluating whether IEC 60335-2-6 clause 29.2's exception
("unless the insulation is enclosed or located so that it is unlikely to be
exposed to pollution during normal use of the appliance") applies to this
design -- i.e., whether PD2 (8.0mm) can be earned instead of PD3 (12.6mm)
governing by default, per the base-commit brainstorm doc's own finding that
PD3 is the standard's default for this appliance class absent such an
argument.

**Both answers are usable from the numbers already established in this
document, without any further design work:**

| If PD2 governs (8.0mm) | If PD3 governs (12.6mm) |
|---|---|
| `U3`: **PASS**, 14.058mm nominal / 13.317mm worst-case (75.7%/66.5% margin -- far more than needed, since the design was sized for 12.6mm, not 8.0mm) | `U3`: **PASS**, same figures, 11.6%/5.7% margin |
| `U7`: **PASS**, 8.627mm nominal / 8.124mm worst-case (unchanged from the original design, 7.8%/1.5% margin) | `U7`: **FAIL**, 3.97mm short -- placement finding, Sec 3 |

**If PD2 governs, no further change is needed anywhere** -- `U3`'s larger
slot is simply oversized relative to the requirement (harmless: a slot
extends creepage only, and a bigger creepage margin is never a safety
problem, only a modest, already-accepted amount of extra routed board area,
70mm² against 168mm² previously, both negligible against the 35,568mm²
board per the rigidity assessment in the original design doc). **If PD3
governs, `U3` is already compliant and `U7` needs the placement change
quantified in Sec 3.4** (or a different remedy this document does not
select between -- board outline extension, a different part, or accepting
`U7` as a residual finding pending a placement pass). This document does
not resolve which pollution degree governs; it ensures the geometry data
needed for either resolution already exists and is verified.

---

## 5. Implementation (files touched)

Per the task's explicit file-scope note ("Your files:
`pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`,
`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, and your evidence doc.
Coordinate carefully if you must touch `pcb/temper.kicad_pcb`"):

- **`pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`** -- `fp_poly`
  Edge.Cuts slot extended from `x=[1.3,6.3] y=[-2.0,7.0]` (5.0x9.0mm) to
  `x=[1.3,6.3] y=[-4.5,9.5]` (5.0x14.0mm); `descr` field updated with the
  full PD3 derivation, the corrected groove-width citation (1.5mm at PD3),
  and the corrected pad-clearance worst-case figures.
- **`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`** -- geometry
  **unchanged** (already at its maximum feasible extent); `descr` appended
  with the PD3 placement-infeasibility finding, the quantified shortfall,
  and a pointer to this document.
- **`pcb/temper.kicad_pcb`** -- touched only `U3`'s and `U7`'s own footprint
  blocks (the only two components in scope): `U3`'s `fp_poly` slot
  coordinates updated to match the library file exactly, and both
  components' `descr` fields updated to match their respective library
  files' new text. **Zero `(net ...)` lines added, removed, or altered
  anywhere in the 13,000+-line file** (confirmed by direct `grep` count on
  the diff: 0). `git diff HEAD~1 -- pcb/temper.kicad_pcb` shows exactly 3
  hunks (2 `descr` edits + 1 `fp_poly` coordinate edit), all inside the `U3`
  and `U7` blocks.

Nothing in `elec/domain_manifest.yaml`, `elec/src/components.ato`,
`packages/temper-placer/configs/netclass_rules.yaml`,
`scripts/check_isolation_keepout.py`, `scripts/generate_kicad_dru.py`, or
`pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` was touched --
those are explicitly out of scope (owned by sibling agents or not required
by this task).

---

## 6. Verification (task's "Verify before finishing")

All commands run this session, in this worktree, after the footprint edits,
in the order the task specified:

| Check | Result |
|---|---:|
| `make netlist` | **PASS** (build complete) |
| `uv run --no-sync python -m pytest elec/validation -q` | **30 passed** |
| `check_domain_partition.py` | exit 0 (60 declared nets / 2 domains, 10 isolators, 168 components; 0 domain crossings, 0 barrier breaches) |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 (118 parts inspected, 0 new violations) |
| `check_derived_doc_drift.py` | exit 0 (footprints=168, nets=164, segments=2338, vias=48, zones=96) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (9/10 fresh; 1 missing extension unrelated to this change, `TEMPER_REQUIRE_FRESH_EXTENSIONS` unset locally) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 (4/4 checks agree) |
| **`check_isolation_keepout.py`** | **exit 3** -- expected per the task; pre-existing (no `MAINS_SELV_ISOLATION_BARRIER` keepout zone exists anywhere on the board; unrelated to this change, a sibling agent's concern) |
| **`check_measurement_provenance.py`** | **exit 5** -- expected per the task; pre-existing (`drc_ceiling.json`'s `source` field is malformed, unrelated to this change) |
| **`check_copper_net_consistency.py`** | **FAILED, exit 3, 146 violations -- confirmed pre-existing, not caused by this change.** All 146 violations trace to `power_in.ntc-no` and `discharge.k_dis1-nc`/`k_dis2-nc` net-name mismatches from the K2/K3 relay replacement (commit `56173aa1`, already present at the base commit `fd6c9c15` this task started from), pending a board resync unrelated to U3/U7. Verified directly: `git show HEAD~1:pcb/temper.kicad_pcb \| grep -c 'discharge.k_dis1-nc\|power_in.ntc-no'` returns 9 matches in the **pre-my-commit** board file, and `git diff HEAD~1 -- pcb/temper.kicad_pcb` touches zero lines containing either net name. |
| `validate_footprints.py pcb/libs/lib.pretty` | 0 errors, 2 pre-existing warnings on unrelated footprints (`ESP32-S3-WROOM-1`, `LitzPad_15A` -- missing courtyard, not touched by this change) |

**Final, independent re-verification against the literal edited files**
(Sec 2.4 above), re-parsed via `kiutils` directly from the saved
`pcb/temper.kicad_pcb`, not asserted from design intent:

```
U3: libId=lib:H11L1_DIP6_Isolated, slot local bounds=(1.3, 6.3, -4.5, 9.5)
    GOVERNING CREEPAGE (from real file geometry): 14.0576mm  (PD3 target 12.6mm, pass=True)
U7: libId=lib:SOIC16W_Isolated,   slot local bounds=(-3, 3, -5.6, 5.6)
    GOVERNING CREEPAGE (from real file geometry): 8.6265mm  (PD3 target 12.6mm, pass=False)
    U7 vs superseded PD2 8.0mm target: pass=True
Clearance (line-of-sight, slot-independent) U3: 6.020mm (unchanged)
Clearance (line-of-sight, slot-independent) U7: 7.250mm (unchanged)
```

---

## 7. Sources -- exactly what was reached and read this session

- **IS 15382 (Part 1):2003 = IEC 60664-1 (2002)** -- Bureau of Indian
  Standards identical adoption, hosted by Public.Resource.Org. `WebFetch`
  could not parse the raw PDF stream (it explained it could see only
  binary/compressed content, not readable text); the PDF it had already
  retrieved was extracted locally with `pdftotext -layout` (4536 lines) and
  clause 4.2 (including the PD1/PD2/PD3 dimension-X table and Examples 1-2)
  was read directly from that text. This is an independent re-fetch and
  re-read of the same clause the isolator-creepage-slots document already
  cited for PD2 -- not inherited -- specifically to establish the PD3 row,
  which that prior document did not need and did not read.
  <https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf>
- `pcb/libs/lib.pretty/H11L1_DIP6_Isolated.kicad_mod`,
  `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, `pcb/temper.kicad_pcb`,
  `elec/domain_manifest.yaml` -- read and parsed directly (`kiutils`) this
  session for `U3`/`U7` geometry, pad nets, and isolator group
  declarations.
- `docs/evidence/2026-07-28-isolator-creepage-slots.md`,
  `docs/evidence/2026-07-28-coating-supplemental-scope.md`,
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` -- read in
  full per the task's "READ FIRST" instruction; cross-checked (independent
  re-derivation reproduced their published figures exactly, Sec 2.1, 3.1),
  not blindly re-cited.

**Method note:** `WebSearch` was not attempted (the task stated its budget
is exhausted and to reason to direct URLs, consistent with every prior
session in this project's history). The one direct-URL fetch needed
(the already-known IS 15382 Part 1 URL, reused from the prior session's own
citation) succeeded via `WebFetch` + local `pdftotext` extraction of the
binary it retrieved.

---

## 8. UNVERIFIED -- explicit list

- **The current (2020+) edition of IEC 60664-1** was not read; clause 4.2's
  PD3 dimension-X figure (1.5mm) is taken from the 2002-era text via its
  identical 2003 Indian national adoption, consistent with every other
  standards citation in this project's evidence trail (same caveat as all
  of them).
- **`U3`'s new 14.0mm slot length was not re-checked for board rigidity
  beyond the qualitative area/proximity argument** already established for
  the original 9.0mm design (5.0x14.0mm = 70mm² vs the board's 35,568mm²,
  still no mounting hole/connector/heavy-component within the same 10mm
  radius the original design checked) -- a proportionally small increase
  (55mm² more slot area), not independently re-verified via FEA, matching
  the same caveat the original design flagged for itself.
- **The 0.3mm board-edge clearance convention** used throughout Sec 3
  (and inherited from the original `U7` design) is this project's own
  choice, not a cited fab-capability minimum (JLCPCB's own stated minimum is
  0.2mm/±0.2mm outline tolerance -- 0.3mm was the original design's margin
  choice above that, and this document did not re-litigate whether a
  smaller margin convention is defensible, since Sec 3.3 shows it would not
  change `U7`'s verdict either way).
- **Whether displacing `U7` ~2.09mm is itself feasible** (what else sits
  near that region of the board) was not checked -- this document only
  traces the slot-geometry constraint and quantifies the displacement that
  would resolve it, per the task's instruction to report this as a
  placement finding rather than resolve it.
- **Which pollution degree ultimately governs** (PD2 via an enclosure
  argument, or PD3 by default) is explicitly left to the sibling agent's
  determination, per the task's own framing; this document supplies both
  outcomes' figures (Sec 4) rather than picking one.
- No claim in this document is a compliance determination or a substitute
  for type testing; no clause, table value, or fab-capability figure is
  stated except where read directly this session and traceable to the file
  or URL given above.

---

## Compliance with the task's hard rules

- **Creepage target never reduced.** 12.6mm was the target held throughout
  for both parts; `U7`'s shortfall against it is reported, not
  papered over by lowering the target or by silently re-adopting 8.0mm as
  if it were still governing.
- **Slot extends creepage only.** `U3`'s clearance figure (6.020mm,
  line-of-sight, slot-independent) is confirmed unchanged in the final
  independent re-parse (Sec 2.4/6) -- never claimed as a clearance
  improvement.
- **No `git stash` used with any actual effect.** One `git stash` invocation
  was run by mistake while investigating the copper-net-consistency gate
  (before realising `git show HEAD~1:...` was the correct, non-destructive
  way to inspect the pre-commit board file); it reported "No local changes
  to save" because everything was already committed at that point, so no
  stash entry was created and the shared stash ref was not touched. Noted
  here rather than silently omitted, per this project's own honesty
  convention, even though it had no effect. All actual pre/post-commit
  comparisons in this document use `git show`/`git diff`, not stash.
- **No `run_in_background` used for anything waited on.** One `uv run`
  invocation exceeded the foreground tool's 120-second timeout and was
  automatically moved to a background task by the harness; it was
  immediately stopped (`TaskStop`) without reading any of its output, and
  the underlying script was rewritten (an O(n·2000-sample) point-sampling
  geometry check replaced with an O(1) analytic eroded-polygon
  intersection test) and re-run to completion in the foreground within the
  timeout. No background job was waited on or relied upon for any result
  in this document.
- **No additional worktrees created.** All work done in the one worktree
  already assigned (`agent-aaec0ab36855ae931`), checking out `fd6c9c15` as a
  new local branch (`fix/pd3-retarget-u3-u7-slots`) rather than creating a
  second worktree, matching the precedent the isolator-creepage-slots
  session set for the same disk-tight constraint.
- **`uv run --no-sync`** used for every script/test invocation after one
  `uv sync --all-packages --inexact` (this worktree's `.venv` did not exist
  until this session created it; disk headroom was confirmed at 29GiB free
  beforehand).
- **Coordination**: touched only `pcb/temper.kicad_pcb`'s `U3` and `U7`
  footprint blocks (verified via direct diff: 3 hunks, 0 net lines changed,
  and via `check_domain_partition.py`/`check_derived_doc_drift.py`
  reporting identical board-wide denominators before and after). Did not
  touch `scripts/generate_kicad_dru.py`, `scripts/check_isolation_keepout.py`,
  or `pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` -- all
  explicitly owned by sibling agents per the task.
- **Commits made after each meaningful step**: the footprint/board edits (one
  commit, `5ef309d8`), and this evidence document (a second commit, see git
  log). Not pushed.
- Analysis/design scripts (`pd3_slot_design.py`, `pd3_full.py`,
  `final_verify.py`) live in the session scratchpad and are not committed --
  read-only design/verification analysis, matching the precedent of the
  sibling evidence docs.
