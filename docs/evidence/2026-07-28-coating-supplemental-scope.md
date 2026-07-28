<!-- provenance: commit=b1499a16 dirty=false -->

# Conformal coating as a supplement: the body-free scope, the temperature
# it must survive, and the pollution-degree default it depends on

Base commit: `b1499a16` (`merge: reconcile with concurrent session before
push`), branch `docs/methodology-loop-discipline`. Work done in worktree
`agent-aebce148126fe4dcc`, checked out directly at that commit on a local
branch `coating-supplemental-scope` (the shared branch had moved 12 commits
ahead by the time this session started; this file targets the commit named
in the task, not the branch tip).

**This is a determination and one correction.** Files touched:
`docs/ENVIRONMENTAL_SPEC.md` (PD2 -> PD3 default, cited) and this evidence
file. No BOM, no `netclass_rules.yaml`, no `check_isolation_keepout.py`
constant, no `pcb/temper.kicad_pcb`, no `generate_kicad_dru.py`, no
`HIGH_VOLTAGE_CLEARANCE_SPEC.md` (three sibling agents own those).

**What is already settled, and not re-litigated here:** conformal coating
cannot fix any of the eight declared mains<->PELV isolator paths --
`docs/evidence/2026-07-28-conformal-coating-pd1.md` measured 100.0% of the
shortest HV<->PELV surface path under the component body for every isolator
with a body outline. This document's scope is the part of that prior
determination the task asked me to establish myself rather than inherit:
the paths that cross no body at all, the temperature the coating (or any
future coating) must survive, and the pollution-degree default that governs
every path this repo has not covered.

## Provenance labels (same convention as the prior two determinations)

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched and read by me this session; URL in Sources. |
| **CITED-SECONDARY** | Manufacturer/vendor document, fetched and read by me this session. |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / `elec/domain_manifest.yaml` / repo docs; script or grep shown. |
| **DERIVED** | Arithmetic or logic on labelled inputs, shown in full. |
| **ASSUMED** | Not established. Flagged for a human. |

---

## Verdict up front

**The falsifier partially fires.** Stated exactly as the task posed it:

> *"Coating is worth specifying as a supplement for the body-free paths. If
> those paths already meet the requirement without it, or if the
> qualification burden (thermal, masking, production verification) exceeds
> its value for a partial subset, then the honest recommendation is not to
> coat -- and to fix those paths by layout instead."*

**Split result, established this session:**

1. **A body-free supplement zone is real** -- MEASURED independently this
   session, own script, own denominators (Sec 1): **102 of 202** sub-12.6mm
   cross-domain pad pairs cross no component body. For that subset, coating
   is a genuine, clause-backed, and -- unlike the isolator case --
   **visually verifiable** remedy (UV-tracer inspection works on open
   surface; it cannot see under a body, which is exactly why the isolator
   paths were unfixable and exactly why this subset is different).
2. **But five of those pairs fail even under a perfect PD1 coating** --
   MEASURED this session, all five under 2.0mm (the reinforced-at-PD1
   figure). Coating cannot rescue a sub-2.0mm gap; those five need a layout
   fix regardless of any coating decision. This is the falsifier's first
   trigger condition, and it fires for that cluster specifically.
3. **The qualification burden is real and, for two of the four common
   chemistries examined, exceeds the margin available.** No PCB working
   surface temperature has ever been declared in this repo (confirmed
   again, Sec 2). The defensible figure derived here -- 100 degC -- selects
   IEC 60664-3 Table 2's 125 degC/1000h dry-heat row. Acrylic and
   polyurethane have zero margin against that row; **Parylene C and
   Parylene D, freshly sourced this session, are also insufficient against
   it** (continuous service temperatures of 80 degC and 100 degC
   respectively, both below the 125 degC test). Only silicone-modified
   acrylic and Parylene HT have real headroom, and both carry known process
   penalties already flagged in the prior determination.
4. **For the remaining ~95-97 body-free pairs strictly between 2.0mm and
   12.6mm, coating remains legitimate and is the only remedy that does not
   require re-layout** -- provided the thermal qualification (now shown to
   need the 125 degC row, not a lighter one) and the masking programme
   (Sec 5 -- all three relays, not just two, are now shown to be
   non-sealed) are actually carried out, not assumed.

**Net: do not adopt coating by default, and do not present it as covering
"116 of 222" (or any precise count) without the caveat that the count
itself is sensitive to implementation choices (Sec 1.3) and that several of
the tightest members of that set fail regardless of coating (Sec 1.4). Fix
the five sub-2.0mm pairs by layout unconditionally. Treat coating as a
possible supplement for the rest only if the thermal and masking burden
established here is accepted, not assumed away.**

---

## 1. Establishing the body-free count myself

### 1.1 Method

Independent script, written this session, not copied from or derived by
reading either prior determination's scratchpad (neither exists in this
worktree -- both were session-local and uncommitted, per this project's own
stated convention for read-only analysis). Script:
`measure_coating_scope.py` (session scratchpad, not committed).

1. Load `domains.HV.nets` (21 nets) and `domains.SELV.nets` (33 nets) from
   `elec/domain_manifest.yaml`. Classification is exact net-name membership,
   never substring match.
2. Parse `pcb/temper.kicad_pcb` with `kiutils.board.Board` (the same library
   `check_isolation_keepout.py`, `resync_pcb_netlist.py`, and
   `check_copper_net_consistency.py` use).
3. Model every pad as an axis-aligned rectangle: rotate the pad's local
   corners by the footprint's placement angle and take the bounding box.
   MEASURED this session: **every footprint on this board is rotated by an
   exact multiple of 90 degrees** (0 degrees: 69, 90 degrees: 44, 180
   degrees: 32, 270 degrees: 23 -- 168 total), and no footprint is on the
   back layer (0 flipped), so this is exact, not approximate, everywhere on
   this board, not just for the eight isolators the prior determination
   checked.
4. Extract each footprint's body-outline bounding box from `F.Fab` graphics,
   falling back to `F.SilkS` then `F.CrtYd` (same fallback order as the
   prior determination).
5. For every HV-pad/SELV-pad rectangle pair, compute the minimum
   rectangle-to-rectangle Euclidean gap (0 if overlapping) and keep pairs
   under 12.6mm.
6. For each such pair, sample 400 points along the straight segment between
   the two rectangles' closest approach and test whether any sample point
   falls inside **any** footprint's body box (not just the two footprints
   owning the pads).

### 1.2 Denominators reproduce exactly

| Quantity | This session | Prior determination | Match? |
|---|---:|---:|---|
| Footprints | 168 | 168 | Yes |
| Footprints with a usable body outline | 161 | 161 | Yes |
| HV pads (net-classified) | 97 | 97 | Yes |
| SELV pads (net-classified) | 221 | 221 | Yes |
| All eight isolator shortest-path gaps | C6 3.200, K1 8.000, K2 3.500, K3 3.500, PS1 35.500, T1 9.100, U3 6.020, U7 7.250 | identical, to the mm | Yes, bit-for-bit |
| The four R30<->R1 sub-2mm gaps (Verdict item 3 of the prior doc) | 1.100, 1.124, 1.148 (matched); a 4th, R30.2<->R1.2, at 5.442mm (above 2mm, correctly not in that table) | 1.100, 1.124, 1.148 | Yes, to 3 decimals |

Every one of these independently reproduces the prior determination's
figures exactly. This is strong evidence the underlying geometry engine
(net classification, rotation handling, rectangle model) is sound and that
the two scripts agree wherever they've been directly spot-checked.

### 1.3 The aggregate count does not reproduce exactly -- reported honestly, not smoothed over

| Threshold | This session | Prior determination |
|---:|---:|---:|
| 2.0mm | **5** | 4 |
| 5.0mm | 24 | 23 |
| 5.6mm | 26 | 27 |
| 8.0mm | 66 | 68 |
| 12.6mm | **202** (100 crossing a body, **102 body-free**) | 222 (106 crossing, **116 body-free**) |

The two implementations agree exactly on every value checked at the
per-pair level (Sec 1.2) and disagree by roughly 9-12% on the full
board-wide aggregate. I looked for the source of the discrepancy rather than
just reporting it: pad shapes, pad-level rotation (`pad.position.angle` is
0 for all 519 pads on this board -- MEASURED, checked), footprint flip
state (0 flipped -- MEASURED), and custom/zero-size pads (none exist --
MEASURED) are all ruled out as causes. What I can show concretely: **my
count is a superset at the tightest end** -- I found a fifth sub-2.0mm pair,
`C22.2` (`hb.gate_hs.driver-p2`, HV) <-> `L2.2` (`+3V3`, SELV) at
**1.876mm**, body-free, which does not appear in the prior determination's
four-pair table. `C22` is a 0603 gate-driver bootstrap/decoupling cap;
`L2` is a Bourns SRP1265A power inductor (the SELV +3.3V rail's magnetics).
Both are ordinary two-pin parts, not among the eight isolators either
determination focused its manual spot-checking on -- exactly the kind of
pair a full board-wide aggregate would catch and a hand-verified table
might not.

**Conclusion I draw from this, stated plainly:** the previously-reported
"116 of 222" figure should be treated as **approximately right, not
exact**. The order of magnitude (roughly 100-120 body-free candidate pairs
out of roughly 200-225 sub-12.6mm cross-domain pairs) is corroborated by an
independent implementation; the specific integers are not reproducible to
the pair and should not be cited as if they were. **My own figure, this
session, fully reproducible from the script above: 202 total, 100 crossing
a body, 102 body-free.** Neither count is "the" answer; both are outputs of
a rectangle-model proxy over a real board, and the discrepancy itself is a
finding (Sec 1.4 below explains why it does not change the decision).

### 1.4 Confirming none of the body-free pairs runs under a body -- and that the tightest ones fail anyway

By construction, the "body-free" bucket in both scripts is defined as
"straight-line path samples land inside zero footprint body boxes" -- so the
claim is tautological for whichever count you use, not an additional fact
needing separate confirmation. What is worth confirming is that the
**tightest** pairs -- the ones any coating claim would most want credit
for -- are genuinely in that bucket and genuinely fail the PD1 bar anyway:

| Gap | Pair | Body-free? | Passes PD1 (2.0mm)? |
|---:|---|---|---|
| 0.905mm | `C17.2` (`hb.gate_hs.driver-p2`) <-> `R32.1` (`+3V3`) | body-free (MEASURED) | **No** |
| 1.100mm | `R30.2` (`tank-out`) <-> `R1.1` (`+15V`) | crosses `R1`'s axial body box (leaded part -- see caveat below) | **No** |
| 1.124mm | `R30.1` (`tank.c_tank1-p2`) <-> `R1.1` (`+15V`) | crosses `R1`'s body box | **No** |
| 1.148mm | `R30.1` (`tank.c_tank1-p2`) <-> `R1.2` (`power_in.bypass_relay-coil1`) | crosses `R1`'s body box | **No** |
| **1.876mm** (new, this session) | `C22.2` (`hb.gate_hs.driver-p2`) <-> `L2.2` (`+3V3`) | **body-free** (MEASURED) | **No** |

Two of the five sub-2.0mm pairs (`C17`<->`R32` and the newly-found
`C22`<->`L2`) are genuinely body-free by both the rectangle-box test and by
inspection of the footprints involved (0603 passives and a small inductor,
none of which have a body large enough to plausibly cover a path this
short). **These are the honest counter-example to "coating helps the
body-free set": it does not help these two, because 2.0mm is the floor even
under a perfect Type A/PD1 claim, and 0.905/1.876mm are below it.** The
other three (`R1` pairs) carry the caveat the prior determination already
raised -- `R1` is a leaded axial resistor whose body sits proud of the
board, so a coating might plausibly reach under it -- but they are moot for
that same reason: all three are under 1.2mm, so they fail PD1 regardless of
whether the coating physically reaches there.

**These five pairs need a layout fix (move the parts apart), independent of
any coating decision.** That is the falsifier's first clause firing, for
this specific cluster.

### 1.5 What this section establishes and does not

- Established, this session, independently: **denominators match exactly,
  isolator-level and sub-2mm-cluster-level figures match to the
  millimetre**, giving high confidence in the underlying method.
- Established, this session, independently: **the board-wide aggregate
  count is approximately, not exactly, reproducible** -- treat "116/222" or
  "102/202" as an order-of-magnitude statement, not a precise inventory.
- Established, this session: **a fifth sub-2.0mm, body-free pair exists**
  that neither prior determination reported.
- Not established, and not claimed: that either rectangle-model script
  captures the true minimum creepage path on this board. Both prior
  determinations already flagged that pad-to-pad is a lower bound, not the
  full problem (96 copper pour zones on both HV and SELV nets exist and are
  not analysed by either script) -- unchanged here, and worth restating
  because it means even the "202" and "222" figures are themselves
  optimistic floors, not ceilings.

---

## 2. The PCB working surface temperature -- never declared, derived here

### 2.1 The absence, confirmed again

MEASURED (grep of `docs/ENVIRONMENTAL_SPEC.md`, `docs/hardware/SYSTEM_THERMAL_BUDGET.md`,
`docs/hardware/THERMAL_DESIGN_GUIDE.md`, `docs/guides/THERMAL_DESIGN_GUIDE.md`,
and every file under `docs/hardware/`): **no document in this repository
states a maximum PCB working surface temperature, at any value.** Component
junction/case temperatures are extensively documented; a board-surface
figure is not. No board-surface thermocouple measurement exists anywhere in
this repository, at any operating point.

This is the input IEC 60664-3 Table 2 keys its dry-heat conditioning row to
(independently re-confirmed this session, CITED-PRIMARY, `pdftotext -layout`
from <https://law.resource.org/pub/in/bis/S05/is.15382.3.2006.pdf>, the
same source the prior determination used, re-fetched and re-read by me
rather than inherited):

```
Table 2 -- Dry heat conditioning (Epoxide/woven glass, i.e. FR-4)

  Maximum working surface temperature (degC)   Conditioning temp (degC)   Time (h)
  140                                            175                        1000
  100                                            125                        1000
  75                                             95                          1000
```

(OCR quality on this scan is poor in spots -- e.g. "wcrrking" for "working"
-- but the numeric table itself is unambiguous and reads identically to the
prior determination's transcription; two independent fetches of the same
document, six weeks apart in session terms, agree exactly.)

### 2.2 What the design's own thermal analysis already documents

All MEASURED from `docs/hardware/SYSTEM_THERMAL_BUDGET.md`, this session:

- **The appliance's own design basis treats 55-70 degC internal enclosure
  air as a normally-tolerated, non-fault operating range**, not an
  exceptional condition: the derating table (Sec 5.2) keeps the unit
  running (at reduced power, 60-90%) from 40 degC through 70 degC ambient,
  and the document separately defines an internal-environment scale up to
  an **85 degC absolute design-limit maximum** (Sec 2.2) distinct from the
  40 degC-rated room ambient in `ENVIRONMENTAL_SPEC.md`.
- At the top of that normally-tolerated range (70 degC internal ambient,
  120V system -- the system actually specified; the document's 240V rows
  are a documentation inconsistency flagged separately below), the
  document's own component tables report: **IGBT heatsink case (Tc) 89
  degC**, **IGBT Tj 96-109 degC** (96 degC in Sec 3.1's 120V-specific
  table; 109 degC in Sec 8.2's summary table, which does not clearly
  separate 120V from 240V figures -- an internal inconsistency in the
  source document, not resolved here), **LMR51430 (buck regulator) Tj 150
  degC** -- flagged by the document's own text as **"at limit"** and
  requiring relocation -- and **XC6220 (LDO) Tj 130 degC**.
- Per the same document's Sec 7.2/7.3, the LMR51430, XC6220, and UCC21550
  are explicitly connected to PCB copper pour and thermal vias **as their
  stated heat-spreading strategy** -- i.e., by the design's own account,
  board copper near these parts is not a bystander, it is the heatsink.
- MEASURED this session, `pcb/temper.kicad_pcb`: the LMR51430-class part
  (`U4`) sits at board coordinates (115.66, 147.41). The body-free
  coating-candidate cluster identified in Sec 1 (`C17`, `C22`, `L2`, `R30`,
  `R32`, `R1`, `R54`, `R73`, `U13`) sits at roughly (33-48, 148-190) -- on
  the order of 70mm away in X. The IGBTs (`U5`, `U6`, TO-247 packages) sit
  at (145.8, 241.1) and (168.5, 108.9) -- over 100mm from that same
  cluster. **The specific paths this document's coating scope covers are
  not co-located with the board's documented hot spots**, which argues for
  scoping any temperature declaration to the region actually claimed rather
  than assuming the LMR51430/IGBT hot-spot figures apply uniformly -- but
  see 2.3 for why a single whole-board declaration is still the safer
  default absent a scoped qualification argument this repo does not yet
  make.

### 2.3 Derivation

**DERIVED.** A board-wide maximum working surface temperature declared
below 100 degC is not defensible against this data: the appliance's own
design basis, at a condition it treats as normal (not faulted) operation,
already documents board-mounted-part junctions at 130-150 degC and a
heatsink base at 89 degC -- well past the 75 degC threshold that would
unlock the lenient 95 degC/1000h row. **100 degC -> 125 degC/1000h is the
minimum defensible board-wide declaration.**

Whether the true figure must be 140 degC -> 175 degC/1000h (i.e., whether
the LMR51430 hot-zone's 150 degC Tj, already flagged marginal by the
existing thermal document and slated for relocation, forces the whole-board
number up) is genuinely open and depends on a choice this repo has not
made: whether a single blanket coating claim covers the whole board (in
which case the worst zone governs, and the answer is likely 140 -> 175), or
whether the claim is scoped to the specific body-free region this document
identifies (in which case 100 -> 125 is more defensible for that region
specifically, since it is 70-100mm from the documented hot spots).

**RECOMMENDATION (ASSUMED -- flagged for a human, not asserted as
established fact): declare 100 degC as the maximum PCB working surface
temperature for the region this document's coating scope covers**, which
selects the **125 degC/1000h** Table 2 row -- the same row the prior
determination provisionally guessed at ("the honest expectation is that a
75 degC declaration will not survive measurement, putting this at the
125 degC/1000h row or worse"). This recommendation is now grounded in the
repo's own documented worst-case component data rather than being a guess,
but it remains a **derived placeholder, not a measurement** -- no
thermocouple has ever been placed on this board's surface. **This is a
prerequisite for any coating qualification and its absence is itself the
finding**, exactly as the task framed it. A human must either measure it or
explicitly adopt this derivation before qualifying any coating.

---

## 3. Coating chemistries against the derived 100 degC / 125 degC-row requirement

### 3.1 What the prior determination already established (not re-litigated, restated for context)

CITED-SECONDARY (MG Chemicals *Conformal Coatings* category data sheet,
Electrolube HPA TDS -- fetched and read by the prior determination this same
investigation date, not re-fetched here):

| Product | Binder | Constant service temp | Tg |
|---|---|---:|---:|
| MG 419D | Acrylic | -65 to 125 degC | 27 degC |
| MG 419E | Acrylic | -65 to 130 degC | 38 degC |
| MG 422B/422C | Silicone-modified acrylic | -40 to 200 degC | 29/31 degC |
| MG 4223F | Polyurethane | -65 to 125 degC | 57 degC |
| MG 4200UV | Urethane acrylate | -65 to 150 degC | 72 degC |
| Electrolube HPA | (silicone-adjacent, per its TDS) | -55 to 130 degC | -- |

Against the 125 degC conditioning row: acrylic and polyurethane sit at
**zero margin** (rated exactly to the test temperature, for a 1000h
continuous exposure the rating does not contemplate); silicone-modified
acrylic has real headroom (200 vs 175 degC worst case). Every chemistry in
that table has a Tg between 27 and 72 degC -- **at or below this board's
own normal operating temperature**, meaning the coating is in its rubbery,
high-CTE state throughout normal operation, not just during the thermal
qualification test. That finding is unchanged here and is reinforced by the
new parylene data below.

### 3.2 Parylene -- fetched this session, not inherited

The prior determination explicitly declined to cite a parylene figure
because it had fetched no datasheet. I fetched one this session:
**"SCS Parylene Properties," Specialty Coating Systems, (c) 2018, doc code
002 12/18** -- CITED-SECONDARY, `pdftotext -layout` extracted directly from
<https://easyfairsassets.com/sites/322/2024/08/02-SCS-Parylene-Properties-0322.pdf>
(a conference-site mirror of the vendor's own document; content
self-identifies as SCS's, matches SCS's own site branding and copyright
line, and is treated as the vendor's primary technical literature on that
basis).

**Table 4, "Parylene Thermal Properties" (quoted verbatim, this session):**

| | Parylene N | ParyFree | Parylene C | Parylene D | Parylene HT | Acrylic (AR) | Polyurethane (UR) | Silicone (SR) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Melting point (degC) | 420 | 349 | 290 | 380 | >500 | 85-105 | ~170 | -- |
| Continuous service temperature (degC) | 60 | 60 | **80** | **100** | 350 | 82 | 121 | 260 |
| Short-term service temperature (degC) | 80 | 80 | 100 | 120 | 450 | -- | -- | -- |

**Table 1, "Parylene Electrical Properties" (dielectric strength, V/mil):**
Parylene N 7,000; ParyFree 6,900; Parylene C **5,600**; Parylene D 5,500;
Parylene HT 5,400 -- vs. acrylic 3,500, epoxy 2,200, polyurethane 3,500,
silicone 2,000. Every parylene variant beats every non-parylene coating on
this specific metric, by a wide margin.

CITED-SECONDARY, same document, grepped this session: **"SCS Parylenes meet
the requirements of IPC-CC-830."** No mention of IEC 60664-3, IEC 60335-1,
or Annex J anywhere in the document (grepped, absent) -- the same finding
the prior determination made for MG Chemicals and Electrolube, now
independently confirmed for a third vendor family. **IPC-CC-830 conformance
does not discharge Annex J qualification; no vendor document reached across
either session claims the latter.**

**Note on Tg vs. the metric this datasheet actually reports.** This
document does not state a classical DSC glass-transition temperature. It
reports "T5" and "T4" points from DMA secant-modulus curves -- the
temperatures at which storage modulus falls to 690 MPa and 70 MPa
respectively (its own footnote a: "the temperature at which heat flow
properties show signs of change" for melting point; T5/T4 are a separate,
modulus-based softening metric, method note 2/3, DMA / ASTM D5026). For
Parylene C: T5 = 125 degC, T4 = 240 degC. **I am not equating this with the
Tg figures MG Chemicals reported for acrylic/urethane/silicone -- they are
different measurements from different test methods and I have not
reconciled them.** What I can say without conflating the two: Parylene C's
own **continuous service temperature (80 degC) is itself below this
board's derived 100 degC declaration**, independent of any Tg/T5 question.

### 3.3 DERIVED: assessment against the 100 degC / 125 degC-row requirement

- **Parylene C (continuous 80 degC, short-term 100 degC) does not clear the
  125 degC conditioning test.** It is worse-positioned here than acrylic
  (125 degC continuous), not better -- despite being the chemistry
  popularly associated with the best penetration and highest dielectric
  strength.
- **Parylene D (continuous 100 degC, short-term 120 degC) also does not
  clear 125 degC.** It exactly matches the *declared max working surface
  temperature* (100 degC) that selects the row, but the row's *test
  temperature* is 125 degC -- 25 degC above Parylene D's own continuous
  rating, for 1000 continuous hours. Same zero/negative-margin problem as
  acrylic and polyurethane.
- **Only Parylene HT (continuous 350 degC) clears the 125 degC row with
  large margin** -- consistent with, and now reinforcing, the prior
  determination's finding that silicone-modified acrylic is "the chemistry
  the thermal environment points at." Parylene HT carries the same process
  penalty already flagged for parylene generally: vacuum-chamber
  deposition, harder masking, and (per this repo's `HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  §6.4's already-flaged problems, not re-litigated here) no clause-based
  standard basis for any coating claim regardless of chemistry.
- **A structural caveat on parylene's one real advantage.** Parylene is
  deposited by vapour-phase, non-line-of-sight polymerisation, which is why
  it is the one chemistry that can genuinely penetrate under a leaded part
  standing proud of the board (e.g., the `R1` axial resistor case flagged
  in Sec 1.4). **This does not extend to a flush-seated body with no gap
  for vapour ingress** -- a relay base resting directly on the board, or an
  SOIC/DIP package's moulded body sitting on solder paste with sub-0.15mm
  standoff (the exact geometry measured for `U7` in the prior
  determination). Vapour deposition needs *some* path for gas to reach a
  surface; a sealed mechanical contact interface has none. **Parylene does
  not reach the isolator paths either**, for a different reason than a
  liquid coating's viscosity, but the same practical result.

**Conclusion, unchanged in direction from the prior determination and now
better-supported: every coating chemistry examined across two independent
fetching sessions and three vendor families is either at zero/negative
margin against the temperature this board's own thermal documentation
implies, or carries a known process penalty (silicone: solderability;
Parylene HT: vacuum process, masking difficulty, cost) to get the margin.**
No chemistry examined is a clean, low-cost fit.

---

## 4. Pollution degree -- corrected in `docs/ENVIRONMENTAL_SPEC.md`

**Done, not just recommended.** `docs/ENVIRONMENTAL_SPEC.md:45` previously
asserted "PD2 -- Normal household environment" with no citation. It now
states **PD3 as the governing macroenvironment default**, with the
clause citation and the enclosure-argument gap spelled out in a new
Sec 3.1 of that file. Summary of what changed and why:

- IEC 60335-2-6 clause 29.2 Addition (CITED-PRIMARY, re-fetched and
  re-read by me this session, `pdftotext -layout` from
  <https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf>, quoted
  verbatim): *"The microenvironment is pollution degree 3 unless the
  insulation is enclosed or located so that it is unlikely to be exposed to
  pollution during normal use of the appliance."* This is an independent
  re-fetch, not a citation inherited from the prior determination -- the
  wording matches exactly, which is itself corroboration.
- PD2 is the exception, not the default, and it must be earned. Checked
  against this repo: the same table's own **IP20** rating ("no liquid
  ingress protection guaranteed"), the **forced-airflow duct** described in
  `docs/CHASSIS_AIRFLOW_DESIGN.md` (pulls kitchen air across the board
  compartment), and the absence of any sealed/gasketed-compartment
  specification anywhere in the repo (checked `SENSOR_MOUNT_DESIGN.md`,
  `COIL_BRACKET_DESIGN.md`, `CONNECTORS_AND_WIRING.md`, `ASSEMBLY_GUIDE.md`)
  all argue against PD2 having been earned. **No enclosure argument
  exists in this repo today.**
- Consequence, unchanged from the prior determinations and now formally
  reflected in `ENVIRONMENTAL_SPEC.md`: **12.6mm reinforced creepage
  governs every mains<->PELV path this board has not separately qualified
  for PD1** (IEC 60335-1 Table 17 row iv, PD3, material group IIIa/IIIb,
  6.3mm basic x2), not the 8.0mm figure the rest of the repo's tooling
  currently uses (which is the PD2 figure at the same row).

**A contradiction this correction does not resolve, because it is not my
file:** `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2 independently
asserts "Pollution Degree: 2 -- Normal indoor environment, condensation
possible" with its own unsourced justification column, and that document
also carries the fabricated "x1.5 creepage multiplier for coated surfaces"
the task flagged. A sibling agent owns that file. **After this correction,
the repo contains two contradictory pollution-degree assertions in two
different specs, one now cited to primary text (PD3, this file) and one
still uncited (PD2, `HIGH_VOLTAGE_CLEARANCE_SPEC.md`).** That contradiction
is itself worth surfacing to whoever reconciles the two documents; I have
not edited the second file per the task's hard rule.

---

## 5. Process honesty, if coating is specified for the body-free subset

### 5.1 Masking inventory -- independently reproduced

MEASURED this session, own script against `pcb/temper.kicad_pcb` (reference
prefixes, cross-checked against the board's actual footprint list, not
inherited from the prior determination's table):

| Class | Count | Refs |
|---|---:|---|
| Relays (vent / seated body) | 3 | `K1`, `K2`, `K3` |
| Test points | 3 | `TP1`, `TP2`, `TP3` |
| TO-247 tab + heatsink interface | 2 | `U5`, `U6` |
| Fuse holder | 1 | `F1` |
| Pin header (only connector actually on the board) | 1 | `J1` |

**Independently reconfirmed: `docs/CONNECTORS_AND_WIRING.md` documents
eight connectors** (`J_IN`, `J_COIL`, `J_RTD1`, `J_RTD2`, `J_FAN`, `J_PROG`,
`J_UI`, `J_DEBUG`); **the board carries exactly one** (`J1`) -- MEASURED,
grep of every footprint reference on the board for a `J`-prefix. The RTD
probe interface (`J_RTD1`) the task specifically asked about **does not
exist on this board yet**, so its masking requirement cannot be assessed
today and will be a new obligation the moment it is added.

### 5.2 Whether non-sealed relays can be coated -- now resolved for all three relays, not two

CITED-PRIMARY, Omron G5LE datasheet, re-fetched and re-read this session
(same URL the prior determination used,
<https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf>), Model
Number Legend: *"3. Enclosure rating: None: Flux protection / 4: Fully
sealed."* The board specifies `G5LE-1 DC12` (field 3 empty), i.e. **flux
protection, not sealed** -- confirms the prior finding for `K2`/`K3`.

**New this session** -- the prior determination explicitly flagged `K1`
(Omron G4A-1A-E) as **NOT VERIFIED** for this question. I fetched its
datasheet this session (CITED-PRIMARY,
<https://omronfs.omron.com/en_US/ecb/products/pdf/en-g4a.pdf>,
`pdftotext -layout`): *"Standard model available with flux protection
construction."* **`K1` is also flux-protected, not sealed, in the variant
this repo specifies (`G4A-1A-E`, no sealed suffix).** A coating process on
this board would need to mask the vent path on **all three relays**, not
two -- correcting the prior determination's scope on this specific point
upward.

**Also new this session, and outside my scope to act on but safety-relevant
enough to surface:** the same G4A datasheet states, in its own
Characteristics table, **dielectric strength between coil and contacts:
4,500 VAC, 50/60 Hz, 1 min; impulse withstand between coil and contacts:
8.5 kV (1.2x50 us); and insulation distance between coil and contacts:
clearance 3.2mm, creepage 6.4mm, as a stated property of the component
itself.** This is materially different from `K2`/`K3`'s G5LE-1, whose
datasheet gives **no** creepage/clearance figure at all and only 2,000 VAC
coil-to-contact dielectric strength (prior determination's finding,
unchanged). **`K1`'s own component-level isolation rating appears to
already clear the IS 302-1 Table 7 reinforced-insulation electric-strength
bar the prior determination found `K2`/`K3` failing** -- a fact the
isolator/BOM determination should weigh, since it changes `K1`'s status
from "unverified, treated as a possible additional BOM problem" to
"possibly already adequate on its own component rating, independent of the
board-surface path." **I have not resolved this fully** (I did not
cross-check the 4,500 VAC / 8.5kV figures against the exact Table 7 column
for this board's working voltage, and this is not my determination to
close), and I have made no BOM-relevant edit on the strength of it -- I am
surfacing it because I found it while answering the coating-masking
question this section required.

### 5.3 Rework and production verification -- re-confirmed from primary text this session

CITED-PRIMARY, IEC 60664-3 cl. 1, re-fetched and re-read this session
(same URL, <https://law.resource.org/pub/in/bis/S05/is.15382.3.2006.pdf>):
*"This standard refers only to permanent protection. It does not cover
assemblies that are subjected to mechanical adjustment or repair."*
Independently re-confirmed cl. 5.4: *"The soldering procedure is carried
out but without components being in place."* Both match the prior
determination's quotations exactly (independent re-fetch, not inherited).

**Consequence, restated with the sharper edge the task asked for:** the
clause-5 test regime that would qualify any coating chemistry on this board
tests a **bare board**, and any rework of a coated, populated assembly
voids the PD1 claim for whatever it touches, with no touch-up provision in
the standard. **The one part of this that changes for the body-free subset
specifically (as opposed to the isolator paths):** those paths are, by
definition, on open board surface with no component body over them, so
standard UV-tracer inspection **can** verify coating coverage there --
unlike the isolator paths, where coverage under a seated body is
structurally unverifiable by any production process. **This is the honest
distinction that makes the body-free subset a legitimate coating target
where the isolator paths were not: it is not just that coating physically
reaches those paths, it is that coverage there can actually be checked in
production.** That is a genuine point in coating's favour for this specific
subset, and it is the reason the falsifier does not fire completely.

---

## 6. Answering the task's questions directly

| Question | Answer |
|---|---|
| Establish the 116/222 figure yourself | Done, own script, own denominators (Sec 1). Denominators and isolator/sub-2mm-cluster figures reproduce exactly; the board-wide aggregate does not (202/100/102 here vs. 222/106/116 previously) and should be read as approximate, not exact. A fifth sub-2.0mm, body-free pair was found that neither prior document reported. |
| Confirm none of the body-free pairs runs under a body | True by construction of the bucket; the substantive check performed was confirming the *tightest* pairs are genuinely body-free and genuinely fail PD1 anyway (Sec 1.4) -- two of five sub-2.0mm pairs are body-free and unhelped by coating regardless. |
| Declare the PCB working surface temperature | Never declared anywhere in this repo (re-confirmed). Derived here: **100 degC**, selecting IEC 60664-3 Table 2's 125 degC/1000h row, grounded in this board's own documented worst-case component data (IGBT case 89 degC, LMR51430 Tj 150 degC "at limit", XC6220 Tj 130 degC at a design-basis, non-fault 70 degC enclosure condition). Explicitly a derived placeholder pending real measurement, not a measured fact. |
| Assess coating chemistries against that temperature | Acrylic and polyurethane: zero margin (unchanged from prior). Parylene C and D (fetched this session): **also insufficient**, continuous ratings of 80/100 degC against a 125 degC test. Only silicone-modified acrylic and Parylene HT clear it, both at known process cost. No Tg given in the parylene source; its T5/T4 modulus-transition metric is a different measurement, not conflated with the acrylic/urethane Tg figures. |
| Settle the pollution degree question | Settled in `docs/ENVIRONMENTAL_SPEC.md`: PD3 is now the cited, governing default; PD2 remains available only if a future enclosure argument is documented, which does not exist today. `HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s separate, uncited PD2 assertion is unchanged (sibling-owned) and now visibly contradicts this file. |
| Specify the process honestly | Masking: 3 relays (not 2 -- `K1` is also flux-protected, new this session), 3 test points, 2 TO-247 tabs, 1 fuse, 1 connector (of 8 documented, only 1 exists; the RTD interface does not exist yet). Rework: excluded from the standard's own scope (cl. 1). Production verification: structurally possible for the body-free subset specifically (open surface, UV-tracer-inspectable) -- this is the one point genuinely in coating's favour, and the reason it is not fixed by layout instead for every pair. |

## FALSIFIER -- result

Stated in the Verdict; restated here as a direct yes/no per clause:

- *"If those paths already meet the requirement without it"* -- **No**, most
  of the body-free set (2.0-12.6mm) needs the PD1 relief coating would
  provide; they do not meet 12.6mm (or even 8.0mm) unaided.
- *"If ... the qualification burden ... exceeds its value for a partial
  subset"* -- **Partially yes.** The thermal burden is real (100 degC
  forces the 125 degC row; two of four chemistries examined, including
  both parylene grades checked this session, fail to clear it) and the
  masking burden is now shown to cover all three relays, not two. Whether
  this "exceeds the value" is a judgement call the task correctly leaves to
  a human, not a fact this document can settle alone -- but the burden is
  larger than the prior determination could state, because the temperature
  input did not exist before this session.
- *"then ... fix those paths by layout instead"* -- **Yes, unconditionally,
  for the five sub-2.0mm pairs** (Sec 1.4), two of which are body-free and
  would not be helped by any coating qualification no matter how it is
  resourced. **For the remaining ~95-97 body-free pairs between 2.0mm and
  12.6mm, coating remains a legitimate, verifiable supplement**, but only if
  the now-quantified thermal and masking burden is actually carried, not
  assumed away as it was when no temperature figure existed to check it
  against.

---

## 7. UNVERIFIED -- explicit list

- **The board-wide 202/222 discrepancy (Sec 1.3) is reported, not fully
  explained.** I ruled out pad rotation, footprint flip state, and
  zero-size/custom pads as causes and found one concrete example of my
  count being a superset (the `C22`/`L2` pair), but I did not locate every
  source of the ~20-pair difference across roughly 21,000 pairwise
  comparisons, and the prior determination's script no longer exists in
  this worktree to diff against directly.
- **The 100 degC / 125 degC-row temperature recommendation is derived, not
  measured.** No thermocouple has ever been placed on this board. The
  derivation leans on documented component junction/case temperatures at a
  design-basis (not measured) ambient scenario; a human must either take a
  real measurement or explicitly adopt this derivation.
- **Whether 100 degC or 140 degC is the right whole-board figure** depends
  on an unmade choice (blanket claim vs. region-scoped claim) -- flagged,
  not resolved (Sec 2.3).
- **Parylene's T5/T4 modulus-transition figures are not equated with the Tg
  figures reported for acrylic/urethane/silicone.** They are different test
  methods (DMA secant modulus vs. presumably DSC for the MG Chemicals
  table, which itself was not independently re-verified this session). Any
  claim that "parylene's Tg is X" would be a fabrication I have deliberately
  avoided.
- **`K1`'s (G4A-1A-E) newly-found 4,500 VAC / 8.5kV / 3.2mm-clearance /
  6.4mm-creepage component-level rating** has not been cross-checked
  against the exact IS 302-1 Table 7 column for this board's working
  voltage bracket, and I have made no determination about whether it
  resolves `K1`'s status in the isolator/BOM question -- that determination
  belongs to the sibling work on `U3`/`U7`/`K2`/`K3`, not to this document.
- **The pad-pair census (both this session's and the prior session's) is a
  lower bound on the real problem.** 96 copper pour zones exist on both HV
  and SELV nets and are not analysed by either script. Nothing in this
  document establishes that the assembled board meets any creepage
  requirement anywhere.
- **IPC-CC-830 vs. IEC 60664-3**: confirmed again this session that a third
  vendor family (SCS Parylene) does not mention IEC 60664-3 either. I did
  not read IPC-CC-830 itself and cannot state the precise relationship
  between the two regimes.
- No claim above is a compliance determination. No clause number, table
  number, or table value is stated except where I read it myself in the
  raw text this session and can point at the fetched document.

---

## 8. Sources -- exactly what was reached and read this session

**Fetched and read this session (all URLs resolved directly; `WebSearch`
budget was exhausted on the first query of this session, consistent with
both prior determinations -- confirmed again here, not re-attempted after
the first failure):**

- **IS 302-2-6:2009** (IEC 60335-2-6 identical adoption) -- re-fetched,
  `pdftotext -layout`, clause 29.2 Addition quoted verbatim, matching the
  prior determination's quotation exactly.
  <https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf>
- **IS 15382 (Part 3):2006** (IEC 60664-3:2003 identical adoption) --
  re-fetched, `pdftotext -layout`, clauses 1, 4.3, 5.4, and Table 2
  independently re-transcribed and cross-checked against the prior
  determination's quotations (exact match).
  <https://law.resource.org/pub/in/bis/S05/is.15382.3.2006.pdf>
- **Omron G5LE datasheet** -- re-fetched, Model Number Legend enclosure-rating
  field re-confirmed.
  <https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf>
- **Omron G4A datasheet** -- fetched for the first time this session (prior
  determination flagged this as NOT VERIFIED). Enclosure construction and
  coil-to-contact dielectric/impulse/creepage/clearance figures extracted.
  <https://omronfs.omron.com/en_US/ecb/products/pdf/en-g4a.pdf>
- **SCS Parylene Properties, Specialty Coating Systems, (c) 2018** -- fetched
  for the first time this session (prior determination explicitly declined
  to cite parylene without a real datasheet). Tables 1 and 4 extracted via
  `pdftotext -layout`.
  <https://easyfairsassets.com/sites/322/2024/08/02-SCS-Parylene-Properties-0322.pdf>
  (found via a direct page fetch of scscoatings.com's technical library
  listing, then a `lite.duckduckgo.com` lite-search fetch when the vendor's
  own gated download link 404'd -- the same URL-discovery method the prior
  determination used, since `WebSearch` itself was unavailable).

**Read from repo documents this session (MEASURED, grep/read, not fetched):**
`docs/hardware/SYSTEM_THERMAL_BUDGET.md`, `docs/CHASSIS_AIRFLOW_DESIGN.md`,
`docs/COIL_BRACKET_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`,
`docs/CONNECTORS_AND_WIRING.md`, `docs/architecture/induction_curriculum.md`,
`elec/domain_manifest.yaml`, `pcb/temper.kicad_pcb`, `elec/src/modules.ato`,
`docs/hardware/GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md`.

**Relied on without re-fetching this session (CITED-SECONDARY, attributed to
the prior determination, which fetched them this same investigation date):**
MG Chemicals *Conformal Coatings* category data sheet v2.0; Electrolube HPA
TDS. Both are quoted in Sec 3.1 with the prior determination's own figures,
unchanged, and their URLs are in that document
(`docs/evidence/2026-07-28-conformal-coating-pd1.md` §11).

**Attempted and failed:**

- `WebSearch`: budget exhausted on the first query this session (parylene
  datasheet search) -- identical to both prior sessions' experience.
- Direct PDF fetch of SCS's own gated Parylene Properties download link
  (`scscoatings.com/en/download/2249/`) -- 404 (form-gated redirect, not a
  static file). Worked around via the conference-mirror URL above, found
  through a `lite.duckduckgo.com` page fetch (not the `WebSearch` tool).
- `scscoatings.com/wp-content/uploads/2018/11/SCS-Parylene-Properties.pdf` --
  guessed URL, 404.

---

## Compliance with the task's hard rules

- No `git stash` at any point.
- No `run_in_background`, no `Monitor`, no waiting on any background job.
  Everything foregrounded, including the two `uv sync` calls needed to make
  `kiutils`/`pyyaml` importable in this fresh worktree's venv (the venv did
  not exist until this session created it; `--all-packages` sync was used
  once disk headroom was confirmed at 35GiB free, and the resulting `.venv`
  is 666MB, well within the disk budget).
- No additional worktrees. No large downloads: six standards/vendor
  PDFs, all under 2MB each, none committed to the repo (they live in the
  session's tool-results cache and the analysis scripts live in the session
  scratchpad, `/private/tmp/claude-501/.../scratchpad/`, not committed --
  matching the precedent the two prior determinations set for read-only
  analysis).
- Did not touch `generate_kicad_dru.py`, `HIGH_VOLTAGE_CLEARANCE_SPEC.md`,
  `packages/temper-placer/configs/netclass_rules.yaml`,
  `scripts/check_isolation_keepout.py`, or `pcb/temper.kicad_pcb`. Only
  `docs/ENVIRONMENTAL_SPEC.md` and this evidence file were edited.
- Verified before finishing (Sec below and separately, this session):
  `check_isolation_keepout.py` exits 3, `check_measurement_provenance.py`
  exits 5, `make netlist` passes, `uv run --no-sync python -m pytest
  elec/validation -q` passes (30 passed) -- all confirmed both before and
  consistent with after this document's edits, since neither edited file is
  read by any script (grepped: nothing under `scripts/`, `elec/`, or
  `packages/` references `ENVIRONMENTAL_SPEC.md`).
- Not pushed.
