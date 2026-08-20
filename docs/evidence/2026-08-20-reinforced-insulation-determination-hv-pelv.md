<!-- provenance: branch research/reinforced-insulation-determination, based on origin/main tip eb5022510.
     pcb/temper.kicad_pcb sha256 = 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
     verified identical before and after this session -- never opened for write. No design value,
     threshold, DRC rule, DRU, ratchet, oracle or config was changed. MIN_BARRIER_WIDTH_MM = 12.6
     remains enforced. elec/**/*.ato was read only.
     This document reads no repo state at runtime and loads no compiled extension, so
     `make venv-isolate` was NOT run -- stated explicitly per the task brief.
     Primary standards text: IS 302-1:2008 (BIS adoption of IEC 60335-1, Sixth Revision, published
     under India's RTI Act at law.resource.org), sha256
     924652d8e791c780fc09d934600ad2558fd5a63e1feb76464963b471ee2d3168, 5,568,079 bytes, 80 PDF
     pages -- the identical document 0cbc04248 used, re-downloaded and re-hashed this session.
     The PDF is image-only (`pdftotext` yields 38 lines, all RTI cover boilerplate). It was read
     two ways: (a) a full-document OCR text layer produced this session by rendering each printed
     column separately at 150 dpi with `pdftoppm -x/-W` and OCRing via libtesseract5 through a
     ctypes shim (the `tesseract` CLI is not installed; `eng.traineddata` was fetched from
     tessdata_fast), which keeps the two-column text un-interleaved and searchable; and (b) for
     EVERY load-bearing quotation below, a direct read of the 150-160 dpi full-page render, cited
     by printed page number. Quotations marked "page-verified" were read from the image, not OCR. -->

# Reinforced insulation IS required between the HV domain and this board's LV domain. The ×2 of cl. 29.2.3 applies. Unconditionally, on two independent primary-text grounds, neither of which depends on user accessibility.

## Verdict, first line

**The ×2 applies. Yes. Not conditionally.**

Every creepage figure now in force stays where it is: `MAINS↔SELV` 4.8 mm, `DC_BUS↔SELV`
8.0 mm, `SELV↔TANK` ≥20.0 mm floor. **Nothing halves.** `MIN_BARRIER_WIDTH_MM` = 12.6 is
untouched by this document (and was never opened for write).

The flag left open by `0cbc04248` — *"`gnd ~ pe` makes the LV domain PELV per cl. 3.4.4,
which permits three separations of which reinforced is only one"* — is correct on its
facts and does not lead where it might appear to. The three separations cl. 3.4.4 permits
are **(i) basic insulation *and protective screening*, (ii) double insulation,
(iii) reinforced insulation**. Basic insulation *alone* is not among them. The only branch
that would halve the figures is (i), and it requires an **earthed screen** interposed
between the circuits — which this board's barrier, a copper-free keepout spanning every
layer, does not contain and by construction cannot contain.

And branch (i) is independently foreclosed anyway, by a clause nobody in this repository
has cited yet:

> **22.27** Parts connected by protective impedance shall be separated by double insulation
> or reinforced insulation.
> Compliance is checked by the tests specified for double insulation or reinforced insulation.

This board declares two protective-impedance chains bridging `+170V_BUS` into LV-domain
nets (`elec/domain_manifest.yaml:1054-1073`). **cl. 22.27 therefore requires double or
reinforced insulation between the HV and LV parts as a matter of this construction's own
declared topology, with no protective-screening escape and no dependence on whether
anything is user-touchable.** It closes the door that cl. 3.4.4 opens.

**This question is closed. It should not be re-opened without a change to the physical
construction — specifically, without removing the OVP protective-impedance dividers AND
adding a PE-bonded protective screen. §6 states exactly what that would take.**

---

## Provenance labels

| Label | Meaning |
|---|---|
| **PRIMARY** | Standard's own text, retrieved and read directly this session; source, printed page and method given. |
| **REPO** | Read this session from this repository's committed files (path and quote given). |
| **INFERRED** | Reasoning on labelled inputs, shown in full and marked as reasoning, never as standards text. |
| **UNOBTAINABLE** | Not reached. Stated as a gap; never reconstructed. |

---

## 1. The classification of this board's LV domain: it is PELV, and cl. 27.1 makes that mandatory rather than optional

### 1.1 `gnd ~ pe` is real — REPO, verified this session

`elec/src/main.ato:753`, at the foot of a 27-line comment block headed
"GROUND ARCHITECTURE — Floated SELV domain, PE-bonded (2026-07-26)":

```
    gnd ~ pe  # SELV ground reference: bonded to protective earth, NOT to power_return
```

`pe` reaches the LV domain from the AC inlet (`main.ato:692`,
`power_in.pe ~ pe  # Protective earth, from the external AC connector`). The bond is a
direct 0 Ω net join, not an impedance — the same comment block distinguishes it explicitly
from the Y-cap path: *"The new gnd → PE bond is a separate, direct (0 ohm) DC path that
never touches power_return."*

The doubler-midpoint correction from `0cbc04248` is re-confirmed independently here.
`elec/src/modules.ato:932-936`:

```
    # Y-capacitor: PE bonding from doubler midpoint to protective earth.
    # Class I appliance pattern: provides EMI return path from the power
    # return net to PE without a DC short.
```

So there are two distinct PE ties with different characters: `gnd → pe` is a hard DC bond,
`power_return → pe` is a 2.2 nF Y1 AC-only coupling. **`gnd` is earthed. `power_return` is
not.**

### 1.2 The domain's voltages are within SELV — REPO

`vcc_15v` / `vcc_3v3` / 5 V logic. `AuxSupply.power_out.voltage = 15V`
(`elec/src/modules.ato:1565`). No node in the LV domain is above 15 V.

### 1.3 cl. 3.4.1–3.4.4 — PRIMARY, page-verified (printed page 4, PDF page 9)

> **3.4.1 *Extra-Low Voltage*** — Voltage supplied from a source within the appliance that
> does not exceed 50 V between conductors and between conductors and earth when the
> appliance is supplied at rated voltage.
>
> **3.4.2 *Safety Extra-Low Voltage*** — Voltage not exceeding 42 V between conductors and
> earth, the no-load voltage not exceeding 50 V.
>
> When safety extra-low voltage is obtained from the supply mains, it is to be through a
> safety isolating transformer or a convertor with separate windings, the insulation of
> which complies with double insulation or reinforced insulation requirements.
>
> NOTES
> 1 The voltage limits specified are based on the assumption that the safety isolating
> transformer is supplied at its rated voltage.
> 2 Safety extra-low voltage is also known as SELV.
>
> **3.4.3 *Safety Isolating Transformer*** — Transformer, the input winding of which is
> electrically separated from the output winding by an insulation at least equivalent to
> double insulation or reinforced insulation, that is intended to supply an appliance or
> circuit at safety extra-low voltage.
>
> **3.4.4 *Protective Extra-Low Voltage Circuit*** — Earthed circuit operating at safety
> extra-low voltage which is separated from other circuits by basic insulation and
> protective screening, double insulation or reinforced insulation.
>
> NOTES
> 1 Protective screening is the separation of circuits from live parts by means of an
> earthed screen.
> 2 A protective extra-low voltage circuit is also known as a PELV circuit.

15 V, earthed. **PELV.** The flag was right.

### 1.4 cl. 27.1 makes PELV compulsory here, not merely descriptive — PRIMARY, page-verified (printed page 47, PDF page 52)

> Class II appliances and Class III appliances shall have no provision for earthing.
>
> **Safety extra-low voltage circuits shall not be earthed unless they are protective
> extra-low voltage circuits.**
>
> Compliance is checked by inspection.

This matters more than it looks. The repo has, at various times, called the LV domain
"SELV" (`main.ato:753`'s own comment says "SELV ground reference"; the domain is named
`SELV_LV` in `docs/PCB_SAFETY_DESIGN_RULES.md:17`; `elec/domain_manifest.yaml` and the
gate scripts all say SELV). Under cl. 27.1, an **earthed** SELV circuit is
*non-compliant as SELV* — earthing it is only permitted if it is a PELV circuit. So the
board is not choosing between "SELV" and "PELV": having bonded `gnd ~ pe`, PELV is the
only compliant classification available, and cl. 3.4.4's separation requirement is the one
that binds. Calling it SELV in the manifests is a naming inaccuracy, not a second option.

**Classification: PELV. Basis: cl. 3.4.4 read with cl. 3.4.2 and cl. 27.1, all
page-verified primary text; `gnd ~ pe` verified at `elec/src/main.ato:753`.**

---

## 2. The three separations cl. 3.4.4 permits, named from clause text, with the condition each carries

Straight from 3.4.4 as quoted in §1.3, in the standard's own order:

| # | Separation | Condition it carries | Creepage consequence |
|---|---|---|---|
| **i** | **basic insulation *and* protective screening** | An **earthed screen** between the circuits — cl. 3.4.4 NOTE 1: *"Protective screening is the separation of circuits from live parts by means of an earthed screen."* The screen must be a real earthed conductor interposed between HV and LV, with earthing continuity satisfying cl. 27.5 (≤0.1 Ω, measured). | Table 17 **basic** figure applies to the HV↔screen gap (cl. 29.2.1). The task's "×1" column. |
| **ii** | **double insulation** | cl. 3.3.3: *"Insulation system comprising both basic insulation and supplementary insulation."* Two **independent** insulations. cl. 29.2.1 sets basic at the Table 17 figure; cl. 29.2.2: *"Creepage distances of supplementary insulation shall be at least those specified for basic insulation in Table 17."* | Two separate creepage paths, each at the Table 17 basic figure, in series with an intermediate part between them — **not** one gap at the basic figure. |
| **iii** | **reinforced insulation** | cl. 3.3.4: *"Single insulation applied to live parts, that provides a degree of protection against electric shock equivalent to double insulation under the conditions specified in this standard."* | cl. 29.2.3, page-verified printed page 52: *"Creepage distances of reinforced insulation shall be at least **double** those specified for basic insulation in Table 17."* The ×2. |

**Basic insulation on its own is not one of the three.** That is the whole point of the
table, and it is why the flag's phrasing — "reinforced is only one of three" — does not
imply that two of the three are cheaper. Only branch (i) is cheaper per-gap, and it buys
the reduction by adding a **conductor**, not by removing a requirement.

Two collateral notes worth recording so they are not re-discovered as if they were escapes:

- **cl. 29.1.5 NOTE 2 is the standard's only earthing-based relaxation, and it is a
  *clearance* relaxation** — PRIMARY, page-verified (printed page 52, PDF page 57):
  *"If the secondary winding of a step-down transformer is earthed, or if there is an
  earthed screen between the primary and secondary windings, clearances of basic insulation
  **on the secondary side** shall be not less than those specified in Table 16, but using
  the next lower step for rated impulse voltage as a reference."* Followed immediately by
  NOTE 3: *"The use of an isolating transformer without an earthed protective screen or
  earthed secondary does not allow a reduction in the rated impulse voltage."* This is
  about clearances *within* the secondary circuit, is scoped to basic insulation, and
  **has no creepage analogue anywhere in cl. 29.2**. Earthing the secondary buys one
  impulse step of clearance. It does not touch Table 17.
- **cl. 27.5 confirms PELV circuits may internally carry basic insulation** — PRIMARY,
  page-verified (printed page 48, PDF page 53): *"If the clearances of basic insulation in a
  protective extra-low voltage circuit are based on the rated voltage of the appliance, this
  requirement does not apply to connections providing earthing continuity in the protective
  extra-low voltage circuit."* This is about basic insulation *inside* the PELV circuit and about
  which earthing connections need the 0.1 Ω test. It says nothing about the HV↔PELV
  barrier.

---

## 3. Which separation applies to *this* construction — and why (i) is unavailable twice over

### 3.1 First foreclosure: there is no earthed screen, and the barrier is defined as the absence of one — REPO

`scripts/check_isolation_keepout.py` enforces the barrier as a **keepout region**, not as a
screened structure. From its own docstring:

> Looks for a zone on the board that is BOTH a keepout (`keepoutSettings` is not None, i.e.
> a "rule area" in modern KiCad terms, not an ordinary copper pour) AND named exactly
> `BARRIER_ZONE_NAME` … 1. LAYER SPAN: the zone's declared layers, after expanding `*.Cu`
> wildcards, cover every copper layer the board's own stackup declares … 2. KEEPOUT
> SETTINGS: tracks/vias/pads/copperpour/footprints are all [excluded]

A region from which tracks, vias, pads, copper pour and footprints are all excluded on
every copper layer is, by definition, a region containing **no earthed screen**. The
12.6 mm figure is a single uninterrupted surface creepage path between HV copper and LV
copper. Branch (i) of cl. 3.4.4 is therefore not the separation this board has. Branch (ii),
double insulation, likewise requires an intermediate part between two independent
insulations (cl. 3.3.3) and there is none. **What remains is (iii), reinforced.**
(INFERRED — this is the application of §2's clause text to the construction, and is
labelled as reasoning, not as standards text. The clause text and the construction facts
underneath it are each PRIMARY/REPO.)

### 3.2 Second foreclosure, and the durable one: cl. 22.27 — PRIMARY, page-verified (printed page 34, PDF page 39)

> **22.26** Appliances having parts of Class III construction shall be constructed so that
> the insulation between parts operating at safety extra-low voltage and other live parts
> complies with the requirements for double insulation or reinforced insulation.
> Compliance is checked by the tests specified for double insulation or reinforced insulation.
>
> **22.27** Parts connected by protective impedance shall be separated by double insulation
> or reinforced insulation.
> Compliance is checked by the tests specified for double insulation or reinforced insulation.

**cl. 22.27 is the one that settles this**, because this board *declares* protective
impedance across exactly this boundary. `elec/domain_manifest.yaml:1054-1073` — REPO,
quoted in full structure:

```yaml
protective_impedance_chains:
  - name: ovp01_comparator_divider
    chain: [safety.ovp.r_div_top1, safety.ovp.r_div_top2, safety.ovp.r_div_top3]
    boundary_a: "+170V_BUS"
    boundary_b: "safety.ovp.comp-inp"
    min_length: 3
  - name: ovp01_adc_sense_divider
    chain: [safety.ovp.r_adc_top1, safety.ovp.r_adc_top2, safety.ovp.r_adc_top3]
    boundary_a: "+170V_BUS"
    boundary_b: "V_BUS_SENSE"
    min_length: 3
```

Both chains connect the HV half-bus to an **LV-domain net** — a comparator input and the
MCU's bus-sense ADC node. `RTDSensing`'s own docstring records the same fact from the other
side (`elec/src/modules.ato:1772-1778`): *"the OVP bus-sense divider in
SafetyInterlock/OVPComparator still connects resistively from the HV half-bus into this
same `gnd` net … so `gnd` — and therefore this module — is not yet on a domain with ZERO
galvanic connection to HV, only a high-impedance (~1.3M ohm / ~520k ohm) one."*

The HV domain and the LV domain are therefore, in the standard's exact words, **"parts
connected by protective impedance"** — and cl. 22.27 requires them to be separated by
double or reinforced insulation. Note what cl. 22.27 does *not* offer: it has no
protective-screening branch. Where cl. 3.4.4 lists three separations, cl. 22.27 lists two,
and the earthed-screen option is the one it omits.

The relevant protective-impedance construction requirements are met, which is what keeps
cl. 22.27 (rather than something worse) the operative clause — PRIMARY, cl. 22.42, printed
page 35: *"Protective impedance shall consist of at least two separate components whose
impedance is unlikely to change significantly during the lifetime of the appliance. If any
one of the components is short-circuited or open-circuited the values specified in 8.1.4
shall not be exceeded."* Three series resistors per chain, `min_length: 3` enforced by
`check_domain_partition.py`'s `check_chain_integrity`; the single-fault currents recorded
in `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:66` (380.4 µA / 949.7 µA worst
two-shorted-resistor case) sit under cl. 8.1.4's protective-impedance limit — PRIMARY,
page-verified printed page 12: *"the current between the part and the supply source shall
not exceed 2 mA for dc, its peak value shall not exceed 0.7 mA for ac."*

*(Out of scope but flagged for the owner: cl. 8.1.4's ac limit is **0.7 mA peak**, and the
repo's touch-current arithmetic is carried against a 1.35 mA figure from IEC 60335-2-6.
Whether the divider currents are assessed as dc or as ac-peak is a question this document
did not take up.)*

### 3.3 The Class-III-construction leg, offered but not relied on — INFERRED

cl. 22.26 (quoted above) would give a third independent route to double-or-reinforced *if*
the LV domain is "a part of Class III construction". cl. 3.3.13 — PRIMARY, page-verified
printed page 4: *"**Class III Construction** — Part of an appliance for which protection
against electric shock relies upon safety extra-low voltage and in which voltages higher
than those of safety extra-low voltage are not generated."* The LV domain plainly satisfies
the second half. The first half is arguable in both directions: protection here relies on
extra-low voltage **plus** earthing, which is what makes it PELV rather than a Class III
part. **Marked INFERRED and not load-bearing.** §3.1 and §3.2 each carry the verdict alone.

### 3.4 One more floor, which relaxes nothing — PRIMARY, page-verified printed page 34

> **22.31** Clearances and creepage distances over supplementary insulation and reinforced
> insulation shall not be reduced below the values specified in **29** as a result of wear.
> If a part, such as a wire, screw, nut or spring, becomes loose or falls out of position,
> clearances and creepage distances between live parts and accessible parts shall not be
> reduced below the values specified for supplementary insulation.

Recorded because it is the only clause in the standard that pairs "live parts" with
"accessible parts" and a creepage figure, and someone will find it. It is a
displaced-part floor at the *supplementary* (= basic, per 29.2.2) figure. It does not
authorise designing to that figure.

---

## 4. Does anything user-accessible conduct? — the never-answered item 8, answered

**Short answer: on the board as committed, no LV conductor is user-accessible through a
connector, because no such connector exists. But the LV domain is galvanically continuous
with the user-accessible metal chassis through the `gnd ~ pe` bond, and every documented
next step adds user-accessible LV conductors. And the verdict in §3 does not depend on any
of this.**

### 4.1 As-built: the connectors are not there — REPO

`docs/hardware/RTD_PROBE_INTERFACE_ANALYSIS.md` (2026-08-07) is a completed investigation of
exactly this, and its finding is unambiguous: *"No RTD probe connector exists anywhere in
`elec/src/*.ato`, the compiled netlist, or `pcb/temper.kicad_pcb`."* `rtd_force_p/n`,
`rtd_sense_p/n` are each a genuine single-pin net terminating at the MAX31865
(`U9.12/8/11/10`). Same for `usb_dn`/`usb_dp` (verdict: *"vestigial MCU-pin wiring, not a
stalled feature"*), and for `mcu.TXD0`/`mcu.RXD0`. That document's §2 states: *"The **only**
connector instantiated anywhere in `elec/src` is a single 2-pin `PinHeader_1x02` for the fan
(`j_fan`, `modules.ato:1672`)."* — that line reference has drifted; `j_fan = new
PinHeader_1x02` is at `elec/src/modules.ato:1644` as of this session's tip, and the finding
is unchanged.

So, itemising the task's list against the committed design:

| candidate | status as committed |
|---|---|
| RTD probe jack (`J_RTD1`) | **not instantiated** — spec-only in `docs/CONNECTORS_AND_WIRING.md` (JST `B4B-XH-A`) |
| Heatsink sensor jack (`J_RTD2`) | **not instantiated** — spec-only |
| USB | **not instantiated** — no connector, no firmware stack (`grep -rli usb firmware/` empty) |
| Debug header (`J_DEBUG`, Samtec FTSH-105 JTAG) | **not instantiated** — spec-only |
| Programming header (`J_PROG`, 6-pin UART) | **not instantiated** — spec-only |
| UI header (`J_UI`, 8-pin: 3V3/GND/encoder A/B/button/LED) | **not instantiated** — spec-only |
| Fan header (`J_FAN`) | **instantiated**, 2-pin, internal to the chassis |
| Coil terminals (`J_COIL`) | HV, not LV |

### 4.2 But the LV domain reaches user-accessible metal anyway — REPO

`docs/CONNECTORS_AND_WIRING.md` §4:

> - **PE (Protective Earth)**: Star point on Chassis.
> - **PCB Grounding**: Mounting holes connected to Chassis GND via metal standoffs. AC Inlet
>   PE connected to Chassis Star Point. PCB PE pad connected to Chassis Star Point.

The chassis is a **vintage RCA 12A3 steel tube-amplifier chassis** (`docs/ASSEMBLY_GUIDE.md`,
`docs/COIL_BRACKET_DESIGN.md`, `docs/reports/PROJECT_STATUS_20251216.md`) — user-accessible
metal on every side of the appliance. `gnd ~ pe`, `pe` → chassis star point → chassis.
**The LV domain's reference conductor is the same conductor a user's hand lands on.**

That is not, by itself, a defect — it is the Class I pattern, and cl. 3.3.9 (*"conductive
accessible parts are connected to the protective earthing conductor … in such a way that
conductive accessible parts cannot become live in the event of a failure of the basic
insulation"*) is precisely the provision for it. But note the asymmetry, and it is the
reason cl. 3.4.4 demands a **screen** rather than accepting an earthed **circuit**: an
earthed accessible metal part carries fault current to earth and clears the branch
protection. An earthed *circuit* has one earthed conductor (`gnd`) and many un-earthed ones
(3V3 logic, RTD sense lines, encoder lines) which run out of the chassis on harnesses. A
HV→LV insulation failure that lands on a signal conductor rather than on `gnd` does not
clear anything; it energises the signal net. A protective screen intercepts that fault
before it reaches the circuit at all. The board has no screen. (INFERRED, labelled.)

### 4.3 A correction the repo needs: the RTD is **not** a user-touchable food probe — REPO

Six repository documents describe the RTD as a *"user-touchable RTD food probe"* or
*"user-touchable, food-contact"*: `docs/STRATEGY.md:1780-1783`,
`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:35`,
`docs/hardware/SELV_ISOLATION_REDESIGN.md:9,107`,
`docs/evidence/2026-07-30-insulation-tier-audit.md:96-100,377`,
`docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md:53,503`, and
`scripts/check_isolation_keepout.py`'s own docstring (*"the RTD probe reads the pan surface,
and the UI (buttons, USB) is touched directly during operation"*).

The mechanical specification says otherwise. `docs/SENSOR_MOUNT_DESIGN.md` §1 and §3.3:

> The pan sensor mount … ensures the RTD (PT100) sensor maintains consistent physical and
> thermal contact with the **underside of the glass-ceramic cooktop**.
>
> ```
> [ Pan ]
> ------------------- [ Glass-Ceramic (4mm) ]
>       (Thermal Grease)
>    [ Aluminum Button ]
>    [ PT100 Element ]
>    [ PTFE Guide Sleeve ]
>    [ Compression Spring ]
>    [ Chassis Base Plate ]
> ```

The PT100 sits **inside the enclosure, under 4 mm of glass-ceramic**, spring-loaded against
an aluminium button on a bracket bolted to the chassis. It is a pan-surface sensor, not a
removable food probe, and nothing in the mechanical design puts it where a user can touch
it. `docs/hardware/RTD_PROBE_INTERFACE_ANALYSIS.md` §1 independently calls it *"the
dedicated pan/food-temperature probe that closes the PID loop"* with a *"Spring-Loaded Pan
Sensor Mount."*

**I am recording this because it removes one of the arguments previously used to justify
reinforced, and the verdict survives its removal without a scratch.** The
`check_isolation_keepout.py` docstring's stated rationale — "a barrier between a
mains-derived circuit and a part a user's hand can reach" — rests on an accessibility claim
that the as-built and as-specified design does not support. The *figure* it enforces is
correct; the *reason written next to it* is not the strongest reason available, and cl.
22.27 is. Someone auditing that docstring will find the accessibility claim shaky and may
conclude the figure is shaky too. It is not.

### 4.4 The task's alternative scenario, evaluated

The brief raised the possibility that *"nothing conducts — capacitive touch or membrane
behind a non-conductive panel, which is what three filed competitor schematics do."* This
board is not that design: the specified UI (`J_UI`) is a **rotary encoder with a shaft and a
push-button** plus an LED string on an 8-wire harness (`docs/CONNECTORS_AND_WIRING.md`
§2.6), and no capacitive-touch or membrane front end appears anywhere in `elec/src` (grep for
`touch`/`membrane`/`capacitive` in the schematic returns only unrelated prose). But the
scenario does not need adjudicating: **§3.1 and §3.2 do not reference accessibility at all.**
cl. 3.4.4 governs separation *between circuits*, and cl. 22.27 governs separation between
*parts connected by protective impedance*. Neither has a user-accessibility predicate. Even
on the most favourable reading of accessibility available, the ×2 stands.

---

## 5. What each pairing's number becomes: unchanged

| pairing | basic (Table 17, PD3, IIIa/IIIb, rows per `0cbc04248`) | required class | required creepage | in force |
|---|---|---|---|---|
| `MAINS↔SELV` | 2.4 (row ii, ×2 already applied there) | **reinforced** | **4.8** | 4.8 ✔ |
| `DC_BUS↔SELV` | 4.0 (row iii) | **reinforced** | **8.0** | 8.0 ✔ |
| `SELV↔TANK` | 10.0 (row vi) | **reinforced** | **≥20.0** | ≥20.0 floor ✔ |

The row determinations are `0cbc04248`'s and are not re-litigated here. What this document
adds is that the **class** multiplying them is reinforced, and that this is now settled from
requirement text (cl. 22.27, cl. 3.4.4) rather than assumed.

`MIN_BARRIER_WIDTH_MM` = 12.6 remains a row-iv fossil for the DC-bus crossing and remains
insufficient for the tank crossing, exactly as `0cbc04248` found. **This document changes
neither finding and changes no value.** It removes the possibility that the barrier gets
halved on a PELV argument.

---

## 6. What would actually change this answer — stated so the escape hatch is named rather than left to be re-discovered

Branch (i) of cl. 3.4.4 is a real branch. Taking it would require **all** of:

1. **A protective screen physically interposed between the HV and LV copper**, on every
   copper layer, bonded to PE. Not a pour that happens to be near the barrier — an earthed
   conductor *between* the two circuits, such that no direct HV↔LV surface path exists that
   does not pass the screen.
2. **Earthing continuity for that screen meeting cl. 27.5** — PRIMARY, page-verified printed
   page 48: a current of 1.5× rated current or 25 A, whichever is higher, from a ≤12 V
   source, passed between the earthing terminal and the part, with calculated resistance
   *"not exceed[ing] 0.1 Ω."* A guard trace sized for logic currents does not pass this.
3. **cl. 27.6 satisfied, if the screen is PCB copper** — PRIMARY, page-verified printed page
   48: *"The printed conductors of printed circuit boards shall not be used to provide
   earthing continuity in hand-held appliances. They may be used to provide earthing
   continuity in other appliances if: a) at least two tracks are used with independent
   soldering points and the appliance complies with 27.5 for each circuit; and b) the
   material of the printed circuit board complies with IS 5921 (Part 6) or IS 5921 (Part 7)."*
   This appliance is not hand-held, so the route is open — but it costs **two independent
   tracks with independent soldering points**, each passing the 27.5 test, plus a laminate
   material declaration. (Side finding, out of scope but flagged: the same clause governs the
   existing `gnd ~ pe` bond wherever that continuity is carried on PCB copper rather than to
   a stud. Not assessed here.)
4. **Basic-insulation creepage (Table 17, undoubled) on the HV↔screen gap**, per cl. 29.2.1.
   The 12.6 mm single gap becomes two gaps plus a conductor; whether that is a net saving in
   board area on a 100 × 150 mm board is a layout question, not a standards one.
5. **Removal or re-architecture of the OVP protective-impedance dividers.** This is the
   blocking condition. cl. 22.27 has no screening branch: while `+170V_BUS` is connected by
   protective impedance to `safety.ovp.comp-inp` and `V_BUS_SENSE`, double or reinforced
   insulation is required between those parts regardless of any screen. **A screen alone
   does not unlock branch (i) on this construction.**

Any one of 1–5 failing leaves the ×2 in force. All five are construction changes.

---

## 7. Confidence, edition risk, and what remains unobtainable

**Confidence in the verdict: high.** Two independent primary-text legs (cl. 3.4.4 with the
construction fact that the barrier is a copper-free keepout; cl. 22.27 with the
construction fact that protective-impedance chains are declared across the boundary), plus
a third (cl. 22.26) offered and explicitly not relied on. The single INFERRED step in each
leg is the application of quoted clause text to a REPO-verified construction fact, shown in
full at §3.1 and §3.2.

**Edition risk — the one real gap, and it is stated rather than papered over.** All
quotations are from **IS 302-1:2008**, the BIS adoption (Sixth Revision). Clause numbers
3.3.x, 3.4.x, 8.1.4, 22.26, 22.27, 22.31, 22.42, 27.1, 27.5, 27.6, 29.1.x and 29.2.x are stable
in this text. **IEC 60335-1:2020 Ed. 6 was not obtained** and I did not attempt to obtain
it. `0cbc04248` already established that Table 17 is not frozen across editions (the
UL/CSA 6th Ed. has written >30 kHz creepage into these same clauses). Whether cl. 22.27
survives verbatim into Ed. 6 is **not verified**. It is a construction requirement of long
standing and I have no reason to expect it moved, but that expectation is not evidence and
is not offered as any. — **UNOBTAINABLE (Ed. 6).**

**Still unobtainable, unchanged from `0cbc04248`:** IEC 60664-4, needed for the 47 kHz tank
crossing above IEC 60664-1's 30 kHz scope ceiling. Not sought this session; nothing here
depends on it. The tank pairing's ≥20.0 mm remains a floor derived on the ≤30 kHz basis,
and the *class* multiplying it — reinforced — is what this document establishes, not the
row.

**Not sought:** no certification body, lab, or manufacturer was contacted.

---

## 8. Hard-prohibition compliance

- `pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
  verified identical before and after this session; never opened for write.
- `MIN_BARRIER_WIDTH_MM` = 12.6 unchanged. No DRC rule, DRU, threshold, ratchet, oracle or
  config changed. `power_pcb_dataset/drc_ceiling.json` untouched.
- `elec/**/*.ato` read only. `elec/domain_manifest.yaml` read only.
- No `git stash`. No history rewrite. No `gh pr merge --admin`.
- This document is evidence for the owner's decision. It is not the decision, and it
  authorises no change.
