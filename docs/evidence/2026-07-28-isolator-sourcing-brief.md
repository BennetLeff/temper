<!-- provenance: commit=320e3c816fe3212ded0e934a6fa6098c121bf170 dirty=false -->

# Sourcing brief: the 5 remaining mains<->SELV barrier blockers (C6, K2, K3, U3, U7)

Branch `docs/isolator-sourcing-brief`, from `origin/main` at `320e3c81`
("Merge pull request #388 from BennetLeff/fix/pad-geometry-model"). Every
measurement below was produced by running the code shown against
`pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml` at that commit, on a
clean tree, using the **corrected** pad model
(`packages/temper-placer/src/temper_placer/core/pad_geometry.py`, PR #388).
No pre-#388 figure is carried over.

**This document changes nothing.** `elec/src/*.ato`, `docs/hardware/BOM.md`,
`pcb/temper.kicad_pcb` and `mpn-fabrication-allowlist.yaml` are untouched.
The purchasing decision is the user's.

---

## Summary (read this first)

**Headline: 5 of 5 blockers have a verified path to >=8.0mm. Only 2 of the 5
(K2, K3) actually need a different device.**

| Ref | Needs a new device? | Verified candidate / fix | Resulting gap |
|---|---|---|---:|
| C6 | **No** (footprint) + yes, MPN must change (declared part unverifiable, its real counterpart obsolete) | `VY1222M47Y5UQ6TV0` (Vishay VY1, X1/Y1, 10.0mm lead spacing, **Active, 365 in stock DigiKey**) on a 10.00mm-pitch land | **8.0-8.6mm** (pad-diameter dependent) |
| K2 | **Yes** -- G5LE-1's pinout is unfixable | `RT314012` (TE Schrack RT1, 1 form C, 12VDC, **Active, 7442 in stock DigiKey**, datasheet: coil-contact >=10/10mm clearance/creepage, reinforced insulation) | **12.760mm** |
| K3 | **Yes** -- identical part, identical problem | same as K2 | **12.760mm** |
| U3 | **No new device** -- same die, same pinout, wide-lead-form orderable variant | `H11L1TVM` (onsemi H11L1, `TV` = VDE 0884 + 0.4" lead spacing, **Active, 1701 in stock DigiKey**) on `Package_DIP:DIP-6_W10.16mm` | **8.560mm** |
| U7 | **No** -- pure land-pattern change to TI's *own* published HV option (MPN must still be corrected -- the declared one is not orderable) | `UCC21550BDWKR` (TI, Active/Production) on the datasheet's "HV / ISOLATION OPTION" land pattern | **8.100mm** |

**"No verified candidate found": zero.** Every slot is filled with a part
number read off a manufacturer datasheet or a distributor product page, with
the specific figure quoted below.

Three of the four fixes clear the CP-SAT module's more conservative 8.5mm
working margin as well; **U7's 8.100mm and C6's 8.0-8.4mm (at stock pad
diameters) clear the 8.0mm gate but not 8.5mm** -- see "Margin" below.

Three incidental defects were found while doing this and are reported at the
end, because each is the same defect class the fabricated-MPN audit exists
for: C6's declared MPN does not appear to exist, U7's declared MPN is not a
TI orderable part number, and U7's declared pin list contradicts its own
footprint.

---

## Method

Re-measurement uses the repo's own code, not a re-derivation: the *same*
`compute_pad_groups` / `evaluate_isolator_feasibility` /
`temper_placer.core.pad_geometry` path that `check_isolation_keepout.py` and
the CP-SAT barrier constraint use, so "this brief says 8.56mm" and "the gate
measures 8.56mm" cannot disagree about geometry.

Candidate land patterns were measured with the same `pad_axis_radius`
support-function model, against the *stock KiCad 9 footprint libraries
installed on this machine*
(`/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`) -- i.e.
real, checkable land patterns, not invented ones.

Two thresholds are reported throughout:

- **8.0mm** -- `scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM`
  (line 173), the actual gate.
- **8.5mm** -- `isolation_barrier.py`'s working corridor width, 0.5mm of
  deliberate headroom above the gate. A part that clears 8.0 but not 8.5
  passes the safety gate but leaves the CP-SAT solve with zero margin.

Reproduction (both parts, one script):

```
uv run --no-sync python - <<'EOF'
from pathlib import Path
from temper_placer.core.pad_geometry import pad_axis_radius
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import (
    compute_pad_groups, evaluate_isolator_feasibility, load_domain_manifest_nets)
REPO = Path(".")
hv, selv = load_domain_manifest_nets(REPO / "elec/domain_manifest.yaml")
nl = parse_kicad_pcb(REPO / "pcb/temper.kicad_pcb").netlist
by_ref = {c.ref: c for c in nl.components}
for ref in ("C6", "K2", "K3", "U3", "U7"):
    g = compute_pad_groups(by_ref[ref], hv, selv)
    f = evaluate_isolator_feasibility(g, corridor_width_mm=8.0)
    print(ref, by_ref[ref].footprint, f.gap_x_mm, f.gap_y_mm, f.achievable_gap_mm, f.feasible)

def rowgap(span, pad_len, pad_w, shape, rr=0.25):   # two opposing pad rows
    return span - 2 * pad_axis_radius(pad_len, pad_w, shape, 0, 0.0, rr)
print("C6  P10.00mm/2.0mm pads ", rowgap(10.00, 2.0, 2.0, "circle"))
print("U3  DIP-6_W10.16mm      ", rowgap(10.16, 1.6, 1.6, "circle"))
print("U7  TI HV/ISOLATION land", rowgap(9.75, 1.65, 0.6, "roundrect"))
EOF
```

---

## Re-measured table (corrected model, this commit)

`gap_x` / `gap_y` are the worst-case edge-to-edge separations between the
component's own HV-net pad cluster and its SELV-net pad cluster, along each
local axis; `achievable` is the best of the two (i.e. the best any rotation
can do). Negative means the clusters overlap on that axis.

| Ref | Part as declared in `elec/src` | Footprint on the board | gap_x (mm) | gap_y (mm) | **achievable (mm)** | Shortfall vs 8.0 | Pass @8.0 | Pass @8.5 |
|---|---|---|---:|---:|---:|---:|:--:|:--:|
| C6 | Murata `DE1E3KX222MA4BA01`, 2.2nF Y1 250VAC | `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` (a local **stub**, `descr`: "Created to resolve netlist reference") | 3.200 | -1.800 | **3.200** | **-4.800** | NO | NO |
| K2 | Omron `G5LE-1 DC12`, SPDT | `Relay_THT:Relay_SPDT_Omron-G5LE-1` | -2.500 | -0.500 | **-0.500** | **-8.500** | NO | NO |
| K3 | Omron `G5LE-1 DC12`, SPDT | `Relay_THT:Relay_SPDT_Omron-G5LE-1` | -2.500 | -0.500 | **-0.500** | **-8.500** | NO | NO |
| U3 | `H11L1` (Everlight/onsemi/Vishay, family part) | `Package_DIP:DIP-6_W7.62mm` | 6.020 | -1.600 | **6.020** | **-1.980** | NO | NO |
| U7 | TI `UCC21550BDW` (see defect #2) | `lib:SOIC16W_Isolated` (KiCad `SOIC-16W_7.5x10.3mm_P1.27mm` with pads 12/13 deleted) | 7.250 | -0.600 | **7.250** | **-0.750** | NO | NO |

For contrast, the two that came off the list in #388 re-measure at
T1 = 9.100mm and K1 = 8.000mm on this same run -- unchanged, so this
measurement path reproduces #388 exactly.

### The binding pad pair, per part (why it is too small)

Measured directly off the board, not inferred:

| Ref | Binding HV pad | Binding SELV pad | Centre-to-centre | Root cause |
|---|---|---|---:|---|
| C6 | pad 1, `PWR_RTN`, 1.8mm round | pad 2, `gnd`, 1.8mm round | 5.000mm | **Lead pitch.** A 5.00mm-pitch land. 5.00 - 0.9 - 0.9 = 3.20mm. |
| K2 | pad 1 `PWR_RTN` (COM), 2.5x2.5 rect | pad 2 `discharge.k_dis1-coil1`, 2.5x2.5 oval | 6.325mm | **Pinout arrangement.** The G5LE-1's COM terminal sits at (0.0, -7.1) and a coil terminal at (-6.0, -5.1): 2.0mm apart in Y and 6.0mm in X, i.e. the pole pin is *between* the coil pins in one axis and level with them in the other. No rotation helps. |
| K3 | pad 1 `DC_BUS_RTN` (COM) | pad 2 `discharge.k_dis2-coil1` | 6.325mm | identical part, identical geometry |
| U3 | pad 1, LED anode `a`, 1.6mm | pad 4, `ZCD_ISO`, 1.6mm | 7.620mm | **Row spacing.** 300-mil DIP: 7.62 - 0.8 - 0.8 = 6.02mm. |
| U7 | pad 9, `DC_BUS_RTN`, 2.05x0.6 | pad 3, `+3V3`, 2.05x0.6 | 9.300mm centres | **Land pattern, not the package.** Pads are 2.05mm long on a 9.30mm centre span, so they reach 0.69mm *inboard of the lead heel* on both sides: 9.30 - 1.025 - 1.025 = 7.25mm. |

Note the shape of these causes: **C6 and U7 are land-pattern problems, U3 is
a lead-form problem, and only K2/K3 are genuine device problems.**

---

## C6 -- Y-capacitor, mains-derived return to protective earth

### Is it "not sourced yet"? Partly -- and the part of it that *is* sourced does not hold up.

The brief's premise ("this part isn't even sourced yet") is **half true, and
the true half is the less serious half**:

- **It IS sourced in the source of truth.** `elec/src/modules.ato:744-749`
  declares `y_cap_pe` with `mpn = "DE1E3KX222MA4BA01"`, `value = 2.2nF +/- 20%`,
  `dielectric = "Y1"`, `voltage_rating = 250V`.
- **The footprint is a stub.** `pcb/temper.kicad_pcb:205` / `:3398`, `descr`:
  *"Stub for safety capacitor (Y2 type). D=10.0mm disc, W=5.0mm, P=5.0mm
  pitch. Created to resolve netlist reference."* It also says **Y2** while the
  `.ato` requires **Y1** -- two different safety classes.
- **The declared MPN does not survive checking** (defect #1 below), and the
  real Murata part it is nearly-spelling is **obsolete**.

So this is *not* purely a specification task: the footprint is wrong, the
MPN is wrong, and a replacement part does have to be chosen. But the
*geometry* was never the part's fault.

### The decisive fact: the declared part already has a 10.0mm lead pitch

Murata's own current DE1/Type-KX datasheet (fetched, read; see Sources)
lists, in its part-number table:

```
DE1E3KX222MA4BN01F   T.C. E   2200pF  +/-20%   D=9.0  T=7.0  F=10.0  d=0.6   Lead Style A4
```

`F` is lead spacing: **10.0mm**. The board is standing a 10.0mm-lead-spacing
Y1 disc on a **5.00mm-pitch** land. That alone is a build defect independent
of the isolation barrier.

### Electrical requirements a replacement must still meet

From `modules.ato:740-752` and `main.ato:449-471`: 2.2nF +/-20%, **Y1** class
(not Y2), >=250VAC r.m.s. line-to-ground, through-hole, PE bond from the
doubler midpoint (`dc_bus.gnd_ref`, a mains-derived node) to protective
earth in a Class I appliance under IEC 60335-1. Y1 is the class that
corresponds to reinforced/double insulation for a line-to-earth bridge --
it is the whole reason this part exists, so a Y2 substitute is not
acceptable regardless of what the stub footprint's `descr` says.

### Geometric requirement

With round through-hole pads of diameter `d_pad` on a pitch `P`, the gate
measures `P - d_pad`. So `P >= 8.0 + d_pad`. Measured options:

| Land pattern | Pad dia | Gap | @8.0 | @8.5 |
|---|---:|---:|:--:|:--:|
| current stub, P=5.00mm | 1.8mm | 3.200mm | NO | NO |
| KiCad `C_Disc_D12.5mm_W5.0mm_P10.00mm` (stock) | 2.0mm | **8.000mm** | YES (exactly) | NO |
| P=10.00mm, 1.6mm pads (0.9mm drill on a 0.6mm lead) | 1.6mm | **8.400mm** | YES | NO |
| P=10.00mm, 1.4mm pads (0.8mm drill) | 1.4mm | **8.600mm** | YES | **YES** |

The stock KiCad 10mm-pitch disc footprints use 2.0mm pads and land *exactly*
on 8.000mm -- zero margin, the same knife-edge K1 sits on. A 1.4-1.6mm pad
is entirely reasonable for a 0.6mm lead and buys the margin back. **This is
a footprint decision, and it is the cheapest of the five fixes.**

### Verified candidate

**`VY1222M47Y5UQ6TV0`** -- Vishay BCcomponents VY1 series.

| Spec | Value | Source |
|---|---|---|
| Capacitance | 2200 pF +/-20% | DigiKey product page 2824499 (read) |
| Class | **X1, Y1** | DigiKey page; Vishay VY1 datasheet 28537 ("Class X1, 760 VAC, Class Y1, 500 VAC") |
| Voltage | 760VAC (X1) / 500VAC (Y1) | as above -- **exceeds** the 250VAC requirement |
| **Lead spacing** | **0.394" (10.00mm)** | DigiKey page; datasheet 28537 p.2 table ("F (mm) +/-1mm: 10.0 or 12.5") |
| Body diameter | 12.0mm max | datasheet 28537 p.2 (2200pF Y5U row: Dmax 12.0, Tmax 5.0) |
| Status / stock | **Active**, 365 in stock (cut tape) + incoming | DigiKey page, fetched 2026-07-28 |
| Lead style | formed/kinked inline, tape-and-reel (`TV` = tape + inline kinked; `0` = 10.0mm) | datasheet 28537 ordering-code table |

Fits `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` (12.0mm body <= 12.5mm),
or a 1.4-1.6mm-pad variant of it for margin.

The VY1 ordering code is documented in the datasheet (digits 15-17 =
packaging / lead style / lead spacing), so bulk and straight-lead variants
of the same capacitor exist -- **but I have not verified any specific
alternate code at a distributor, and per this repo's own rules I will not
write one down.** Order the code above, or ask the distributor for the bulk
equivalent by description.

### Alternative, if you want to stay with Murata

`DE1E3KX222MA4BN01F` is the real spelling of what the `.ato` was probably
reaching for (2200pF, X1/Y1, 250VAC, F=10.0mm -- Murata's own datasheet, and
DigiKey confirms "Lead Spacing 0.394" (10.00mm)"). **DigiKey lists it as
Obsolete, "no longer manufactured", 0 in stock.** Its listed successor
`DE1E3RA222MA4BN01F` is *also* reported obsolete (TME/search; I did not
reach a first-party Murata lifecycle page for it). Do not design it in.

---

## K2 / K3 -- bus-discharge relays

### Why this one genuinely needs a different device

The Omron G5LE-1's five terminals are laid out (footprint frame, mm):

```
pad 1  COM   ( 0.0, -7.1)   <- HV      pad 2  coil (-6.0, -5.1)  <- SELV
pad 3  NO    (-6.0,  7.1)               pad 5  coil ( 6.0, -5.1)  <- SELV
pad 4  NC    ( 6.0,  7.1)   <- HV
```

The pole terminal is 2.0mm from a coil terminal in Y and level with the
other coil terminal in X. Both axes are negative. **No land pattern, no pad
shrink, and no rotation can produce 8mm from that arrangement** -- the
copper has to be where the pins are. The `1.0mm` control run in
`2026-07-28-barrier-constrained-placement.md` already showed K2/K3 fail even
at a 1mm corridor; that is still true on the corrected model.

Note this is a *terminal-layout* fact, not an insulation-quality fact: the
G5LE's own coil-contact insulation (per `modules.ato:906-908`: 2000VAC
dielectric, 4.5kV impulse) is not what fails. What fails is that the part
was never designed to have its coil and its contacts on opposite sides of a
PCB barrier.

### Electrical requirements a replacement must still meet

Read out of `modules.ato:837-1092` (the `BusDischarge` module and its
docstring):

| Requirement | Value | Why |
|---|---|---|
| Contact form | **SPDT / 1 form C, with an accessible NC contact** | The whole design is fail-safe: coils energized = NC open = discharge disengaged. Loss of power closes NC. A form-A relay cannot do this (that is exactly why the G5LE-1 was chosen over the G4A-1A-E bypass relay). |
| Coil | 12VDC nominal, fed from the 15V SELV rail through a **100R** dropper (`r_coil1`/`r_coil2`, `RC1206FR-07100RL`) | With a 360R coil this gives ~32.6mA and ~11.7V at the coil. A different coil resistance **changes both** and the dropper must be resized. |
| Coil must-operate | <= ~11.7V | see above |
| Contact duty | break ~21.8mA at up to **170VDC**, purely resistive, with an RC snubber (100R 2W + 470nF/630V PP) across each NC-COM gap | `modules.ato:875-890` |
| Contacts nominal | 10A / 250VAC declared | vastly over-specified for a 22mA load; not a binding constraint |
| Coil budget | 2 x ~33mA from the 15V rail while running | `modules.ato:894` |

**The 170VDC break is already out-of-catalog on the G5LE-1** and the design
knows it (`modules.ato:875-880`: "max switching voltage is 125VDC ... a
170VDC break is out-of-catalog at ANY current"). It is mitigated by the
snubber, not by the relay. **A replacement does not fix this** -- see the
honest caveat below. Do not treat the swap as resolving that separate open
item.

### Requirement class for a candidate

*A PCB power relay whose coil terminals and contact terminals are at
opposite ends of the package (not interleaved), with a manufacturer-stated
coil-to-contact clearance/creepage of at least 8mm and a reinforced-insulation
claim, in 1 form C, with a 12VDC coil close to 360R.*

The "opposite ends" part is the operative one and it is checkable per
footprint. Measured against stock KiCad land patterns with the same model:

| Candidate footprint | gap_x | gap_y | best | @8.0 | @8.5 |
|---|---:|---:|---:|:--:|:--:|
| `Relay_SPDT_Omron-G5LE-1` (current) | -2.500 | -0.500 | **-0.500** | NO | NO |
| `Relay_SPDT_Schrack-RT1-FormC_RM3.5mm` | 13.820 | -3.000 | **13.820** | YES | YES |
| `Relay_SPDT_Schrack-RT1-FormC_RM5mm` | 12.760 | -2.500 | **12.760** | YES | YES |
| `Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm` | 12.760 | -2.500 | **12.760** | YES | YES |

Also checked and **rejected**: `Relay_SPDT_Finder_36.11` -- its COM pin sits
between the coil pins in the same way the G5LE-1's does (3.55mm best axis).
Being a different manufacturer is not the property that matters; terminal
topology is.

### Verified candidate

**`RT314012`** -- TE Connectivity / Schrack "Power PCB Relay RT1".

| Spec | Value | Source |
|---|---|---|
| Contact arrangement | 1 form C (CO) | TE RT1 datasheet, "PRODUCT INFORMATION" table, RT314012 row |
| **Coil-contact clearance/creepage** | **>=10 / 10 mm** | TE RT1 datasheet, "INSULATION DATA" |
| Coil-contact dielectric strength | 5000 Vrms | same table |
| Insulation class | **"5kV/10mm coil-contact, reinforced insulation"** | RT1 datasheet, FEATURES, line 1 of the doc |
| Standards | "Product in accordance to IEC 60335-1" | RT1 datasheet, FEATURES -- *the same standard this design's 8.0mm figure is drawn from* |
| Coil (012 code) | rated 12VDC, **operate 8.4V**, release 1.2V, **360R +/-10%**, 400mW | RT1 datasheet, "COIL VERSIONS, DC COIL" |
| Contact rating | 16A / 250VAC, max switching voltage 400VAC | RT1 datasheet, "CONTACT DATA" |
| Status / stock | **Active, 7,442 in stock at DigiKey** (14-week factory lead time) | DigiKey product page 1128622, fetched 2026-07-28 |
| TE part number | 9-1393239-5 (Austria) / 1-1649328-3 (China) | RT1 datasheet product-information table |

**The coil is a drop-in for the existing dropper**: 360R / 400mW is
*identical* to the G5LE-1's declared coil (`modules.ato:907`), so
`r_coil1`/`r_coil2` (100R) keep delivering ~11.7V, comfortably above the
RT1's 8.4V must-operate. That is the single biggest reason to prefer this
family over any relay with a "sensitive" coil.

Same-family alternatives, same insulation data, different pin pitch /
contact rating: **`RT114012`** (12A, 3.5mm pinning, footprint
`Relay_SPDT_Schrack-RT1-FormC_RM3.5mm`, 13.820mm) and **`RT214012`** (12A,
5mm pinning). Both appear in the same datasheet's product table with TE part
numbers; **I did not confirm their stock at a distributor**, so `RT314012`
is the one I am putting my name on.

### Board-area cost (measured, not guessed)

From the KiCad courtyards: G5LE-1 is 17.0 x 23.0mm = **391 mm^2**;
RT1-16A-FormC_RM5mm is 29.9 x 13.6mm = **407 mm^2**. That is +4% area per
relay, but a very different aspect ratio -- long and thin, with coil at one
end -- which is exactly the shape a barrier-constrained placement wants.
Two relays, so ~32 mm^2 net. This is not a packing risk on a 152 x 234mm
board.

### Honest caveats

1. **The 170VDC DC break is NOT fixed by this swap.** RT1's contact data
   gives max switching voltage as 400*VAC*; its DC capability is published
   only as a "MAX. DC LOAD BREAKING CAPACITY" *graph* (an image; not
   machine-extractable from the PDF) and an EN60947-5-1 rating of
   "2A, 24VDC, DC13". 170VDC is very likely out-of-catalog here too. The
   existing snubber argument (`modules.ato:880-890`) carries over unchanged
   and unimproved. **Flagged as unresolved, not as fixed.**
2. **DigiKey's parametric "Coil Current: 14.2 mA" for RT314012 contradicts
   its own listed "Coil resistance: 360 ohms"** (12V/360R = 33.3mA). The
   datasheet says 360R / 400mW. If the delivered part is not 360R, the 100R
   dropper must be resized. Resolve at procurement; do not assume.
3. The RT1 is a 12A/16A relay switching 22mA. Contact material is AgNi
   90/10. Low-current switching on a large silver contact is a known
   reliability topic (insufficient wetting current); the design's existing
   snubber + the fact that this is a fault-mode-only path make it
   acceptable in my read, but I did not analyse it and it is not a
   regression relative to the G5LE-1, which has the same issue.

---

## U3 -- zero-cross-detect optocoupler

### Replacement is not needed. A lead-form variant of the *same part* fixes it.

`H11L1` in a 300-mil DIP-6 gives 7.62 - 0.8 - 0.8 = 6.02mm. The
H11LxM-family datasheet's own ordering table (Fairchild/onsemi, read
directly) defines lead-form suffixes:

```
Option/Order Entry Identifier      Description
  S      Surface Mount Lead Bend
  SR2    Surface Mount; Tape and reel
  T      0.4" Lead Spacing
  V      VDE 0884
  TV     VDE 0884, 0.4" Lead Spacing
  SV     VDE 0884, Surface Mount
  SR2V   VDE 0884, Surface Mount, Tape & Reel
```

and its package drawing gives the wide form's lead span as
**0.400 (10.16) / 0.425 (10.80)** inches (mm). So a 400-mil part exists in
this exact family, with the exact same die and the exact same pinout.

On `Package_DIP:DIP-6_W10.16mm` (stock KiCad, 1.6mm pads at 10.16mm row
spacing): **10.16 - 0.8 - 0.8 = 8.560mm** -- clears both 8.0 and 8.5.

Note the SMD ("S") lead form is the **wrong** direction for this problem:
gullwing pads extend *inboard* under the body, which would shrink the gap,
not grow it. It has to be the through-hole `T` form.

### Electrical requirements a replacement must still meet

From `components.ato:470-509` and `modules.ato:787-835`: 6-pin DIP,
pin 1 = LED anode, 2 = cathode, 3 = NC, 4 = Vo, 5 = GND, 6 = Vcc;
Schmitt-trigger, **open-collector** output (external 10k pull-up to +3V3);
Vcc range must include 3.3V; LED drive is ~5.0mA from a 3.3V-clamped node
through 430R, so the turn-on threshold must be <= ~1.6mA (the "L1" grade of
the L1/L2/L3 family is specifically the 1.6mA one); output must sink the
pull-up current.

### Verified candidate

**`H11L1TVM`** -- onsemi.

| Spec | Value | Source |
|---|---|---|
| Package | **6-DIP (0.400", 10.16mm)** | DigiKey product page 401266 (read) |
| Lead spacing | 0.400" (10.16mm) | DigiKey page; H11LxM datasheet package drawing |
| Isolation voltage | 4170 Vrms (DigiKey); datasheet gives V_ISO = 7500 V_PEAK, t = 1s | DigiKey page; H11LxM datasheet "Isolation Characteristics" |
| Approvals | UL file #E90700 vol. 2; **VDE recognized file #102497 with the `V` option** (`TV` includes it) | H11LxM datasheet, Features |
| Output | Open collector, sinks 16mA at 0.4V max | H11LxM datasheet, Features |
| Supply | 3V - 15V | DigiKey page |
| Pinout | 1=Anode, 2=Cathode, 3=NC, 4=Vo, 5=GND, 6=Vcc | H11LxM datasheet, "Schematic" -- identical to the `.ato` |
| Status / stock | **Active**, 1,701 in stock + 6,000 factory stock at DigiKey | DigiKey page, fetched 2026-07-28 |
| Grade | L1 (the <=1.6mA threshold grade) | family part number |

This is the same device the design already specifies, in the lead form that
was always required for a mains barrier. The `.ato` currently declares
`mpn = "H11L1"` -- a *family* string, not an orderable part number, with an
explicit "Confirm the exact manufacturer and orderable suffix ... at
procurement; not done here" note. This brief is that confirmation.

### Caveat (important, and not resolved here)

Moving the *pads* 10.16mm apart satisfies the board-level keepout gate. It
does **not** by itself establish that the H11L1 is certified for
**reinforced** insulation at this working voltage: the H11LxM datasheet
publishes V_ISO and the VDE file number but **no creepage/clearance figure
for the package**, and I did not read the VDE 0884 certificate itself. The
package body is ~6.1-6.6mm wide, so external creepage over the body surface
is materially less than 10.16mm. If a reinforced-insulation *certificate*
(not just a withstand-voltage number) is required for this crossing, that
question is still open and a stretched-SO / high-creepage optocoupler family
would need to be evaluated instead. **Flagged, not resolved.**

---

## U7 -- isolated gate driver

### Replacement is not needed at all. TI publishes the land pattern that fixes this.

The board's `lib:SOIC16W_Isolated` footprint is (per its own `descr`, and
verified: pad size and positions are byte-identical) KiCad's
`Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` with pads 12 and 13 deleted --
pads 2.05 x 0.6mm on a 9.30mm centre span, giving 7.250mm.

TI's UCC21550 datasheet (SLUSE89C, Aug 2024) publishes **two** land patterns
for both DW0016B and DWK0014A, side by side on the same drawing:

```
   16X (2)      ...  (9.3)        16X (1.65)   ...  (9.75)
   IPC-7351 NOMINAL                HV / ISOLATION OPTION
7.3 mm CLEARANCE/CREEPAGE      8.1 mm CLEARANCE/CREEPAGE
```

The board is on the first one. Measured with the repo's model:

| Land pattern | Pad | Centre span | Gap | @8.0 | @8.5 |
|---|---|---:|---:|:--:|:--:|
| current (TI "IPC-7351 NOMINAL") | 2.05 x 0.6 | 9.30mm | **7.250mm** | NO | NO |
| TI **"HV / ISOLATION OPTION"** | 1.65 x 0.6 | 9.75mm | **8.100mm** | **YES** | NO |

(7.250 vs TI's stated 7.3 because the KiCad pad is 2.05mm, not TI's 2.00mm.)

TI says this explicitly, in footnote (1) to the Insulation Specifications
table:

> "Care should be taken to maintain the creepage and clearance distance of
> a board design to ensure that the mounting pads of the isolator on the
> printed-circuit board do not reduce this distance."

That is precisely the defect: the part's own external clearance and creepage
are both **>8 mm** (datasheet section 5.6, CLR and CPG), and the land
pattern throws 0.85mm of it away.

### Electrical requirements (unchanged -- same part)

`components.ato:27-45`: reinforced isolation, V_ISO 5000 Vrms; 4A source /
6A sink; VCCI 3.0-5.5V control side; VDDA/VDDB up to 25V (design drives from
+15V_LS); dual channel with programmable dead time and DIS. Datasheet
section 5.6 additionally gives: CLR >8mm, CPG >8mm, CTI >600V (material
group I), V_IOWM 1500 Vrms, V_IOSM 10000 V_PK, UL1577 V_ISO 5000 Vrms,
pollution degree 2. The **"B" grade must be preserved** -- A/B/C differ in
recommended minimum VDD (6.5 / 9.2 / 13.5V) and the design runs a 15V
secondary rail.

### Verified candidate (part number correction, not a device change)

**`UCC21550BDWKR`** -- TI, **Active / Production**, SOIC (DWK) | 14 pins,
2000/reel, -40 to 150C, part marking `21550B` (TI datasheet SLUSE89C,
"PACKAGING INFORMATION" addendum, read directly).

Why DWK rather than DW: the board's footprint has **no pads at positions 12
and 13**, which is the DWK package, not the DW. The DWK is fabricated on the
same 16-lead frame with those two leads omitted -- and the reason is
visible in the datasheet's absolute-maximum table: *"Channel to channel
isolation voltage | |VSSA-VSSB| in DWK package | 1850 V"*, i.e. the omission
buys channel-A-to-channel-B isolation, **not** primary-to-secondary
creepage. (The board footprint's own `descr` says the leads are omitted
"for isolation creepage/clearance", which is true only in that
channel-to-channel sense. Minor, but it is the sort of claim that gets
re-used.)

Both land-pattern options are published for DWK0014A as well as DW0016B, so
the HV option is available whichever package is chosen.

### Margin caveat

8.100mm clears the 8.0mm gate by 0.100mm and does **not** clear the CP-SAT
module's 8.5mm working corridor. If the barrier solve is run at 8.5mm, U7
will still be reported infeasible. Options, in order of cheapness:
(a) run the solve at 8.0-8.2mm for this component, (b) accept a
tighter-than-IPC-least heel fillet beyond TI's own HV option (I would not:
TI's HV option already *is* the vendor-sanctioned reduced land), or (c) a
different gate-driver package entirely. Not resolved here; the decision is
a trade between solver margin and land-pattern conservatism.

---

## Resulting picture, if all four fixes are applied

| Ref | Now | After | @8.0 | @8.5 |
|---|---:|---:|:--:|:--:|
| C6 | 3.200 | 8.000 - 8.600 (pad-diameter dependent) | YES | only at <=1.4mm pads |
| K2 | -0.500 | **12.760** | YES | YES |
| K3 | -0.500 | **12.760** | YES | YES |
| U3 | 6.020 | **8.560** | YES | YES |
| U7 | 7.250 | **8.100** | YES | **NO** |
| K1 | 8.000 (unchanged, #388) | 8.000 | YES (exactly) | NO |
| T1 | 9.100 (unchanged, #388) | 9.100 | YES | YES |
| PS1 | 35.500 | 35.500 | YES | YES |

All 8 isolators would clear the **8.0mm gate**. Three (K1 at 8.000, U7 at
8.100, C6 at stock pad diameters) would sit under the CP-SAT module's 8.5mm
working margin, so **either the corridor model's 0.5mm headroom or those
three land patterns has to give** before a barrier-constrained placement
solve can be expected to return SAT. That is a real, remaining decision, and
it is cheaper to resolve on C6 (shrink pads to 1.4mm -> 8.600) than on K1 or
U7.

---

## Incidental defects found while doing this

These are reported, not fixed. Each is the fabricated-MPN defect class that
`scripts/mpn_fabrication_gate.py` exists for; none is currently caught,
because that gate only parses resistor/capacitor `value` + `mpn` pairs and
does not check MPN *existence* for actives or lead-form/footprint agreement
for passives.

**#1 -- `elec/src/modules.ato:748`: `y_cap_pe.mpn = "DE1E3KX222MA4BA01"`
does not appear to exist.**
Murata's *current* DE1/KX datasheet lists this capacitance only as
`DE1E3KX222MA4BN01F` (and `B4B` / `J4B` / `N4A` lead-style siblings, all
with individual-specification suffix `N01F`). Murata's *legacy* catalog
C80E-5 lists it as `DE1E3KX222MpppA01` with lead codes `A5B`/`B5B`/`N5A`.
The declared string is `A4B` (current lead style) + `A01` (legacy suffix) --
a combination that appears in **neither** document, and a targeted web
search returns no exact hit. This is the same signature as
`ERA-3AEB6132V`: internally plausible, externally absent.
`2026-07-27-fabricated-mpn-audit.md` already flagged this MPN as UNVERIFIED;
this pass upgrades it to *probably wrong*, with the real spellings named.
**Also note the real part is obsolete**, so correcting the string is not
enough.

**#2 -- `elec/src/components.ato:30`: `mpn = "UCC21550BDW"` is not a TI
orderable part number.** TI's own packaging addendum in SLUSE89C lists
exactly five orderables: `UCC21550ADWKR`, `UCC21550ADWR`, `UCC21550BDWKR`,
`UCC21550BDWR`, `UCC21550CDWKR` -- all tape-and-reel (`...R`). There is no
tube/`DW` variant. The comment on that line ("Fixed: was UCC21550BDWK
(14-pin), now correct 16-pin DW package") fixed one problem and introduced
another.

**#3 -- U7's declared pins contradict its own footprint.**
`components.ato:52-53` declares `signal NC_12 ~ pin 12` and
`signal NC_13 ~ pin 13`; the board footprint `lib:SOIC16W_Isolated` has no
pads 12 or 13 (verified: pads are 1-11, 14-16). If a 16-pin DW part is
actually populated, two leads land on bare laminate. Choosing
`UCC21550BDWKR` (14-pin DWK) makes the footprint right and requires deleting
those two pin declarations.

**#4 (minor) -- declared creepage slot not realised.**
`elec/src/footprints.ato:32-49` declares `SOIC16W_Isolated` with an
`isolation_slot` (`CreepageSlot`, 1.0mm x 12.3mm) and `elec/Footprints_README.md:12`
advertises "an 8mm creepage slot between primary and secondary sides". The
placed footprint contains geometry on `F.Cu`, `F.SilkS`, `F.Fab` and
`F.CrtYd` only -- no `Edge.Cuts`, no `User.*`, no non-plated hole. There is
no slot on the board. (A slot would not have changed the numbers in this
brief either way -- the gate measures copper pads -- but the README claim is
false as built.)

**#5 (not a defect, checked and cleared) --** K2 pad 5 and K3 pad 5 are both
on net `discharge.k_dis1-coil2`. That looked like a copy-paste error, but
`modules.ato:1103-1110` deliberately ties both coils' low sides to the same
`q_dis_drv.D`, so a shared net is correct. No action.

---

## What I could NOT verify (stated plainly)

- **RT1's DC breaking capacity at 170V.** Published only as a graph image in
  the datasheet PDF; not extractable, not read. The 170VDC break stays an
  open item exactly as it is today with the G5LE-1.
- **RT114012 / RT214012 distributor stock.** Both appear in TE's own product
  table with TE part numbers; I confirmed stock only for `RT314012`.
- **DigiKey's 14.2mA coil-current figure for RT314012** vs. the datasheet's
  360R/400mW. Contradiction noted, not resolved.
- **H11L1TVM's certified creepage/clearance and its VDE 0884 certificate.**
  The datasheet gives V_ISO and the VDE file number, no creepage figure. The
  0.4" lead form fixes the *board* geometry; whether the *component* is
  certified reinforced at this working voltage is unresolved.
- **`DE1E3RA222MA4BN01F` lifecycle at first party.** Reported obsolete by
  distributor/aggregator sources; Murata's own PIM page is a JavaScript
  application that WebFetch could not render.
- **Vishay VY1 bulk / straight-lead ordering codes.** Constructible from the
  datasheet's ordering table, deliberately not constructed -- that is the
  exact move this repo's MPN gate exists to prevent.
- **IEC 60335-1's primary text** for the 8.0mm figure itself: still
  paywalled, still UNVERIFIED at primary, unchanged from
  `check_isolation_keepout.py`'s own docstring and every prior evidence doc.
- **Whether the 8.5mm CP-SAT working margin should be reduced to ~8.2mm** so
  that K1/U7/C6 fit. That is a modelling decision for a human; I did not make
  it, and I did not touch the 8.0mm safety figure in any direction.
- **No live CP-SAT re-solve was run** with the proposed geometries. Every
  "after" number in this brief is closed-form arithmetic over the candidate
  land pattern -- the same arithmetic the solver uses per isolator, which is
  position- and rotation-independent by construction -- but the full
  168-component packing question has not been re-asked.

---

## Hard-constraint compliance

- `elec/src/*.ato`, `docs/hardware/BOM.md`, `pcb/temper.kicad_pcb`: **not
  modified** (`git status --short` clean apart from this file).
- `mpn-fabrication-allowlist.yaml`: **not modified**, nothing added.
- **No MPN in this document was constructed by pattern-matching a
  manufacturer's numbering scheme.** Every part number proposed
  (`VY1222M47Y5UQ6TV0`, `RT314012`, `H11L1TVM`, `UCC21550BDWKR`) was read
  off a manufacturer datasheet table or a distributor product page that was
  actually fetched in this session. Where a code *could* have been
  constructed (VY1 bulk/straight-lead variants, RT1 pin-pitch siblings), it
  was explicitly left unwritten and labelled.
- The 8.0mm creepage requirement was never reduced, and no gate, threshold or
  baseline was weakened.
- No `git stash`.

---

## Sources (all fetched 2026-07-28)

**Datasheets, read directly:**

- TI UCC21550, SLUSE89C (May 2023, rev. Aug 2024) --
  https://www.ti.com/lit/ds/symlink/ucc21550.pdf
  Used: section 5.6 Insulation Specifications (CLR >8mm, CPG >8mm, CTI >600V,
  V_ISO 5000 Vrms) and footnote (1); Absolute Maximum Ratings
  (|VSSA-VSSB| in DWK = 1850V); Device Information table; "EXAMPLE BOARD
  LAYOUT" drawings for DW0016B and DWK0014A (IPC-7351 nominal: 16X(2) pads,
  (9.3) span, 7.3mm clearance/creepage; HV/ISOLATION OPTION: 16X(1.65) pads,
  (9.75) span, 8.1mm clearance/creepage); PACKAGING INFORMATION addendum
  (orderable part numbers and status).
- TE Connectivity / Schrack Power PCB Relay RT1 --
  https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8
  Used: FEATURES ("5kV/10mm coil-contact, reinforced insulation"; "Product in
  accordance to IEC 60335-1"); INSULATION DATA (contact-coil clearance/creepage
  >=10/10mm, 5000 Vrms); COIL VERSIONS DC (012: 12V, operate 8.4V, release 1.2V,
  360R +/-10%, 400mW); CONTACT DATA (250VAC rated, 400VAC max switching);
  PRODUCT INFORMATION table (RT114012 / RT214012 / RT314012 and TE part numbers);
  PRODUCT CODE STRUCTURE.
- Fairchild / onsemi H11L1M, H11L2M, H11L3M "6-Pin DIP Schmitt Trigger Output
  Optocoupler", Rev 1.0.0 --
  https://datasheet.octopart.com/H11L1SM.-Fairchild-Semiconductor-datasheet-8428600.pdf
  Used: Features (UL E90700 vol.2; VDE file #102497 via option `V`; open
  collector sinking 16mA at 0.4V); Schematic (pinout 1=Anode 2=Cathode 3=NC
  4=Vo 5=GND 6=Vcc); Isolation Characteristics (V_ISO 7500 V_PEAK, t=1s);
  Package Dimensions "0.4" Lead Spacing" (0.400 (10.16) / 0.425 (10.80));
  Ordering Information table (`T`, `V`, `TV`, `S`, `SV`, `SR2`, `SR2V`).
- Murata DE1 / Type KX X1,Y1 safety capacitors (EKTDE10A) --
  https://pim.murata.com/asset/pim4/ceramicCapacitorLead/DE1_KX_N01F_E_PDF_CERAMICCAPACITORLEAD
  Used: 2-2 Rated Voltage (X1: AC440V, Y1: AC250V); 2-3 part-number
  configuration ("DE1 denotes class X1,Y1"; lead-style codes A*/B*/J*/N*);
  4. Part number list (`DE1E3KX222MA4BN01F`, D=9.0, T=7.0, **F=10.0**, d=0.6).
- Murata Cat. No. C80E-5 (legacy safety-capacitor catalog) --
  https://www.farnell.com/datasheets/3773.pdf
  Used: DE1E3KX222MpppA01 row (250VAC, 2200pF +/-20%, **lead spacing 10.0mm**,
  lead codes A5B/B5B/N5A) -- establishes that the `A01` suffix historically
  pairs with `A5B`, never `A4B`.
- Vishay BCcomponents VY1 Series, doc 28537, rev. 18-Aug-2025 --
  https://www.vishay.com/docs/28537/vy1series.pdf
  Used: title/class ("Class X1, 760 VAC, Class Y1, 500 VAC"); technical-data
  table (2200pF Y5U: Dmax 12.0, Tmax 5.0, **F = 10.0 or 12.5mm +/-1mm**,
  `VY1222#47Y5UQ6###`); ORDERING CODE table (digits 15-17 = packaging / lead
  style / lead spacing; `0` = 10.0mm).

**Distributor product pages, fetched and read:**

- Vishay `VY1222M47Y5UQ6TV0` -- https://www.digikey.com/en/products/detail/vishay-beyschlag-draloric-bc-components/VY1222M47Y5UQ6TV0/2824499
  (Active; 365 in stock; 2200pF +/-20%; 760VAC; X1,Y1; **lead spacing 0.394"
  (10.00mm)**; body dia 0.472" (12.00mm); Y5U)
- TE `RT314012` -- https://www.digikey.com/en/products/detail/te-connectivity-potter-brumfield-relays/RT314012/1128622
  (Active; **7,442 in stock**; SPDT/1 form C; 12VDC coil; 360 ohm; 16A;
  400VAC max switching; through hole)
- onsemi `H11L1TVM` -- https://www.digikey.com/en/products/detail/onsemi/H11L1TVM/401266
  (Active; 1,701 in stock + 6,000 factory; **6-DIP (0.400", 10.16mm)**;
  4170 Vrms; open collector; 3V-15V supply)
- Murata `DE1E3KX222MA4BN01F` -- https://www.digikey.com/en/products/detail/murata-electronics/DE1E3KX222MA4BN01F/4421160
  (**Obsolete, "no longer manufactured", 0 stock**; 2200pF; 250VAC; X1,Y1;
  **lead spacing 0.394" (10.00mm)**; substitute suggested:
  `DE1E3RA222MA4BN01F`)

**In-repo sources:**

- `packages/temper-placer/src/temper_placer/core/pad_geometry.py` (the model)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`
  (`compute_pad_groups`, `evaluate_isolator_feasibility`)
- `scripts/check_isolation_keepout.py:173` (`MIN_BARRIER_WIDTH_MM = 8.0`)
- `elec/src/modules.ato` (`PowerInput` Y-cap + ZCD, `BusDischarge`),
  `elec/src/components.ato` (`UCC21550BDWK`, `H11L1`, `Relay_SPDT`),
  `elec/src/footprints.ato:32`
- `docs/evidence/2026-07-28-pad-geometry-model-fix.md`,
  `docs/evidence/2026-07-28-barrier-constrained-placement.md`,
  `docs/evidence/2026-07-27-fabricated-mpn-audit.md`
- KiCad 9 stock footprint libraries as installed
  (`/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`):
  `Relay_THT.pretty`, `Package_DIP.pretty`, `Package_SO.pretty`,
  `Capacitor_THT.pretty`
