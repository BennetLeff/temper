<!-- provenance: commit=b39035f508d208b92ce4061e890662acf3262ceb dirty=false -->

# K2/K3 bus-discharge relay coil<->contact isolation: real replacement candidates, and why "drop-in" doesn't quite hold

Base commit: `fed05e82` (`merge: barrier-constrained placement is INFEASIBLE -- and
it is a BOM problem`), branch `docs/methodology-loop-discipline`. Work done in
worktree `agent-a6a0afe3187e45fa9`, branch `k2k3-discharge-relay-isolation`,
checked out directly at that commit.

This document is research/reporting only, matching the precedent set by the
two sibling evidence docs it builds on
(`docs/evidence/2026-07-28-isolation-keepout.md`,
`docs/evidence/2026-07-28-barrier-constrained-placement.md`, and
`docs/evidence/2026-07-28-creepage-requirement-determination.md`, the last
read via `git show f6646c82:...` since it lives on a sibling branch not yet
merged into this base commit). **No BOM, `elec/src/modules.ato`,
`elec/src/components.ato`, `elec/domain_manifest.yaml`, or
`pcb/temper.kicad_pcb` was touched** -- verified clean (`git status --short`
empty) throughout. This is a deliberate choice: the two real candidates found
below need a pin-mapping and footprint verification pass (see "What a human
must still verify") before they belong in the BOM, so this doc reports
findings for that follow-up rather than committing to one.

## Verdict up front

**Two real, independently-verified relay part numbers exist with adequate
coil<->contact isolation for this exact role, and neither requires a
topology change (still an SPDT relay, still a 12V coil, still driven by the
existing dropper/MOSFET/flyback circuit).** Both were verified by fetching
the actual manufacturer PDF datasheet directly this session (not from
memory, not from a distributor blurb) -- full citations below.

- **Panasonic Industry `ALZN1B12W`** (LZ-N series, 1 Form C / SPDT, 12V DC
  coil, Class B insulation): **10 mm minimum** coil-to-contact
  clearance/creepage, 5,000 Vrms dielectric, 10,000 V surge withstand,
  EN60335-1 GWT compliant, explicitly listed for "Home appliance"
  applications.
- **American Zettler `AZ770-1C-12D`** (1 Form C / SPDT, 12V DC nominal
  coil): **8 mm minimum** coil-to-contact creepage AND clearance, 5,000 Vrms
  dielectric, 10,000 V surge, explicitly states "Reinforced insulation, EN
  60730-1 (VDE 0631, part 1)" with an EN 60335-1 (GWT) approved variant, UL
  file E44211, VDE certificate 40006815.

Both numbers **comfortably clear both ends of this repo's disputed
6.5-8.0 mm range** (10 mm and 8.0 mm respectively vs. the 6.32 mm the
current Omron G5LE-1 achieves) -- so this finding survives however the
parallel creepage-figure reconciliation resolves, per the task's own
instruction not to optimize for one number.

**But "drop-in" is the wrong word, and the falsifier only partly holds** --
see "Falsifier verdict" below. Both candidates force a footprint change and
a `components.ato` pin-mapping change (the existing `Relay_SPDT` component
is hardcoded to the Omron G5LE-1's own physical pinout). Neither candidate's
datasheet gives an explicit, manufacturer-warranted DC contact rating at the
circuit's actual 170-200 V working voltage -- but this is a **pre-existing,
not-worsened** gap: the current G5LE-1 has exactly the same limitation,
already flagged in this repo's own `modules.ato` comments, mitigated by an
RC snubber, not by a catalog number. Swapping parts does not fix or break
that separate concern.

## Task 1 -- what K2/K3 actually are and what they must do

All of the following is DERIVED directly from `elec/src/modules.ato`'s
`BusDischarge` module (lines 836-1113) and `elec/domain_manifest.yaml`, this
worktree's own primary source, cross-checked against `pcb/temper.kicad_pcb`'s
real pad coordinates (unchanged from the two sibling evidence docs' own
independent measurements, reproduced here rather than re-derived from
scratch since nothing about the board geometry changed between their base
commits and this one).

- **Part:** Omron G5LE-1 DC12 (`Relay_SPDT` component,
  `elec/src/components.ato:312-332`), designator prefix `K`, footprint
  `Relay_THT:Relay_SPDT_Omron-G5LE-1`. Pin mapping (VERIFIED 2026-07-16 per
  the component's own docstring, against `omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf`
  cross-checked with the KiCad community symbol tied to this footprint):
  pin 1 = COM, pins 2 & 5 = coil (non-polarized), pin 3 = NO, pin 4 = NC.
- **Function:** `BusDischarge` (instantiated once in `Top`, contains both
  `k_dis1`/K2 and `k_dis2`/K3) provides fail-safe active discharge of the
  340 V DC bus to <34 V in <60 s on ANY loss of power (unplug, fuse, aux-
  supply fault, MCU dead), with **zero MCU/firmware involvement in the
  fail-safe path itself**. Each relay's coil is held energized from the 15 V
  SELV rail whenever the unit runs, holding its NC contact OPEN (discharge
  disengaged). Losing power drops the coil, the NC contact closes by spring
  force alone, and a resistor string (`r_dis1a`+`r_dis1b` = 7.8 kohm for
  K2's half-bus, `r_dis2a`+`r_dis2b` = 7.8 kohm for K3's half-bus) is
  switched across each 170 V half-bus. **This "coil de-energized -> contact
  closes with no external power" property is inherent to a mechanical NC
  contact and is the reason this circuit uses a relay at all** -- see Task 3.
- **Coil:** 12 V DC, 33.3 mA, 360 ohm, 400 mW (Omron G5LE-1 catalog figure,
  cited in the module docstring). Driven from the 15 V rail through a
  dedicated 100 ohm/0.25 W dropper per coil (`r_coil1`/`r_coil2`, Yageo
  RC1206FR-07100RL) -> ~11.7 V at the coil, 97.5% of rated (G5LE
  must-operate voltage is 75% of rated, so this has real margin). A shared
  low-side MOSFET (`q_dis_drv`, AO3400A) with its own gate resistor/pulldown
  switches both coils together; `DISCHARGE_CTRL` high = energized = NC open
  = discharge disengaged, matching `PowerInput`'s `bypass_relay` pattern
  exactly.
- **Contacts (what actually gets switched):** each NC contact carries the
  100R+470nF RC snubber's steady leakage (negligible, cap blocks DC) and,
  on de-energize, closes onto a live half-bus tap. Per the module's own
  sizing comments: **break current ~21.8 mA, up to 170 V DC nominal / ~200 V
  worst-case (bus tolerance), purely resistive** (peak power at closure:
  3.7 W per string, well under the resistors' 5 W rating). **Contact catalog
  rating is 10 A / 250 V AC** (Omron G5LE-1 general catalog figure) -- but
  the module's own docstring already flags (VERIFIED 2026-07-16 against
  Omron datasheet K100-E1-08) that **the DC load curve tops out at 125 V,
  with 30 V DC being the UL/CSA-recognized ceiling -- a 170 V DC break is
  out-of-catalog at ANY current.** This is mitigated, not resolved, by
  design: 21.8 mA is far below the ~0.4 A minimum arc-sustain current of Ag
  contacts (5.4% of it), and the RC snubber limits opening dV/dt to
  ~38 V/ms so the contact gap is fully open before it sees bus voltage.
  **This is a real, pre-existing, already-documented gap in this repo, not
  something this task introduces or needs to newly discover** -- it matters
  here only because it constrains which replacement parts are acceptable
  (see hard-rule discussion below): a replacement must not be WORSE on this
  axis even though fixing it outright is out of this task's scope.
- **Expected operations over life:** **ASSUMED, not found in this repo.**
  No document under `docs/` or `elec/` gives a duty-cycle/cycle-count spec
  for K2/K3 specifically (checked `docs/ENVIRONMENTAL_SPEC.md`,
  `docs/REGULATORY_COMPLIANCE.md`, grepped for "cycles"/"duty cycle"/
  "operations" repo-wide -- nothing part-specific for the discharge relays).
  Since discharge only engages on a power-down event (not a normal cooking
  cycle), a reasonable order-of-magnitude estimate is **thousands, not
  millions, of operations over product life** (e.g. a few power-cycles/day
  x 10-year life ~= 10^3-10^4 operations) -- this is DERIVED reasoning from
  the module's own described trigger condition, not an independently
  sourced number, and is comfortably below every mechanical-life figure
  seen on any relay datasheet fetched this session (10^6-10^7 range).

## Task 2 -- real replacement candidates

Both candidates below were verified by fetching the actual manufacturer PDF
directly this session via `WebFetch` (both returned as saved binary PDFs and
were read with the `Read` tool -- not reconstructed from search snippets or
distributor marketing copy). `WebSearch` was exhausted (200/200 used
elsewhere in this shared environment before this task started, same
constraint the sibling creepage-requirement doc hit); `lite.duckduckgo.com`
worked as a lookup path to find the direct PDF URLs, which were then fetched
and read directly.

### Candidate A: Panasonic Industry `ALZN1B12W` (LZ-N series)

**Source (fetched and read directly this session):**
`https://mediap.industry.panasonic.eu/assets/download-files/import/mech_eng_lzn.pdf`
(Panasonic Industry Co., Ltd., Cat. No. ASCTB395E, dated 2022.4, "LZ-N
RELAYS Product Catalog" -- also cross-linked from
`industry.panasonic.com`'s own downloads index for this series).

`ALZN1B12W` is **listed verbatim** in the manufacturer's own "Ordering
Information (Part No.)" table (1 Form C row, 12 V DC column, Class B
insulation column) -- zero derivation needed, the strongest provenance of
the two candidates.

| Parameter | Value | Source |
|---|---|---|
| Contact arrangement | 1 Form C (SPDT, NC contact available) | datasheet p.1-2 |
| Coil-to-contact clearance/creepage | **Min. 10 mm** | datasheet p.2, "FEATURES: Long insulation distance (between contact and coil)" |
| Surge withstand voltage (coil-contact) | 10,000 V | datasheet p.2 |
| Dielectric strength, contact-to-coil | 5,000 Vrms for 1 min (10 mA detection current) | datasheet p.3 |
| Standards | EN60335-1 GWT compliant; UL/C-UL and VDE certified (1 Form C: Class B or Class F insulation, both certified) | datasheet p.2, p.4 |
| Rated coil voltage | 12 V DC | ordering table, p.2 |
| Coil resistance / rated current / power | 360 ohm / 33.3 mA / 400 mW | datasheet p.3 -- **numerically identical to the existing Omron G5LE-1's own coil spec** |
| Contact rating (resistive) | 16 A 250 V AC, AgSnO2 | datasheet p.3 |
| Max switching voltage | 440 V AC (**no DC voltage rating given anywhere in this datasheet**) | datasheet p.3 |
| Min switching load (reference) | 100 mA 5 V DC | datasheet p.3 |
| Mechanical life | Min. 10^6 operations | datasheet p.3 |
| Electrical life, N.C. (1 Form C) | Min. 10 x 10^3 operations at 16 A 250 V AC | datasheet p.3 |
| Package | 12.5 (W) x 28.8 (L) x 15.7 (H) mm, THT, 8-pin | datasheet p.2, p.4 |

**Isolation verdict:** 10 mm clears both the 6.5 mm and 8.0 mm figures in
this repo's disputed range with 2.5-3.5 mm to spare -- the strongest margin
of the two candidates.

**Switching-duty gap (same class as the existing part):** this datasheet
gives **no DC contact-voltage rating at all** -- not even the ~30 V ceiling
AZ770 states explicitly. This is a genuine verification gap, not a
favorable finding: it means Panasonic's own literature does not speak to
DC switching at any voltage for this family, so the same
out-of-catalog-for-170-200V-DC situation the current G5LE-1 already carries
would need to be re-argued (RC-snubber/low-current mitigation) against this
part's own (AgSnO2, not Ag-alloy) contact material -- not independently
checked this session.

### Candidate B: American Zettler `AZ770-1C-12D`

**Source (fetched and read directly this session):**
`https://www.azettler.com/media/pdfs/relays/datasheets/AZ770.pdf`
(ZETTLER Group / American Zettler, Inc., "AZ770 SPDT SUBMINIATURE POWER
RELAY", dated 2021-04-27).

The exact string `AZ770-1C-12D` is **not** listed as a standalone catalog
row (unlike `ALZN1B12W` above) -- it is **derived from the manufacturer's
own documented ordering-code construction rules** (`AZ770-<contact
arrangement>-<coil voltage>D<plating><footprint><coil option>`, all
optional suffixes blank = standard/non-sealed/non-plated/type-1-footprint/
standard-coil), the same pattern the datasheet itself uses for its own
worked examples (`AZ770-1A-5D`, `AZ770-1C-12DSEG`, `AZ770T-1AE-24DS`,
`AZ770-1A-9DSGW`). This is the identical convention this repo's own
`modules.ato` comments already use for other parts (e.g. Omron's "add the
rated coil voltage to the model number" note), so it is a **legitimately
constructed, not fabricated, part number** -- but it is one derivation step
removed from a verbatim catalog line, and I did not check a distributor
stock page for it this session. **Flagged: confirm `AZ770-1C-12D` (or the
nearest stocked coil-voltage/option variant) against a DigiKey/Mouser
listing before committing it to a BOM.**

| Parameter | Value | Source |
|---|---|---|
| Contact arrangement | SPST (1 Form A), **SPDT (1 Form C)** | datasheet p.1 |
| Coil-to-contact creepage AND clearance | **8 mm** (both, stated together) | datasheet p.1, "FEATURES" |
| Surge voltage, coil to contact | 10,000 V (1.2 x 50 us) | datasheet p.1 |
| Dielectric strength, coil to contact | 5,000 Vrms for 1 min | datasheet p.1 |
| Standards | **"Reinforced insulation, EN 60730-1 (VDE 0631, part 1)"**; EN 60335-1 (GWT) approved version available; UL 508, IEC 61810-1; UL/CUR file E44211; VDE certificate 40006815 | datasheet p.1 |
| Nominal coil voltage | 12 V DC (standard coil) | coil voltage table, p.2 |
| Coil resistance | 320 ohm +/-10% | p.2 -- close to (not identical to) G5LE-1's 360 ohm; must-operate 9.0 V DC, max continuous 15.6 V DC |
| Contact rating, 1 Form C (VDE) | 3 A at 250 V AC resistive, 100k cycles; **3 A at 30 V DC resistive, 100k cycles** | p.1 |
| Explicit DC-voltage caveat | *"If switching voltage is greater than 30 VDC, special precautions must be taken. Please contact the factory."* | p.1, directly under the ratings table |
| Package | 17.85 (L) x 10.35 (W) x 12.95 (H) mm, THT, 5-pin ("Type 1" or "Type 2" footprint option) | datasheet p.3 |

**Isolation verdict:** 8 mm clears the 6.5 mm figure with margin and meets
the 8.0 mm figure exactly (not "close to" -- the datasheet states 8 mm as a
round figure, matching the top of this repo's disputed range and the exact
corridor width the barrier-constrained CP-SAT model used, 8.0-8.5mm).

**Switching-duty gap:** AZ770's datasheet is the more forthright of the
two -- it explicitly states a 30 V DC catalog ceiling **and** explicitly
invites a factory consultation for anything above that, which is exactly
the conversation this repo's own docstring already implicitly had with
itself for the current G5LE-1 (same 30 V DC UL/CSA ceiling, same
out-of-catalog-above-that situation). Choosing AZ770 does not create a new
problem here; it inherits the identical one, with a manufacturer contact
path already named in the datasheet for resolving it properly.

### A rejected candidate, for the record (shows the hard rule being applied)

**Omron `G5NB-1A-HA`** (the same "PCB Power Relay" family whose datasheet
was fetched and read in full this session,
`omronfs.omron.com/en_US/ecb/products/pdf/en-g5nb.pdf`) is genuinely
excellent on isolation -- "Satisfies EN61010 reinforced insulation
requirements," "IEC/EN 60335-1 conformed (-HA Model)," 6.0 mm min
creepage/clearance, 4,000 VAC dielectric coil-to-contact, 10 kV impulse --
and is explicitly marketed for "water heaters, refrigerators, air
conditioners, home appliances." **It is rejected here anyway**: every
ordering-table row for this entire family, standard and HA (home-appliance)
alike, is **Contact form: A (SPST-NO) only -- no Form B, no Form C, no NC
contact of any kind exists in this family.** `BusDischarge`'s fail-safe
behavior depends specifically on an NC contact that closes when the coil
loses power; an NO-only relay wired the opposite way (energize to
discharge) would invert the fail-safe direction into a fail-**unsafe** one
(loss of power = no active discharge, backstop bleeders only). This is
exactly the hard rule in action: **G5NB meets the isolation requirement and
fails the switching-duty/topology requirement, so it is not proposed**,
despite being a real, verifiable, on-brand part.

## Task 3 -- is a relay even the right component?

**Evaluated, not adopted, no MPN proposed for this path.** The circuit's
entire safety property -- discharge engages on ANY loss of power, with zero
MCU involvement -- depends on a mechanism that defaults to "conducting" with
**no power applied at all**. A mechanical NC contact gets this for free
(spring force). A solid-state switch (MOSFET/IGBT gate) is inherently
normally-**off**; reproducing "no power -> conducting" would require either:

1. **A depletion-mode (normally-on) HV device** (e.g. a depletion-mode SiC
   JFET), which needs an actively-maintained *negative* gate-source bias to
   stay OFF while the unit runs -- so *loss of that bias supply* (not just
   loss of mains power) would also engage discharge, which is a different
   failure-mode profile than today's design and would need its own
   single-fault analysis before being trusted as "fail-safe" in the same
   sense. I did not find, and am not proposing, any specific verified part
   number for this path this session -- it is a legitimate architecture
   question, not a drop-in substitution, and deserves its own dedicated
   investigation rather than a rushed part swap bolted onto this task.
2. **A stored-energy/capacitive gate latch**, which introduces its own new
   failure modes (leakage, aging) not present in a spring-loaded mechanical
   contact.

**A genuinely interesting, but unresolved, systemic point for a future
pass:** if a solid-state topology were adopted, the *isolation* problem
does not disappear -- it moves. The control (SELV) side of a depletion-mode
switch would still need to cross the mains<->SELV barrier via an isolated
driver (an optocoupler or isolated gate-driver IC), which converts K2/K3's
"relay coil-to-contact" isolation problem into the exact same *class* of
problem this repo's own `docs/evidence/2026-07-28-creepage-requirement-determination.md`
already found to be a **PCB land-pattern/groove problem, not a
component-selection dead end**, for `U7` (TI UCC21550) and (pending one
unverified check) `U3` (H11L1). That is a real, positive argument *for*
eventually considering solid-state -- but it is a topology change with a
new safety-analysis burden of its own, not something to fold into this
task's narrower isolation-defect fix. **Recommendation: keep the relay
architecture for this pass** (Candidate A or B above), and treat solid-state
as a separate, deliberate follow-up if the project wants to revisit the
whole discharge-path architecture.

## Task 4 -- board impact of the recommendation

Recommending **Candidate B (`AZ770-1C-12D`)** as primary (meets the range
exactly with the strongest, most explicit safety-standard language
including the words "Reinforced insulation") with **Candidate A
(`ALZN1B12W`)** as a strong alternative (larger isolation margin, verbatim
catalog part number, slightly weaker DC-rating disclosure). Either choice
has the same category of board impact:

- **Footprint:** neither candidate can reuse
  `Relay_THT:Relay_SPDT_Omron-G5LE-1`. AZ770 (Type 1 footprint):
  17.85 x 10.35 x 12.95 mm, 5-pin THT, mounting-hole pattern ~15.24 mm x
  7.62 mm (5 x 1.3mm dia holes per the datasheet's PC board layout
  drawing) -- notably *smaller* footprint than the existing part, but a
  different pin arrangement, so a new KiCad footprint must be drawn/sourced,
  not assumed compatible. LZ-N: 12.5 x 28.8 x 15.7 mm, 8-pin THT (redundant
  pins per pole, common in this class), also a new footprint needed.
- **`elec/src/components.ato` change:** the `Relay_SPDT` component
  (lines 312-332) hardcodes the Omron G5LE-1's own physical pin numbers
  (`coil1~pin2, coil2~pin5, COM~pin1, NO~pin3, NC~pin4`), verified against
  that specific part's own datasheet and KiCad symbol. **This mapping does
  not transfer** to either candidate (different physical pin numbering) --
  a new component definition (or a footprint-parameterized variant) with
  its own independently-verified pin mapping is needed before `modules.ato`
  can reference the new part. **I did not verify the exact NC/NO/coil pin
  numbers for either candidate to the same rigor** (their wiring diagrams
  are images; this session's PDF text-extraction rendered them
  ambiguously) -- flagged explicitly, not guessed at, in "What a human must
  still verify" below.
- **`elec/src/modules.ato` (`BusDischarge`) change:** `k_dis1.mpn` /
  `k_dis2.mpn` (currently `"G5LE-1 DC12"`) and `.footprint` (currently
  `"Relay_THT:Relay_SPDT_Omron-G5LE-1"`, lines 909-919) would change to the
  new part number and footprint. **No other value in the module needs to
  change**: both candidates' coil specs (12 V / ~33 mA / ~320-360 ohm) are
  close enough to the existing 100 ohm dropper's design point that the
  existing `r_coil1`/`r_coil2`/`d_fly1`/`d_fly2`/`q_dis_drv` drive circuit
  carries over unmodified, and the discharge current (~21.8 mA) and contact
  voltage (~170-200 V) driving the resistor-string/snubber sizing are
  circuit properties independent of which relay switches them.
- **Placement implication (a genuinely positive consequence worth
  flagging for whoever re-runs the CP-SAT barrier model next):** the
  barrier-constrained-placement analysis
  (`docs/evidence/2026-07-28-barrier-constrained-placement.md`) found K2/K3
  **unconditionally infeasible** for an 8.0-8.5 mm isolation corridor on
  *any* axis/rotation, even at a deliberately-relaxed 1.0 mm test corridor
  -- a hard, width-independent fact of the *current* part's pinout (COM and
  a coil pin ~2mm apart in both axes). Either candidate's real
  coil-to-contact separation (10 mm / 8 mm) would move K2/K3 out of that
  "no board feature can ever fix this" bucket into the *same marginal
  category* as `U7`/`U3`/`T1` -- parts whose own geometry is at or near the
  8mm figure, where the prior analysis found the board-level conservative
  bounding-circle pad model (not the part itself) was the binding
  constraint. **This does not by itself prove a compliant placement now
  exists** -- the CP-SAT model would need to be re-run with the new
  footprints to confirm -- but it is a materially different, more hopeful
  starting point than today's "genuinely infeasible" verdict, and is worth
  surfacing for that follow-up rather than left implicit.

### What a human must still verify before this reaches the BOM

1. **Exact NC/NO/coil pin numbers** for whichever candidate is chosen,
   against the manufacturer's own wiring-diagram drawing (not the
   text-extracted approximation in this pass) -- required before writing a
   new `Relay_SPDT`-equivalent component definition.
2. **A real KiCad footprint** matching the candidate's actual land pattern
   -- not checked against this project's footprint library this session.
3. **DC contact-voltage rating at the circuit's actual 170-200V duty**,
   ideally via the manufacturer contact path AZ770's own datasheet names
   ("please contact the factory") -- ports the existing G5LE-1 gap forward,
   does not resolve it.
4. **Distributor stock/lead-time check** for `AZ770-1C-12D` specifically
   (derived, not catalog-verbatim) or `ALZN1B12W` (catalog-verbatim, likely
   the safer sourcing bet).
5. **Re-run the barrier-constrained CP-SAT placement model** with updated
   K2/K3 footprints once real footprints exist, to see whether the
   isolation barrier becomes achievable in practice (not just in principle).

## Falsifier verdict

> "A drop-in or near-drop-in relay exists with adequate coil<->contact
> isolation for this switching duty. If every candidate forces a package or
> topology change, that is the finding -- report the trade-off rather than
> proposing a part that does not meet the electrical requirement."

**Partly falsified, partly holds -- reported precisely, not rounded to a
clean yes/no:**

- **On isolation:** FALSIFIED in the strong sense. Real, manufacturer-
  verified parts exist (`ALZN1B12W`, `AZ770-1C-12D`) whose own datasheets
  state 8-10 mm coil-to-contact creepage/clearance with explicit
  reinforced-insulation/IEC 60335-family language -- comfortably clearing
  both ends of this repo's disputed 6.5-8.0 mm range. This is not a
  "no solution exists" outcome.
- **On topology:** the falsifier's stronger framing ("drop-in") does not
  hold, and this is reported plainly rather than glossed over: both
  candidates force a **package/footprint change** and a
  **`components.ato` pin-mapping change**. Neither is a zero-touch
  substitution.
- **On switching duty specifically:** neither candidate is WORSE than the
  status quo. The 170-200 V DC contact-breaking gap already existed for
  the current G5LE-1 (already documented in this repo's own module
  docstring, already mitigated the same way -- RC snubber, low break
  current relative to arc-sustain threshold) and is inherited unchanged,
  not newly introduced, by either candidate.
- **Net finding:** this is a "same-topology, new-footprint, same-role"
  swap -- meaningfully smaller than the solid-state alternative considered
  in Task 3, but not the zero-effort drop-in the falsifier's literal wording
  asks about. Reported as exactly that, per the task's own instruction not
  to propose a part that doesn't meet the real requirement just to get a
  clean "solved" answer.

## UNVERIFIED (explicit list, per the task's honesty requirement)

- Exact NC/NO/coil pin-number mapping for `ALZN1B12W` and `AZ770-1C-12D`
  against their own manufacturer wiring diagrams -- this session's PDF
  text-extraction rendered the diagrams ambiguously; a fresh, higher-
  fidelity read (or the actual CAD/footprint file) is needed before either
  number is written into `components.ato`.
- Neither datasheet gives an explicit, manufacturer-warranted DC contact
  rating at 170-200 V. AZ770 states 30 V DC catalog / "contact factory"
  above that; LZ-N gives no DC voltage rating at all. This is a carried-
  forward, not-worsened gap shared with the existing G5LE-1 (itself already
  flagged the same way in this repo's own `modules.ato` comments) -- not
  resolved by this pass.
- Whether AgSnO2 contact material (both candidates) has an arc-sustain-
  current threshold comparable to the G5LE-1's plain Ag-alloy contacts (the
  number the existing 21.8mA-vs-~0.4A margin argument depends on) -- not
  independently checked this session.
- Whether a compliant mains<->SELV barrier placement actually becomes
  achievable once K2/K3's footprints are updated -- the barrier-constrained
  CP-SAT model was not re-run with new footprints in this pass (would
  require drawing/sourcing real footprints first, out of scope for a
  research/reporting pass per this project's own precedent).
- Whether ready-made KiCad footprints for either candidate's land pattern
  already exist in this project's footprint libraries -- not checked.
- `AZ770-1C-12D`'s exact string does not appear verbatim in a catalog table
  or a distributor listing fetched this session -- it is derived from the
  manufacturer's own documented ordering-code construction rules (the same
  convention this repo's own comments already use elsewhere), one step
  short of `ALZN1B12W`'s verbatim-catalog-row provenance. Flagged plainly,
  not smoothed over.
- Expected operations-over-life for K2/K3: no explicit repo specification
  found; the thousands-of-operations estimate in Task 1 is DERIVED/ASSUMED
  from the module's own described trigger condition (power-loss events),
  not independently sourced.
- The 6.5mm-vs-8.0mm creepage reconciliation itself remains open per the
  task's own framing -- this doc is intentionally insensitive to that
  question (both candidates clear both figures), so it does not need to be
  resolved here, but it is not resolved BY this doc either.
- IEC 60335-1/60664-1 primary-text clause numbers for the underlying
  creepage/clearance requirement were not independently re-derived in this
  pass -- same UNVERIFIED-at-primary status already carried by every prior
  evidence doc in this chain; this task relied on the already-established
  6.5-8.0mm range rather than re-deriving it.

## Hard rules -- compliance checklist

- Every proposed part number verified via a directly-fetched manufacturer
  PDF datasheet, quoted with its exact source URL above -- no MPN proposed
  without that verification. `G5NB-1A-HA` was fetched and read in full and
  explicitly rejected (topology mismatch), not silently omitted.
- No `git stash` used anywhere in this session.
- No `run_in_background`; no `Monitor` wait. `mcp__claude-in-chrome` was
  attempted (browser extension not connected in this environment, confirmed
  via `tabs_context_mcp`) and abandoned in favor of direct `WebFetch`/PDF
  reads -- not retried in a loop.
- `uv run --no-sync` used throughout; `uv sync --all-packages` run exactly
  once, at the start, into this worktree's own venv.
- `elec/build/` not committed (gitignored; `make netlist` was run to unblock
  the manifest-dependent gates, output not added to git -- confirmed via
  `git status --short`, clean).
- No BOM, `elec/src/modules.ato`, `elec/src/components.ato`,
  `elec/domain_manifest.yaml`, or `pcb/temper.kicad_pcb` edit made this
  pass -- verified (`git status --short` empty throughout, checked
  immediately before writing this doc).
- `scripts/mpn_fabrication_gate.py` run against the (unchanged) repo state:
  PASSED, 0 new violations -- there is nothing new to check since no BOM
  file was touched, but the gate was run anyway per the task's instruction.

## Verification (all commands actually run this session; output shown or summarized above)

| Check | Result |
|---|---|
| `make netlist` | passes (build complete) |
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 (0 new violations; 10 pre-existing allowlist entries, unchanged) |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | exit 0 (2482 copper items, 510/519 pads exact-matched -- unchanged from baseline, confirms `pcb/temper.kicad_pcb` untouched) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (9/10 fresh, `temper-constraints` missing in lenient local-dev mode -- matches every prior session's baseline) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 (4/4 checks agree) |
| `check_isolation_keepout.py` | **exit 3**, unchanged from base commit (no keepout zone exists; this task did not add one) |
| `check_measurement_provenance.py` | **exit 5**, unchanged from base commit (pre-existing `drc_ceiling.json` provenance-tag defect, not touched by this task) |
| `uv run --no-sync python -m pytest elec/validation -q` | 30 passed |

All ten required gates exit 0; the two expected-exception gates exit exactly
3 and 5 as anticipated; `make netlist` and the validation test suite both
pass -- identical baseline to every prior evidence doc in this chain,
confirming this pass introduced zero drift.
