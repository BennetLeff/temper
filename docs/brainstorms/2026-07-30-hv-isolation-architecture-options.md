<!-- provenance: branch docs/hv-isolation-architecture-options, from origin/main at 8bf18b41 -->

# Mains↔SELV isolation: architecture options, a decision document

**Status:** research/decision only. No `pcb/**` or `elec/src/**` changes. This
document does not choose for you — it lays out what each option costs, what
it clears, and what a human needs to know to choose. Ranking given at the end
is reasoning, not authority.

## Read this first: two corrections to the task's own framing, up front

Both are "don't bury it" items. Neither changes the bottom line (this board
cannot meet 12.6mm reinforced creepage at U3/U7 by parts or placement alone),
but both change how you should read everything that follows.

**1. The RTD ground-topology finding is partly stale, not currently live as
literally stated — but the underlying concern is real and should be fixed in
parallel, not instead of, a creepage decision.** `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:30`
(dated 2026-07-26) describes a single 0Ω star join (`power_return ~ gnd`)
that tied the SELV control domain — MCU, safety interlock, and the
user-touchable RTD probe — directly to the voltage-doubler midpoint, which
tracks AC Neutral, and would track AC Line under an L/N-reversed fault. **That
specific defect was fixed** by `docs/hardware/SELV_ISOLATION_REDESIGN.md`
(commits `6976ef44`, `1390e807`), which removed the star join and rebonded
`gnd` directly to `pe` instead. Verified directly against the current source
on this branch:

```
elec/src/main.ato:714   # REMOVED: the star join (`power_return ~ gnd`) that used to sit here.
elec/src/main.ato:754   gnd ~ pe  # SELV ground reference: bonded to protective earth, NOT to power_return
```

`IEC60335_CRITICAL_COMPONENTS.md` was never updated after that redesign
landed and is stale on this one point — the task brief cites it as if it were
the current state, and it is not. This is worth surfacing because the task
explicitly said not to bury a conflict, and this is one: the document the
brief points at is describing a hazard that has already been remediated.

That said, **the topology is not clean**, and this is not a "nothing to see
here":

- `SELV_ISOLATION_REDESIGN.md` §4 (rows 3–4) documents two *still-live*
  resistive bridges from `dc_bus_plus` into the now-PE-referenced `gnd`: the
  OVP-01 bus-sense comparator divider (~1.3 MΩ) and its ADC-sense sibling
  (~510 kΩ). These are deliberate, engineered constructions —
  `elec/domain_manifest.yaml`'s `protective_impedance_chains` block declares
  both as redundant series-resistor chains (`min_length: 3`, so no single
  resistor failure collapses the impedance), which is IEC 60335-1's
  recognized "protective impedance instead of insulation" provision, not an
  uncontrolled short. But it means the RTD probe is not *fully* separated
  from the DC bus even today — it is separated by a verified high impedance,
  not by insulation distance. `SELV_ISOLATION_REDESIGN.md` §9 already walked
  back `RTDSensing`'s "separated from AC mains potential" docstring claim for
  exactly this reason, on its own initiative, before this task existed.
- Independently, `docs/evidence/2026-07-30-insulation-tier-audit.md` (merged,
  PR #455) established — on grounds that have nothing to do with the star
  join — that the `gnd ~ pe` bond is **not** a continuity-tested,
  impedance-verified protective-earth conductor of the kind IEC 60335-1's
  Class I basic-insulation exception requires (it is ordinary PCB copper,
  reasoned through as an EMI/reference-stability decision, not tested to the
  standard the exception needs). Combined with `LV_CONTROL` being
  operator-accessible (the RTD probe, the panel encoder/power/start-stop/
  reset buttons — all wired directly onto it), this is what makes
  `(DC_BUS, LV_CONTROL)` and `(MAINS, LV_CONTROL)` genuinely REINFORCED, not
  BASIC, independent of whether the star join exists.

**My assessment: the ground topology is a real, separate hazard axis that
should be fixed regardless of which creepage option is chosen — but it is not
a precondition for choosing among them.** REINFORCED insulation governs
`(DC_BUS, LV_CONTROL)` for a reason that has nothing to do with the star join
or the OVP-01 dividers: the domain is user-accessible and has no certified
protective-earth path, full stop. Whether `gnd` floats, tracks AC Neutral, or
is PE-bonded through ordinary copper, none of those states earns the BASIC
exception, so none of them changes the 12.6mm figure this document is about.
Fixing the ground topology does not relax the creepage requirement, and not
fixing it does not add a new creepage requirement beyond what
`IEC60335_REQUIREMENTS` already encodes. Treat Option 4 (below) as running in
parallel with whichever creepage option is chosen, not as a gate in front of
it — but do not defer it indefinitely either: if the RTD probe's safety case
ultimately leans on "a fault trips protection fast enough," that argument
needs the ground topology (and OVP-01's own tuning history, which has already
had one fail-open revision caught and fixed) to be independently verified,
not assumed.

**2. The PD2 creepage figure has a real, disclosed conflict, and I can
partially resolve it — but not with full confidence, and this materially
changes Option 2's payoff.** PR #442 (merged) computed PD2 reinforced
creepage at this boundary as **10.0mm**, reasoning that 400V exceeds a 300V
table row and must round up to the next (400V) row, which it read as 10.0mm.
PR #464 (open, not yet merged) independently re-derived the same boundary
from IEC 60335-1 **Table 17** (not Table 16, which PR #442 cites — PR #464's
own §4.1 identifies this as a pre-existing mislabel) and found row iv is
stated as **">250V and ≤400V"**, PD2-IIIa/IIIb column **4.0mm basic / 8.0mm
reinforced** — not 5.0/10.0.

**These cannot both be literal readings of the same table.** The determining
fact is row iv's own stated boundary: it is closed at "≤400V," not open at
"<400V." DC_BUS's working voltage (400V absolute maximum/transient, per
`elec/src/main.ato`'s own `v_bus_abs_max`/`v_bus_max` assertions) sits exactly
at that boundary, inside row iv, not above it — so PR #442's own
no-interpolation reasoning ("a voltage between two rows takes the next row
up") doesn't apply here at all: 400V isn't *between* rows iv and v, it's the
literal upper edge of row iv. I did not independently re-fetch IEC 60335-1's
primary text this session to confirm this beyond what's already in-repo (this
project's own long-standing, repeatedly-disclosed caveat: the primary text is
paywalled and every prior creepage evidence doc in this repo carries the same
UNVERIFIED-at-primary flag). But two things corroborate PR #464's reading
over PR #442's: (a) the boundary text itself, quoted directly in
`docs/evidence/2026-07-30-pollution-degree-determination.md` §3 from a
300dpi page render of IS 302-1:2008 (identical adoption of IEC 60335-1),
and (b) **five independent prior investigative sessions in this repo's
history** (cited in that same document, §5.1–5.4) all derived 12.6mm PD3
reinforced by treating PD2 row iv as 8.0mm, not 10.0mm — i.e., the entire
rest of this repo's PD3 work already implicitly agrees with PR #464, and
PR #442's 10.0mm stands alone, uncorroborated anywhere else. **My reading:
PR #464 is more likely correct, and PR #442's PD2 figure (10.0mm) is an
off-by-one-row error — the real PD2 figure at this boundary is 8.0mm
reinforced, not 10.0mm.** This is reported as my assessed reading, not a
primary-text derivation of my own, and PR #442's merged figure has not been
corrected by this document — that is a decision for whoever owns that PR,
flagged here because it is load-bearing for Option 2 below.

**Why this matters:** at 8.0mm reinforced (my reading), **U3 (8.560mm best
achievable) and U7 (8.100mm best achievable) both clear PD2** — the two
blockers that no market search or CP-SAT re-solve can otherwise fix simply
evaporate, provided PD2 can be legitimately earned (Option 2). At 10.0mm
(PR #442's merged figure), they do not. This single row-selection question is
one of the highest-leverage open items in this whole decision, and it should
be nailed down — ideally against primary IEC 60664-1 Table F.2 or IEC 60335-1
Table 17 directly — before committing schedule to Option 2.

---

## Facts recap (verified this session, not re-derived)

- **Reinforced creepage requirement:** 12.6mm at PD3, 400V, Material Group
  IIIa/IIIb (`docs/evidence/2026-07-30-pollution-degree-determination.md`,
  PR #464, **open, not yet merged to `main`**). PD3 governs because
  IEC 60335-2-6 clause 29.2 Addition makes PD3 the default microenvironment
  for cooking appliances specifically (overriding IEC 60335-1's general PD2
  default), and the PD2 exception requires an enclosure/sealing argument this
  design does not currently make (`docs/CHASSIS_AIRFLOW_DESIGN.md`,
  `docs/COIL_BRACKET_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`, IP20 — all read
  directly this session; confirmed forced-air-vented cavity, no gasketed PCB
  compartment, IP20 explicitly "no liquid ingress protection guaranteed").
- **Violation count:** REQ-SAFE-01 currently reports **98 violations / 52
  pairs** on `main` today (the PR #442-merged PD2/10.0mm figure).
  **138 / 86 pairs** is what PR #464's not-yet-merged PD3/12.6mm correction
  produces on the same, unchanged board.
- **The irreducible package-class gap is U3 and U7 specifically, not all
  five originally-named isolators.** After exhaustive sourcing work already
  done in this repo (`docs/brainstorms/2026-07-30-isolator-component-sourcing.md`,
  plus the PD3-part-selection survey cited in the pollution-degree
  determination doc §5.4):
  - **C6** (Y-capacitor): a real, in-catalog part clears 12.6mm — TDK/EPCOS
    `B81123C1222M000`, 15.00mm lead spacing, ~13.5mm achievable.
  - **K2/K3** (discharge relays): a real, in-stock part clears 12.6mm on
    *both* independent grounds — TE Connectivity/Schrack `RT314012`,
    manufacturer-rated ≥10/10mm coil-contact creepage/clearance (VDE
    40007571, cULus E214025, cCSAus 1142018, "in accordance to IEC 60335-1"),
    and 12.760mm achievable board-copper gap on its stock KiCad footprint.
    DigiKey 1128622, 7,442 in stock at last check.
  - **U7** (UCC21550 gate driver): best achievable **8.100mm**, on TI's own
    published "HV/ISOLATION OPTION" land pattern (SLUSE89C). No TI land
    pattern, and no checked competing part (including the larger UCC21750),
    exceeds this. I independently re-checked a newer TI part in the same
    family this session — **UCC21732** (`ti.com/lit/ds/symlink/ucc21732.pdf`,
    fetched and text-extracted directly) — and it publishes the *identical*
    ">8mm" CLR/CPG spec and the identical 7.3mm/8.1mm land-pattern figures on
    the same SOIC-16 DW package. This corroborates, rather than changes, the
    repo's prior exhaustive finding.
  - **U3** (H11L1 optocoupler): best achievable **8.560mm**, on the
    already-corrected 400-mil DIP-6 lead form. Vishay's VOW136 (a wide-body
    DIP-8 part whose own datasheet claims ≥10mm creepage) converts to the
    *same* 8.560mm board copper gap at its equivalent 10.16mm pitch — the
    datasheet's creepage figure is measured along the package body surface,
    not the straight-line PCB copper gap this project's gate (and, per my
    own web research below, most real safety-review practice) actually
    checks.
  - Neither U3 nor U7 has a sourced or checked candidate anywhere near
    12.6mm. This is a **package-class gap**: DIP/SOIC lead pitch tops out
    around 10–11mm total body width for anything in production in this
    power/pin-count class, and pad diameter always eats back into the pitch.
- **Placement cannot fix U3/U7 either.** `docs/evidence/2026-07-28-barrier-constrained-placement.md`
  ran CP-SAT with the barrier as a hard constraint and got `INFEASIBLE` in
  ~23s — the isolators' HV-pad-to-SELV-pad separation is a property of the
  footprint's own origin, invariant under translation/rotation. No placement
  search can change it.
- **A copper-aware full-board re-solve does clear the 21 genuinely
  placement-fixable pairs** (`docs/evidence/2026-07-30-copper-aware-domain-resolve.md`),
  at either the 8.0mm or 10.0mm threshold, `status=optimal`, audited with 0
  mismatches — but only by moving essentially every component on the board
  (median displacement ~100–116mm on a 152×234mm board), which strands the
  board's existing 2338 routed track segments, 48 vias, and 96 zones (DRC
  `shorting_items` and `unconnected_items` both measurably regress). This is
  a real fix for those 21 pairs, but it is a full re-layout-and-reroute
  project, not a drop-in constraint update.
- **7 pairs (all `C27<->X`) are a netlist/PCB reference-designator resync
  defect**, unrelated to any option below (`scripts/check_copper_net_consistency.py`,
  10 pre-existing pad-mismatch violations). The real tank capacitor these
  pairs are mislabeling has no verified physical position on the board right
  now — an unsafe-direction coverage gap. This should be fixed regardless of
  which architecture option is chosen; it is orthogonal to all five.

---

## Options

### Option 1 — Certified isolation modules (swap the IC for a better-certified one)

**What changes:** nothing feasible, for U3/U7 specifically, as literally
scoped. C6 and K2/K3 already have real part-substitution fixes (above) — but
those are ordinary component sourcing, not really "Option 1" in the sense the
task is asking about, and they should happen regardless of which of the five
architecture options is chosen.

**The crux question, answered:** *does a component's own agency certificate
(UL 1577, VDE 0884, CQC GB4943.1, IEC 60747-5-5/-17) substitute for PCB
creepage/clearance under IEC 60335-1?* **No, not in the sense of letting you
skip the check.** I verified this against a live source this session — TI's
own "Demystifying Clearance and Creepage Distance for High-Voltage End
Equipment" (SLUP419, `ti.com/lit/pdf/slup419`, fetched and text-extracted
directly), which states plainly: *"The parameters addressed in these
certification standards [DIN VDE V 0884-11, UL 1577, CQC GB4943.1] describe
the insulation barrier, and do not directly relate to creepage and
clearance. What does matter for creepage and clearance are the isolation
grades, such as basic, reinforced and functional."* Creepage/clearance is a
separate, independently-computed system requirement (working
voltage/pollution degree/material group, against the applicable table — IEC
60335-1 Table 17 for this appliance class) that the PCB must still satisfy
using the component's own external CPG/CLR rating on its recommended land
pattern. This matches, rather than contradicts, what every isolator
datasheet already checked in this repo says explicitly — TI's own footnote
on the UCC21550/UCC21732: *"Care must be taken to maintain the creepage and
clearance distance of a board design to ensure that the mounting pads of the
isolator on the printed circuit board (PCB) do not reduce this distance."*
The certificate proves the internal barrier (dielectric withstand, partial
discharge); the external creepage number is a second, independent thing you
still have to hit on your own board, and this board's specific gap is that
no available part's external creepage, on any real land pattern, reaches
12.6mm in this component class.

**What it buys:** nothing new for U3/U7 at PD3. The C6/K2/K3 substitutions
(already found, cited above) clear those three regardless of which
architecture option is chosen — treat them as already-actionable, not
contingent on this decision.

**New risks:** none if not pursued as a standalone bet — it is a dead end
that has now been checked twice independently in this repo plus once more by
me this session (UCC21732), not a live option with unexplored upside.

**What would confirm it (if you want to keep looking):** a datasheet, from a
manufacturer not yet checked, publishing an external CPG/CLR rating ≥12.6mm
*on a land pattern that converts to that same net PCB copper gap* — not a
package-body-surface creepage figure that (like VOW136's) doesn't survive
translation into a straight-line board gap at achievable lead pitch. I did
not find one. The genuinely productive version of "use a certified module"
is a *potted/encapsulated* module with large physical pin-to-pin separation
by construction — which this board already does successfully for the
AuxSupply (Mean Well IRM-10-15, 35.5mm achievable gap, 4.2kVAC I/O withstand,
IEC 62368-1/61558-1/-2-16 certified) — but that is functionally Option 3, not
a like-for-like IC swap. See below.

---

### Option 2 — Sealed electronics compartment to earn PD2

**What changes:** a real, gasketed, non-vented enclosure around the PCB(s)
carrying U3/U7, physically excluded from the coil/heatsink forced-air path
that `docs/CHASSIS_AIRFLOW_DESIGN.md` currently routes directly across the
board cavity. This is a new mechanical subsystem, not a documentation change
— the current design has zero precedent for it: `docs/ASSEMBLY_GUIDE.md`'s
only gasket seals the glass-ceramic cooktop panel to the chassis, a
different joint entirely; the PCB itself mounts on plain M3 standoffs with no
enclosing box. IP20 ("no liquid ingress protection guaranteed") argues
against, not for, an enclosure claim, though IP-rating and pollution-degree
sealing are formally separate questions (IP is about the whole appliance's
ingress rating; PD2 is about whether *this specific insulation's*
microenvironment is protected from conductive pollution).

**Cost:** new enclosure design (walls, gasket material, likely a
sub-compartment inside the existing chassis rather than a chassis-wide
redesign), a new BOM line for the seal, and a mechanical engineering pass to
prove the enclosure boundary is actually continuous (cable/connector
penetrations into a sealed compartment need their own sealing, or they
reopen the pollution path the enclosure exists to close). **A real
engineering tension I have not resolved here:** U7 (the gate driver) needs
to be electrically close to the IGBTs it drives, and the IGBTs sit on the
same forced-air heatsink path this option would need to exclude the PCB
from. Whether the isolator components specifically can be sealed away from
airflow while the power semiconductors they drive remain in the airflow
path is a mechanical layout question this document does not answer — it
needs a person who can look at the actual board-to-heatsink geometry, not a
document review.

**What it buys, and why the PD2 conflict above is the crux:** IEC 60335-1
Table 17's clearance table (not creepage — clearance is keyed to impulse
voltage/overvoltage category, not pollution degree, confirmed in PR #464 §4.1
and independently in PR #442's own analysis) is unaffected either way; only
creepage moves. **If PD2 is genuinely 8.0mm reinforced at this boundary (my
reading, above) — sealing the compartment clears U3 (8.560mm, 0.460mm margin)
and U7 (8.100mm, 0.000mm margin against the exact reading, though the
sourcing doc's own board-resync-corrected figure gives 8.100mm vs 8.0mm, a
0.1mm margin) —** the two blockers nothing else in this document can fix.
**If PD2 is actually 10.0mm (PR #442's merged figure) — sealing the
compartment buys nothing for U3/U7 at all**, and this option should be
re-ranked down to "does nothing for the hardest problem." **This has not
been resolved with certainty in this document — get a primary-text answer
before committing schedule to this option.**

Even under the favorable reading, the margins are razor-thin — the isolator
sourcing document's own language calls the 8.1mm U7 figure "a 'just clears
it' result, not a comfortable one." A human choosing this path should treat
it as a knife-edge pass requiring tight manufacturing tolerance control
(solder mask registration, drilling, pad etch), not a comfortable design
margin, and should independently re-verify PD2's exception test (the
enclosure/sealing argument) is actually earned for the *whole* board's
insulation, not just the five isolators — PD2 vs PD3 is a single
environmental classification applied uniformly, not a per-component pick.

**New risks:** thermal (see above, unresolved), a new failure mode if the
seal degrades over the appliance's service life (this is a cooking
appliance — grease/steam exposure at the seal boundary over years of use is
exactly the failure mode PD3's default assumption exists to guard against),
and schedule risk tied directly to the unresolved PD2-figure question.

**Evidence needed to confirm:** (1) the primary-text PD2 row-iv figure,
resolved with certainty; (2) a mechanical design proving continuous
enclosure boundary including cable/connector penetrations; (3) confirmation
the IGBT/heatsink thermal path doesn't require the isolator components to
share the same forced-air cavity.

---

### Option 3 — Move the isolation boundary off-board

**What changes:** replace U3's and U7's *on-board, bare-die* isolation
function with a physically larger, modular isolation element whose creepage
comes from mechanical construction rather than fine IC lead pitch — the same
pattern this board's own AuxSupply (PS1, Mean Well IRM-10-15) already uses
successfully. Concrete forms, none independently verified against a
datasheet in this pass (flagged, not claimed):

- A small isolated daughtercard for the ZCD (U3) and/or gate-drive (U7)
  signal path, connected to the main board via two physically separate
  connectors (one per domain) whose pin groups are trivially >12.6mm apart —
  this converts a fine-pitch IC-footprint problem into an ordinary connector
  placement problem, which is categorically easier.
- A classic magnetic gate-drive transformer for U7 — transformer
  bobbin/core construction often achieves large creepage by default, without
  needing a certified-IC-class part at all. **Not checked against a real
  datasheet in this session — a genuine candidate direction, not a verified
  one.**
- A redesigned zero-cross-detection method for U3 that senses from an
  already-isolated point (e.g., derived from the gate-drive secondary side)
  rather than needing its own dedicated barrier-crossing device at all —
  this would eliminate U3 as a component, not just relocate it.

**Cost:** real schematic redesign scope (currently out of this task's
read-only bounds, but the honest scope estimate is weeks, not days) — new
connector/cable BOM lines, an EMI review for the added cable/connector
interface (a new radiator/receptor path that doesn't exist today), mechanical
space for a daughtercard, and re-verification of ZCD timing, which
`SELV_ISOLATION_REDESIGN.md` §10 already flags as "sized by hand-calculation,
not bench-verified" even in the current design — a redesign would need to
close that gap too, not just relocate the open item.

**What it buys:** potentially clears U3 *and* U7 permanently, **at any
pollution degree** — this option does not depend on the PD2/PD3 row dispute
at all, because it stops relying on borderline IC package geometry entirely.
This is the most robust option in this document for exactly that reason.

**New risks:** added mechanical complexity and a new assembly step
(connector mating — a real field-failure mode if a connector isn't fully
seated), a new EMI path, and it does nothing for the 21 placement-fixable
pairs or the C27 data-integrity defect — those still need the copper-aware
re-solve/reroute and netlist resync regardless.

**Evidence needed:** a datasheet-verified isolated module or transformer
candidate for both U3's and U7's actual functions, with confirmed creepage
adequate at whichever PD figure ultimately governs, plus a connector/EMI
analysis and revised ZCD timing verification.

**Why I believe this is buildable, not hypothetical:** PS1 is not a proposal
— it is already a shipped design element on this exact board, using exactly
this pattern (isolated module, 35.5mm achievable gap, full certified
reinforced isolation, in production). This is the strongest piece of
evidence in this whole document that the *category* of fix works; the open
question is only whether a suitable module exists for U3's and U7's specific
functions at the right size/cost, which was not checked against a live
datasheet in this pass.

---

### Option 4 — Re-architect the ground topology

**What changes:** close the two remaining OVP-01 resistive HV→SELV bridges
as genuine isolated sense paths, per the two options `SELV_ISOLATION_REDESIGN.md`
§5 already laid out (not implemented there, and not implemented here
either): (A) move the comparator to the HV side, referenced to
`power_return`, and carry only a digital fault bit across an opto — smaller
isolator, needs a new HV-referenced bias supply that doesn't exist today; or
(B) an isolated differential amplifier (AMC1311/AMC1301-class) sensing the
true full bus differentially — matches the top-level spec more directly,
needs a second isolated domain referenced to `hv_minus`. A more ambitious,
**exploratory, not fully scoped** variant: build out `gnd ~ pe` into an
actual continuity-tested, impedance-verified Class I protective-earth
conductor (not just a DC bond), which — per the insulation-tier audit's own
§2.2 criteria — could in principle let `LV_CONTROL` legitimately earn the
BASIC-insulation exception instead of REINFORCED, cutting the creepage bar
roughly in half (6.3mm at PD3 instead of 12.6mm). This would be a much larger
undertaking than the resistive-divider fix and is flagged here as a
direction, not a costed plan.

**Cost:** real schematic redesign (new comparator topology or isolated
amplifier + bias supply), worst-case-corner re-verification (the rigor
`LogicUVLOComparator`/UVL-02 already got, per its own design doc's
precedent), and — this design's own comparator-tuning history is a real
cautionary note here, not a hypothetical one — OVP-01 has already had at
least one fail-open revision caught and corrected in this repo's history;
re-tuning a safety comparator carries real risk of getting it wrong again,
not just cost.

**What it buys:** closes a real, if narrow (high-impedance, not a short),
hazard, and makes the RTD probe's "separated from mains" claim fully rather
than partially true. **It does not, by itself, reduce the REINFORCED
creepage requirement or clear any of the 138/86 REQ-SAFE-01 violations**
unless pursued all the way to a certified Class I PE construction (the
exploratory variant above) — which is a much bigger undertaking than fixing
the two dividers alone, and not costed here.

**New risks:** re-tuning risk (above); if the Class I PE route is attempted,
an entirely new continuity/impedance test regime and construction this
design does not have today.

**Evidence needed:** worst-case-corner re-verification of whichever
remediation option is chosen; if the Class I PE route is pursued, an actual
continuity/impedance test plan and construction meeting IEC 60335-1's own
requirements for that exception.

**Relationship to Options 1–3/5: run in parallel, not as a gate.** As
established at the top of this document, none of the creepage figures in
this document depend on which ground-topology state exists — fix this
because it is a real, separate hazard, not because it unblocks anything
above.

---

### Option 5 — Documented deviation

**What would have to be argued, and to whom:** a case to whatever notified
body/test house is performing IEC 60335-1 (or its national deviation — UL
60335-1, CSA) compliance assessment, that the ~4.0–4.5mm creepage shortfall
at U3/U7 (12.6mm required, 8.1–8.56mm achieved) is acceptable despite not
meeting the literal table figure. Typically this would need either (a) an
alternative-method argument that the component's own certified isolation
(dielectric withstand, partial discharge) plus its own external
creepage/clearance rating together constitute adequate protection even
though the number is short of the appliance table's figure, or (b) a
risk/consequence argument (e.g., a let-through-energy/fault-clearing-time
analysis showing a creepage-path failure trips protection before it can
injure a user) — a real engineering study this document has not done and
that would need to be completed and brought to the certifying body *before*
tooling, not discovered after.

**Is it credible? My honest assessment: not on its own, no.** Pollution
degree 3 by definition assumes conductive pollution *will* be present at the
insulation surface — that is what PD3 means, and it's exactly the appliance
category (cooking ranges/hobs) IEC 60335-2-6's own Addition clause exists to
capture. The insulation-tier audit already independently confirmed the
SELV side of this exact boundary is user-touchable (the RTD food probe,
panel controls) — not merely accessible in a fault, accessible in normal
use. Asking a notified body to accept a creepage shortfall against a directly
touchable, food-contact surface, in the pollution degree the appliance's own
governing standard designates as the default for this appliance class, is
not a strong starting position. I would not expect it to be accepted as a
standalone argument. It becomes more credible only in combination with a
real supplementary mitigation (the fault-clearing-time study above) that has
not been done — treat this as a last-resort fallback if Options 2 and 3 both
slip, not a parallel-track option to plan around from the start.

---

## Ranking, and why

1. **Resolve the PD2 figure conflict first — it is a five-minute lookup that
   changes everything downstream.** This is not really "an option," it is a
   precondition for evaluating Option 2 honestly, and I'd put it ahead of
   any of the five.
2. **Option 2 (sealed compartment), conditional on that lookup confirming
   8.0mm at PD2.** If it holds, this clears both irreducible blockers
   (U3, U7) with a mechanical, not electrical-topology, change, and does so
   without touching the schematic at all. But the margins are razor-thin,
   the thermal-path tension with the IGBT heatsink is unresolved, and if the
   lookup goes the other way (10.0mm), this option clears nothing for U3/U7
   and should drop to the bottom of this list.
3. **Option 3 (move isolation off-board).** The most robust fix — works
   regardless of the PD2/PD3 dispute, doesn't depend on knife-edge
   manufacturing margins, and has a working precedent already on this board
   (PS1). Costs the most schedule (real redesign, new BOM lines, connector/
   EMI risk) and needs component research this document didn't complete.
4. **Option 1, as literally scoped, is not viable** for U3/U7 — it is
   subsumed by Option 3 for anything beyond the already-actionable C6/K2/K3
   substitutions, which should happen regardless of which option above is
   chosen.
5. **Option 4 (ground topology), run in parallel with whichever of 2/3 is
   chosen, not instead of it.** Real, worth doing, cheap relative to the
   others, does not by itself move the creepage numbers.
6. **Option 5 (deviation), fallback only**, and only credible alongside a
   real supplementary engineering study not yet done.

---

## Questions only a human can answer

- **The PD2 row-iv figure: 8.0mm or 10.0mm?** Needs a primary IEC 60664-1
  Table F.2 / IEC 60335-1 Table 17 lookup, or an explicit decision to
  standardize on the more conservative 10.0mm regardless of the literal
  reading, given this project's repeated paywalled-primary-text caveat on
  this exact table.
- **Is a sealed, gasketed PCB compartment mechanically and thermally
  compatible with the IGBT heatsink's forced-air cooling on this board?**
  This needs a mechanical engineer looking at the actual board-to-heatsink
  geometry, not a document review — I could not resolve it here.
- **Cost/schedule tolerance:** a fast, cheap, thin-margin fix (Option 2, if
  the PD2 reading holds) versus a slower, more robust redesign (Option 3) —
  this is a business call, not an engineering one.
- **Priority on Option 4:** worth doing in parallel regardless, but how soon
  relative to the creepage fix, and with how much re-verification rigor
  (given OVP-01's own fail-open history)?
- **Certification strategy:** which body and standard actually governs (IEC
  60335-1 via a CE route, UL 60335-1, CSA)? This affects which agency
  certifications from Option 1's research (VDE vs. UL vs. CQC) actually
  matter, and how a deviation (Option 5) would need to be framed and to
  whom.
- **Fallback tolerance:** is the team willing to pre-engage a notified body
  about Option 5 as an explicit fallback if 2 and 3 both slip, or should
  that path be treated as closed unless and until a fault-clearing-time
  study is separately commissioned?

---

## Sources

- `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` §2 (RTD/ground-topology
  finding as originally stated; confirmed stale on the star-join point,
  §"Read this first" above)
- `docs/hardware/SELV_ISOLATION_REDESIGN.md` (the star-join fix, the
  remaining OVP-01 crossings, §5's remediation options, §9's docstring
  walk-back, §10's ranked open items)
- `elec/src/main.ato` (current ground-topology source, verified directly:
  lines ~505–754, `gnd ~ pe`, the removed star join)
- `elec/domain_manifest.yaml` (`protective_impedance_chains` block)
- `docs/evidence/2026-07-30-insulation-tier-audit.md` (PR #455, merged —
  REINFORCED confirmed correct independent of ground topology)
- PR #442 (`docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`,
  merged — PD2 voltage-row fix, the 10.0mm figure)
- PR #464 (`docs/evidence/2026-07-30-pollution-degree-determination.md`,
  **open, not merged** — PD3 determination, the 12.6mm figure, Table 17 row
  iv, the disclosed PD2 row-selection tension in its own §3.1)
- `docs/brainstorms/2026-07-30-isolator-component-sourcing.md` (U3/U7/C6/K2/K3
  live datasheet sourcing)
- `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md` (fix-class
  survey of all 33/76 pairs, Group A/B/C classification)
- `docs/evidence/2026-07-28-barrier-constrained-placement.md` (CP-SAT
  `INFEASIBLE` proof)
- `docs/evidence/2026-07-30-copper-aware-domain-resolve.md` (copper-aware
  re-solve, the reroute-strand finding)
- `docs/CHASSIS_AIRFLOW_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`,
  `docs/ENVIRONMENTAL_SPEC.md` (IP20, PD2 as currently stated pre-PR#464,
  forced-air cavity)
- TI, "Demystifying Clearance and Creepage Distance for High-Voltage End
  Equipment," SLUP419, March 2024 — `https://www.ti.com/lit/pdf/slup419`
  (fetched and text-extracted this session; the certificate-vs-creepage
  quote in Option 1)
- TI, UCC21732 datasheet — `https://www.ti.com/lit/ds/symlink/ucc21732.pdf`
  (fetched and text-extracted this session; independent re-confirmation that
  no wider land pattern exists in this TI package family, §5.6 Insulation
  Specifications, §10.1 Layout Guidelines)
- Prior citations for U3/U7/C6/K2/K3 datasheets (TI UCC21550 SLUSE89C,
  onsemi H11L1M/H11L2M/H11L3M, Vishay VY1 series doc 28537, Vishay VOW136
  doc 84156, TE RT1 `ENG_DS_RT1_0718`) reused from
  `docs/brainstorms/2026-07-30-isolator-component-sourcing.md`, not
  independently re-fetched this session.
