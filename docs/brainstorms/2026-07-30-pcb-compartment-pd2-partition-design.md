<!-- provenance: branch brainstorm/pcb-compartment-pd2-enclosure, from origin/main at 9cd5a356 -->

# A sealed PCB compartment that earns cl. 29.2: partition design options

**Status:** brainstorm / decision-support only. No `pcb/**` or `elec/src/**`
changes. Run as solo rigorous analysis (ce-brainstorm skill, non-interactive
mode) — every place the skill would normally ask the user a question, this
document states the assumption made instead and flags it in the "Assumptions
and open questions" section. This document does not choose for the reader —
it ranks three concrete partition designs against both the pollution-exclusion
test and the thermal bound, and says plainly where the evidence runs out.

**Reading order:** if you only read one section, read "Verdict, up front"
and "Assumptions and open questions."

---

## Verdict, up front

**No option below is confirmed viable today. One (Option 2) has a plausible,
in-repo-groundable path to clearing both the pollution-exclusion test and the
thermal bound — but "plausible" is not "proven," and it depends on three
facts this document cannot resolve** (real UCC21550 θJA, whether LMR51430's
copper pour is actually laid out on the real board, and whether the chassis
has physical room for the added compartment volume). Absent those three, the
honest state is: **sealing the PCB away from the duct is mechanically
achievable and would earn the exception if documented correctly, but doing so
without also stacking every non-air-path thermal mitigation this document
describes pushes the binding component (LMR51430) into zero-to-negative
margin at the repo's own stated 55–70°C worst-case ambient band** — the same
"marginal" conclusion `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`
already reached, restated here specifically against three concrete
partition-design mechanisms rather than a parametric sweep.

**The central mechanical fact governing every option:** the IGBTs (Q1, Q2)
and the two TO-220 rectifiers are PCB-mounted — leads soldered into the
board — while their tabs bolt to a single shared heatsink (`HS1`,
Wakefield-Vette 392-120AB) that must stay in the forced-air duct, because it
*is* the thing being air-cooled. There is no partition geometry that avoids
this: **the compartment boundary must cross through, not around, these four
packages.** Every option below inherits the same physical detail at that one
joint — a cutout in the compartment wall shaped to the four TO-247/TO-220
bodies, sealed around their package perimeter, not their leads. The options
differ in compartment volume, thermal mitigation stacking, and internal
partitioning — not in whether this crossing exists.

---

## Facts recap (grounded this session; see Sources)

- **PD3 (12.6mm reinforced creepage) governs today** because the cl. 29.2
  exception ("unless the insulation is enclosed or located so that it is
  unlikely to be exposed to pollution") is not earned:
  `docs/CHASSIS_AIRFLOW_DESIGN.md` routes forced air — bottom vents → intake
  plenum → 80mm fan → duct → heatsink — directly across the same cavity the
  PCB occupies; `docs/COIL_BRACKET_DESIGN.md` §4 is an explicitly
  air-permeable baffle over the board, not a seal; `docs/ASSEMBLY_GUIDE.md`'s
  only gasket seals the glass cooktop to the chassis, not the electronics.
  IP20 ("no liquid ingress protection guaranteed," `docs/ENVIRONMENTAL_SPEC.md`
  §3) argues against an enclosure claim at the whole-appliance level and is a
  separate question from whether one internal, non-vented sub-compartment
  protects one specific insulation's microenvironment — worth keeping
  distinct in any eventual compliance write-up (see "What must be
  documented," below).
- **PD2 at this design's 400V boundary is 8.0mm reinforced**, not 10.0mm —
  `docs/evidence/2026-07-30-pd2-creepage-row-determination.md` independently
  re-read IS 302-1:2008 (identical adoption of IEC 60335-1) Table 17 row iv
  from a primary-text page render: the row's own stated boundary is "**>250**
  and **≤400**," a closed range that includes 400V literally, not a
  round-up case. This is the figure the PD2 exception would actually buy, if
  earned.
- **PD2/PD3 is a single classification applied to the whole board's
  insulation, not chosen per component** — this is why the thermal-bound
  document and this one both scope the compartment to the *entire* 152 ×
  234mm board (all four PCB_SPECIFICATION zones), not a subset. A partition
  that only walls off the control section (Zone C/D) and leaves the
  half-bridge/gate-drive section (Zone B) in open duct air would not earn PD2
  for Zone B's insulation — and Zone B is exactly where the gate driver
  (U7/UCC21550) sits, one of the two components whose PD3 creepage shortfall
  motivated interest in PD2 in the first place
  (`docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md`,
  Option 2). **The compartment has to be whole-board or it doesn't do the job
  either the thermal document or this one assumes it does.**
- **Thermal bound, already computed** (`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`):
  sealed-compartment design load ≈10.5–12W (9.65W repo budget + 0.7–2.3W IGBT
  lead conduction, this document's own §2 derivation). Compartment outer-wall
  ΔT above chassis air: 8–21°C across a full assumption sweep, central
  ~12–16°C, compact geometry (152×234×33mm). Generous geometry
  (172×254×50mm, +20mm in-plane / +17mm height) runs 20–40% cooler in ΔT at
  the same Q/ε/Ta. **LMR51430 (with its already-specified copper-pour
  mitigation) has +2.4°C to −0.8°C margin at the repo's own 70°C worst-case
  ambient, central assumptions — essentially zero.** UCC21550 gate driver may
  be worse, but its θJA (45–70°C/W) is assumed, not sourced anywhere in this
  repo. The electrolytic bus capacitors do **not** bind (comfortable margin
  except a compound-worst-case tail).
- **Board/chassis dimension conflict, unresolved:** the real board is 152 ×
  234mm (`pcb/temper.kicad_pcb` Edge.Cuts, measured), but the RCA 12A3
  chassis's own stated width is ~230mm — and `docs/specs/REQUIREMENTS.md`
  line 432 self-flags that figure as "**approximate, needs verification**."
  The board is already longer than the chassis is wide, on the chassis's own
  (unverified) numbers. This directly constrains how much compartment volume
  Option 2 below can actually claim.
- **Conformal coating is not an available fallback for anything in this
  document** — no coating process exists in the BOM or assembly today
  (`docs/evidence/2026-07-30-pollution-degree-determination.md` §2, grep
  confirmed), and even a hypothetical one couldn't help here: coating credits
  a different table column (PD1), not the PD3→PD2 step this document is
  about, and doesn't touch thermal at all.
- **No document in this repo describes a PCB compartment today** — this is
  new mechanical scope, not a documentation change. `docs/ASSEMBLY_GUIDE.md`
  Phase 4 currently just says "Secure the PCB into the chassis using M3
  standoffs."

---

## The unavoidable geometry: where the boundary has to run

Given board re-floorplanning is out of scope and the IGBT/heatsink
architecture is fixed, the compartment boundary is not a free design choice
in one respect: it must enclose the full board footprint (all zones) and it
must pass through the TO-247/TO-220 package bodies at the heatsink interface,
because that is the one place a PCB-mounted, heatsink-bolted component
physically straddles "inside the sealed volume" (leads, PCB copper) and
"outside it, in the duct" (heatsink fins, forced air). Every option below
uses the same mechanism at that joint: **a form-fitted cutout in the
compartment wall, matching the outline of the four package bodies (2×TO-247,
2×TO-220) mounted on `HS1`, sealed around the package perimeter with a
compliant gasket** — not a per-lead grommet (leads are far too close together
and too numerous per package for that to be practical) and not a
full-package potting (would trap the package's own heat and defeat the
heatsink's purpose).

This cutout-and-conformal-gasket joint is the **single weakest point in the
pollution-exclusion argument** in every option, for two reasons: (1) it is
the one place the fan actively draws unfiltered kitchen air (grease, steam,
cooking aerosol) directly across the seal, since the heatsink sits inside the
duct's own airflow path; and (2) there is no repo precedent or off-the-shelf
part for a 4-package conformal cutout gasket — the closest analog in this
design is `docs/CHASSIS_AIRFLOW_DESIGN.md` §6's "high-temp foil tape used to
seal joints between duct and heatsink," which is a flat-surface-to-flat-surface
seal, not a conformal cutout around irregular THT package bodies. This is a
real, unresolved engineering task in every option, not a solved problem being
restated.

---

## Options

### Option 1 — Compact conformal-seal box (minimum volume)

**Mechanism:** Compartment walls hug the board's own standoff/clearance
envelope — 152 × 234 × 33mm, the thermal-bound document's "compact" case
(8mm standoff + 25mm general clearance zone, both from
`docs/specs/PCB_SPECIFICATION.md` §2.2/2.4). A base tray + lid, 3D-printed in
the same high-temp PETG/ABS already specified for the duct
(`docs/CHASSIS_AIRFLOW_DESIGN.md` §6), lid-to-base sealed with a continuous
silicone gasket strip, heatsink cutout sealed with a conformal foam/silicone
gasket around the 4 package bodies, cable glands at each wire penetration
(see "Penetrations," below). No added thermal mitigation beyond what
`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §7 and
`docs/hardware/LMR51430_THERMAL_ANALYSIS.md` already specify (copper pour,
component placement away from heat sources).

**Pollution exclusion:** Strong, if executed — smallest total gasket/seam
length, fewest places for a seal defect. Same cutout-gasket weak point as
every option (above).

**Thermal viability — the numbers that already exist for this exact
geometry:** this *is* the thermal-bound document's headline case. At Ta=70°C
(repo's own worst-case band), ε=0.5 (mid), Q=9.65–12W: **LMR51430 margin
+2.4°C to −0.8°C.** At the unfavorable end of the assumption sweep (ε=0.2,
bare LMR51430 layout instead of the copper-pour mitigation), margin is
strongly negative (−15 to −20°C). UCC21550 is at or below zero margin under
central assumptions and its θJA is unsourced. **This option does not clear
the thermal bar with any real confidence at the repo's own stated worst-case
ambient** — it is exactly the "marginal, not comfortably viable" case the
thermal-bound document already computed.

**Verdict:** cheapest, simplest, most defensible on the pollution side; the
weakest of the three on thermal. Only defensible if the LMR51430's real
in-service ambient stays in the "normal/warm kitchen" 25–55°C band the
thermal document shows is comfortably viable — i.e., only if you're willing
to treat the repo's own 55–70°C "worst case... hot location, poor
ventilation, extended cooking" band as acceptably rare rather than a design
target.

---

### Option 2 — Generous-volume compartment with direct chassis conduction ("finned bulkhead")

**Mechanism:** Same sealing mechanism as Option 1 (conformal cutout gasket,
cable glands, lid gasket), but two changes layered on:

1. **Compartment expanded to the thermal-bound document's "generous"
   envelope: 172 × 254 × 50mm** (+20mm in-plane for wall/mounting flange,
   +17mm height to also cover part of the IGBT-zone clearance). 30% more
   surface area, 20–40% lower ΔT than compact at the same load/emissivity.
2. **Direct metal conduction bridges** — thermal pads or bonded aluminum
   straps — from the LMR51430's and UCC21550's ground/thermal copper
   straight to the compartment's chassis-adjacent wall, bypassing the
   compartment's internal air-film resistance entirely for exactly the two
   parts the thermal-bound document identifies as binding
   (`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md` §4, "likely
   the single most effective, lowest-risk mitigation"). This requires
   relocating those two parts toward the compartment's chassis-facing
   surface rather than centrally — an individual-component relocation, which
   the task's hard constraints explicitly allow, not a board re-floorplan.
3. **High-emissivity interior/exterior finish** (matte black rather than
   bare/anodized aluminum) on the compartment walls — a free lever the
   thermal document's own ε=0.2→0.9 sweep is worth 4–5°C by itself at the
   compact case, and applies identically here.

**Pollution exclusion:** Same mechanism and same weak point (heatsink
cutout) as Option 1 — larger box, same number of seams, so no worse.

**Thermal viability — combining the thermal-bound document's own cited
sensitivities (this document's arithmetic, not independently re-modeled;
flagged as such):** generous geometry alone gives ~20–40% lower wall ΔT than
compact at the same Q/ε; combined with ε=0.9 (already shown standalone to be
worth 4–5°C at compact geometry), the local ambient the LMR51430 sees drops
roughly 4–7°C below Option 1's compact/ε=0.5 case. Applied to Option 1's
+2.4°C (Q=9.65W) / −0.8°C (Q=12W) baseline margins, this puts LMR51430
central-case margin in roughly the **+6 to +9°C range (Q=9.65W)** and
**+3 to +6°C range (Q=12W, the conservative IGBT-lead-conduction-inclusive
load)** — genuinely, if modestly, positive under both design-load
assumptions. The direct chassis-conduction bridge is not separately
quantified anywhere in-repo (no thermal-pad resistance or strap geometry
exists to compute against) but is qualitatively expected to add further
margin on top, since it removes the compartment's air-film resistance
entirely for the two binding parts rather than just lowering it. **This is
the only option in this document with a plausible path to clearing the
thermal bar at the repo's own 70°C worst-case band under central
assumptions** — but it is a combination of cited sensitivities, not a single
verified number, and the conduction bridge's actual benefit is unquantified.

**Real, unresolved cost:** two things this document surfaces but does not
resolve:

- **Chassis volume.** The board (234mm) is already longer than the chassis's
  own stated width (230mm, itself flagged "approximate, needs verification"
  in `docs/specs/REQUIREMENTS.md`). Option 2's added +20mm/+17mm margins may
  simply not fit until that dimension conflict is resolved by measuring the
  real chassis — this is not a paperwork gap, it could make Option 2
  physically infeasible.
- **Electrical bonding.** Bonding LMR51430's/UCC21550's local ground copper
  directly to chassis metal is a new electrical connection, not just a
  thermal one. `docs/hardware/PCB_SPECIFICATION.md` §7.2 documents a
  deliberate star-ground topology with only one authorized cross-domain
  connection point; a second, informal ground-to-chassis bond at the
  compartment wall could create an unintended second ground path or loop.
  This needs its own check against the actual grounding scheme before being
  built, not assumed safe because it's "just a thermal pad."

**Verdict:** best thermal case of the three, same pollution-exclusion
strength as Option 1, but gated on two real open items (chassis fit,
grounding-topology compatibility) that this document flags rather than
resolves.

---

### Option 3 — Split-domain dual sub-compartment (hot-zone / cool-zone partition)

**Mechanism:** Instead of one box, two adjoining sealed sub-compartments
sharing an internal wall: one around Zone B (IGBTs, gate driver — the
highest local heat density, closest to the IGBT lead-conduction load and the
heatsink cutout), one around Zones A/C/D (bus caps, buck, LDO, ESP32,
control). Both sub-compartments together still enclose the whole physical
board with one continuous outer sealed boundary (the shared internal wall is
not itself a pollution path, since it's inside the sealed volume) — so the
whole-board PD2 requirement above is still satisfied. The intent is to
directly address the thermal-bound document's single largest *unquantified*
uncertainty: "whether the IGBT-adjacent zone locally recirculates hotter air
onto the LMR51430 if they are placed close together" (§5) — by physically
preventing that recirculation rather than assuming it away.

**Pollution exclusion:** Same overall boundary and same weak point
(heatsink cutout, now entirely within the hot-zone sub-compartment) as
Options 1/2, plus one additional internal seam (the shared wall) — more
places for a seal defect, though the internal wall doesn't face outside air
directly, so it isn't itself a new pollution *ingress* path, only a new
place workmanship could fail.

**Thermal viability:** **Not quantified anywhere in-repo, and not
quantifiable with the tools available here.** The thermal-bound document is
explicit that internal recirculation "only a CFD study or physical prototype
with thermocouples would" resolve (§5). Sizing the internal wall, its
thermal coupling to each sub-zone, and whether it actually reduces the
LMR51430's local ambient below Option 2's figure is a real unknown this
document cannot bound the way it bounded Options 1 and 2's wall-ΔT numbers
from the natural-convection correlation.

**Verdict:** structurally the most promising answer to a real, named gap in
the existing analysis — but it is the option whose validation path runs
through a prototype or CFD study, which the task's own hard constraints
disfavor as a *primary* answer ("do not propose 'build it and measure' as
the primary answer"). Ranked third for that reason, not because the idea is
weak — it is the one direction genuinely worth a follow-on CFD/prototype
study if Option 2 proves insufficient once its own two open items are
resolved.

---

## Ranking

1. **Option 2 (generous volume + chassis conduction), conditional on
   resolving chassis fit and grounding-topology compatibility.** Best
   thermal case with a defensible, in-repo-groundable path; same
   pollution-exclusion strength as the others.
2. **Option 1 (compact, minimum mitigation).** Cheapest and mechanically
   simplest, strongest on pollution exclusion by virtue of having the fewest
   seams — but does not clear the thermal bar with confidence at the repo's
   own 55–70°C worst-case band. Only defensible if that band is treated as
   acceptably rare in practice, which is a product-risk call this document
   does not make.
3. **Option 3 (split-domain), as a follow-on study, not a first build.**
   Addresses a real gap Options 1/2 don't, but its own thermal case cannot be
   verified against anything in this repo today.

**None is a green light as written.** Option 2 is the only one worth
costing out further, and even it needs three specific facts resolved first
(below) before it should be treated as more than "plausible."

---

## Penetrations — every one is a pollution path

The compartment's cable/wire entries, enumerated from `docs/ASSEMBLY_GUIDE.md`
Phase 4 and `docs/COIL_BRACKET_DESIGN.md` §6 (nothing here requires a
schematic change — these are new mechanical/BOM lines, the same category as
the existing HS1/TIM/mounting-hardware "mechanical, not in the 155
electrical components" lines in `docs/hardware/BOM.md` §11):

| Penetration | Source | Proposed seal |
|---|---|---|
| AC mains (L, N, PE) | Input lugs, `ASSEMBLY_GUIDE.md` Phase 4 | IP-rated cable gland, sized to lug gauge |
| Coil leads (Litz, high-current) | Resonant tank terminals, off-board per `PCB_SPECIFICATION.md` Zone B | Cable gland or grommet; note these carry significant current — gland must not constrict/pinch |
| RTD sense wires | `SENSOR_MOUNT_DESIGN.md` interface | Small-gauge grommet |
| Fan PWM header | `CHASSIS_AIRFLOW_DESIGN.md` fan | Small-gauge grommet or panel connector |
| Front-panel UI (encoder, display) | `ASSEMBLY_GUIDE.md` Phase 4 | Panel-mount connector with its own gasket, or multi-conductor gland |
| Compartment mounting itself | M3 standoffs, currently open per `PCB_SPECIFICATION.md` §2.2 | Standoff bosses molded into the compartment tray, not a separate penetration if the tray *is* the standoff structure |

None of these is individually hard — IP-rated cable glands and panel
connectors are commodity parts. The point of listing them is that **the
compliance argument has to address every one explicitly**, not just the
headline heatsink cutout; a certifying body reviewing a cl. 29.2 exception
claim will ask about all of them, and none is currently documented anywhere
in this repo.

---

## What would have to be documented for the cl. 29.2 argument to stand

1. **A construction record** (drawing + BOM entry) defining the compartment
   boundary explicitly: material, wall thickness, and — critically — an
   explicit statement of what is inside vs. outside the sealed volume (the
   full board including Zone B is inside; only the heatsink fin stack, fan,
   and duct are outside). This document does not exist today anywhere in the
   repo (confirmed by search).
2. **A sealing method and inspection criterion for every joint**: lid-to-base
   gasket compression spec, heatsink-cutout conformal gasket compression/gap
   spec (the weakest joint — needs the most rigorous documentation), and each
   cable gland's torque/compression spec.
3. **An assembly work instruction** — `docs/ASSEMBLY_GUIDE.md` Phase 4
   currently says only "Secure the PCB into the chassis using M3 standoffs."
   This needs a real procedure: gasket installation order, inspection step,
   and — importantly — a **rework/service procedure** that reopens and
   reseals the compartment without damaging the seal (a permanently potted or
   RTV-bonded seal is not serviceable; a compressed-gasket-plus-screws design
   is, and should be the default for that reason).
4. **A distinction, stated explicitly in whatever document makes this
   argument** (likely `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` or
   `docs/ENVIRONMENTAL_SPEC.md`), between the appliance's declared external
   IP20 rating (unrelated, addresses user-facing ingress) and this internal,
   non-vented sub-enclosure's own pollution-exclusion claim for one specific
   insulation's microenvironment — so a reviewer doesn't read IP20 as
   contradicting the enclosure argument, or the enclosure argument as
   silently upgrading the appliance's IP rating.
5. **Likely new test scope, not just paperwork**, at the heatsink-cutout
   joint specifically, since it is the one place the fan actively draws
   unfiltered kitchen air across the seal: `docs/ENVIRONMENTAL_SPEC.md` §4
   already has damp-heat and mechanical-stress tests, but nothing that
   exercises a grease/aerosol-laden airflow directly against a conformal
   gasket. This is a genuine incremental validation burden this design does
   not carry today, not a box-ticking documentation exercise.
6. **Citation of the governing clause chain**, matching the rigor already
   used elsewhere in this repo's PD3 work
   (`docs/evidence/2026-07-30-pollution-degree-determination.md` §1): IEC
   60335-2-6 cl. 29.2 Addition text, the specific mechanical facts that
   satisfy "enclosed or located so that it is unlikely to be exposed to
   pollution," and an explicit statement that this reasoning was NOT applied
   to weaken any table figure — only to change which pollution-degree column
   of the same table governs, per the project's own hard rule against
   loosening a safety distance for a green result.

---

## Assumptions and open questions

Each of these is a place the ce-brainstorm skill would normally ask the user
directly; run non-interactively, this document makes the most defensible
assumption and states it, per the task's instructions.

1. **Assumed: the compartment must enclose the whole board (all four PCB
   zones), not a subset.** This follows from PD2/PD3 being a single
   whole-board classification and from Zone B (containing U7/UCC21550,
   named in the sibling brainstorm as one of the two components PD2 would
   unblock) needing to be inside the sealed volume for that benefit to
   apply. **Question for the user:** if the goal is only general thermal/
   margin relief and not specifically unblocking U3/U7's creepage shortfall,
   would a smaller, partial-board compartment be an acceptable target? It
   would be materially cooler and simpler, but would not earn PD2 for Zone
   B's insulation and would not help U3/U7.
2. **Assumed: a direct copper-to-chassis conduction bridge (Option 2) does
   not itself introduce a new safety-relevant ground path**, on the
   reasoning that the chassis is presumably PE-bonded (Class I) and the
   LV_CONTROL ground already references PE via the `gnd ~ pe` bond described
   in the sibling brainstorm. **Question for the user:** confirm the chassis
   metal at the actual compartment-wall location is the same continuous
   PE-bonded body (not an isolated bracket) before building this bridge, and
   confirm it doesn't create a second, unauthorized cross-domain ground
   connection alongside the documented single star-ground point
   (`PCB_SPECIFICATION.md` §7.2).
3. **Assumed: a conformal cutout gasket around the four TO-247/TO-220 package
   bodies satisfies "enclosed... unlikely to be exposed to pollution" for
   the PCB's own creepage paths, even though the packages' tabs remain
   physically open to duct air on their heatsink-facing side.** The
   reasoning: the insulation this clause protects is the PCB copper creepage
   paths, which are fully inside the sealed volume in this design; the
   semiconductor die-to-tab isolation is a separate, already-handled system
   (the Sil-Pad TIM + insulating shoulder washers). **Question for the
   user/certification owner:** confirm this reading is the one a chosen
   certifying body would accept — this is a genuine interpretive judgment
   call, not a settled fact.
4. **Assumed: Option 2's generous envelope is mechanically realizable.**
   Given the board is already longer than the chassis's own (unverified)
   stated width, this is flagged, not assumed resolved. **Question for the
   user:** measure the real RCA 12A3 chassis's internal cavity dimensions
   before committing schedule to Option 2's added volume.
5. **Assumed: cable glands, grommets, and a compartment tray/lid are
   in-scope mechanical/BOM additions, not a "board re-floorplan."** They
   don't touch schematic nets or PCB footprint placement — only enclosure
   hardware, in the same category as the existing heatsink/TIM/mounting-
   hardware BOM lines. **Question for the user:** confirm this reading of
   scope, especially for the compartment mounting standoffs, which may
   replace rather than merely augment the M3 holes currently specified in
   `PCB_SPECIFICATION.md` §2.2.
6. **Not attempted here, by design:** independently sourcing the UCC21550's
   real θJA or verifying whether the LMR51430's copper-pour mitigation is
   actually laid out on `pcb/temper.kicad_pcb`'s copper zones. Both are
   flagged as open in the thermal-bound document and remain open here — no
   option in this document resolves them, and either could independently
   flip the verdict in either direction. **These should be resolved before
   committing schedule to any partition build**, regardless of which option
   is chosen.

---

## Sources

- `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md` (branch
  `analysis/pcb-compartment-thermal-bound`) — the thermal bound this document
  builds on; read in full.
- `docs/evidence/2026-07-30-pollution-degree-determination.md` — PD3
  determination, cl. 29.2 clause text, why coating doesn't help.
- `docs/evidence/2026-07-30-pd2-creepage-row-determination.md` — the 8.0mm
  (not 10.0mm) PD2 reinforced figure at this design's 400V boundary.
- `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md` —
  sibling decision document; its "Option 2" is this document's direct
  predecessor and explicitly left the mechanical/thermal question to a
  follow-up, which this document is.
- `docs/ENVIRONMENTAL_SPEC.md`, `docs/CHASSIS_AIRFLOW_DESIGN.md`,
  `docs/COIL_BRACKET_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`,
  `docs/specs/PCB_SPECIFICATION.md`, `docs/specs/REQUIREMENTS.md`,
  `docs/hardware/SYSTEM_THERMAL_BUDGET.md`,
  `docs/hardware/LMR51430_THERMAL_ANALYSIS.md`, `docs/hardware/BOM.md` — all
  read directly this session.
- `pcb/temper.kicad_pcb` — Edge.Cuts (board size), TO-247-3_Vertical
  footprint confirmed present.
